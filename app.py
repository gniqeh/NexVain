from __future__ import annotations
import html
import json
import os
import re
import shutil
import io
import uuid
import math
import zipfile
import mimetypes
import hmac
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, Response, HTMLResponse, StreamingResponse
import history_store
import publish_checks
from template_engine import TEMPLATES, DEFAULT_CONTENT, CSS as TEMPLATE_CSS, render_template
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("NEXVAIN_DATA", str(ROOT / "data")))
DB = DATA / "nexvain.sqlite3"
PUBLIC = ROOT / "published"
ASSETS = ROOT / "web"
MEDIA = DATA / "media"
PACKAGES = DATA / "packages"
PACKAGES.mkdir(parents=True,exist_ok=True)
MEDIA.mkdir(parents=True,exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)
PUBLIC.mkdir(exist_ok=True)
app = FastAPI(title="NexVain", version="0.7.0")

def development_mode():
    return os.environ.get("NEXVAIN_DEV_MODE","").strip().lower() in ("1","true","yes")

@app.middleware("http")
async def protect_admin(request: Request, call_next):
    path=request.url.path
    dev=development_mode()
    if dev and (request.client is None or request.client.host not in ("127.0.0.1","::1","testclient")):
        return Response("Local access only in development mode",403)
    if not dev and (path == "/admin" or path.startswith(("/api/","/package/","/media/"))):
        expected=os.environ.get("NEXVAIN_ADMIN_PASSWORD","")
        if expected:
            import base64
            auth=request.headers.get("authorization","")
            try:
                scheme,encoded=auth.split(" ",1)
                user,pwd=base64.b64decode(encoded,validate=True).decode().split(":",1)
                valid=scheme.lower()=="basic" and hmac.compare_digest(user,os.environ.get("NEXVAIN_ADMIN_USER","admin")) and hmac.compare_digest(pwd,expected)
            except (ValueError,UnicodeError):
                valid=False
            if not valid:
                return Response("Authentication required",401,headers={"WWW-Authenticate":'Basic realm="NexVain Admin"'})
        elif request.client is None or request.client.host not in ("127.0.0.1","::1","testclient"):
            return Response("Admin password required for remote access",403)
    is_edit=(request.method in ("POST","PUT","DELETE") and path.startswith("/api/")
             and not path.startswith(("/api/history/","/api/charts","/api/assets")))
    is_restore=(request.method=="POST" and path.startswith("/api/history/restore/"))
    sensitive=(is_restore or request.method=="DELETE" or path=="/api/publish")
    if sensitive and not dev:
        secret=os.environ.get("NEXVAIN_ADMIN_PASSWORD","")
        if not secret: return Response("Configure NEXVAIN_ADMIN_PASSWORD for critical operations",403)
        if not hmac.compare_digest(request.headers.get("x-nexvain-confirm",""),secret):
            return Response("Admin password confirmation required",403)
    snap=None
    if is_edit and not is_restore:
        try: snap=history_store.create(DATA,PUBLIC,request.method+" "+path)
        except Exception: return Response("Safety snapshot failed; change cancelled",503)
    response=await call_next(request)
    if request.url.path=="/" or request.url.path.endswith((".html","/admin")):
        response.headers["Cache-Control"]="no-store"
    if is_edit and 200<=response.status_code<300 and path!="/api/publish":
        with connection() as db:
            db.execute("INSERT INTO settings(key,value) VALUES (\'draft_revision\',\'1\') ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")
    if request.method in ("POST","PUT","DELETE") and path.startswith("/api/") and not path.startswith("/api/history/"):
        history_store.audit(DATA,{"action":request.method+" "+path,"status":response.status_code,"snapshot":snap})
    return response


@contextmanager
def connection():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()

with connection() as db:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS topics (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
      page TEXT NOT NULL DEFAULT '{}', position INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS dcells (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
      template TEXT NOT NULL DEFAULT 'standard',
      page TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS topic_dcells (
      topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
      dcell_id INTEGER NOT NULL REFERENCES dcells(id) ON DELETE CASCADE,
      alias TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (topic_id,dcell_id));
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    db.execute("INSERT OR IGNORE INTO settings VALUES ('theme','blue')")
    cols={r["name"] for r in db.execute("PRAGMA table_info(dcells)")}
    if "mode" not in cols:
        db.execute("ALTER TABLE dcells ADD COLUMN mode TEXT NOT NULL DEFAULT 'editor'")
    if "content" not in cols:
        db.execute("ALTER TABLE dcells ADD COLUMN content TEXT NOT NULL DEFAULT '{}'")

class TopicIn(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    description: str = ""
    page: dict = Field(default_factory=dict)
    position: int = 0

class DcellIn(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    description: str = ""
    template: str = "standard"
    page: dict = Field(default_factory=dict)
    mode: str = "editor"
    content: dict = Field(default_factory=dict)

class RelationIn(BaseModel):
    dcell_id: int
    alias: str = ""
    position: int = 0

class ChartIn(BaseModel):
    title: str = Field(default='统计图',max_length=100)
    kind: str = 'bar'
    labels: list[str] = Field(min_length=1,max_length=20)
    values: list[float] = Field(min_length=1,max_length=20)

class SettingsIn(BaseModel):
    theme: str

def parse_row(row):
    obj = dict(row)
    if "page" in obj:
        obj["page"] = json.loads(obj["page"])
    if "content" in obj:
        obj["content"] = json.loads(obj["content"])
    return obj

def one(db, table, ident):
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (ident,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{table} not found")
    return parse_row(row)

@app.get("/api/history")
def view_history():
    return {"events":history_store.recent(DATA),"snapshots":history_store.checkpoints(DATA),
            "admin_password_configured":bool(os.environ.get("NEXVAIN_ADMIN_PASSWORD")),
            "development_mode":development_mode()}

@app.post("/api/history/checkpoint")
def manual_checkpoint():
    return {"ok":True,"snapshot":history_store.create(DATA,PUBLIC,"Manual checkpoint")}

@app.post("/api/history/restore/{ident}")
def restore_checkpoint(ident:str):
    rescue=history_store.create(DATA,PUBLIC,"Pre-restore safety copy")
    try: history_store.restore(DATA,PUBLIC,ident)
    except FileNotFoundError: raise HTTPException(404,"Checkpoint not found")
    except (ValueError,OSError,sqlite3.DatabaseError,zipfile.BadZipFile) as error:
        raise HTTPException(409,str(error))
    return {"ok":True,"restored":ident,"rescue_checkpoint":rescue}
@app.get("/api/topics")
def list_topics():
    with connection() as db:
        return [parse_row(r) for r in db.execute("SELECT * FROM topics ORDER BY position,id")]

@app.post("/api/topics")
def create_topic(item: TopicIn):
    with connection() as db:
        cur=db.execute("INSERT INTO topics(name,description,page,position) VALUES (?,?,?,?)",
            (item.name,item.description,json.dumps(item.page,ensure_ascii=False),item.position))
        return one(db,"topics",cur.lastrowid)

@app.put("/api/topics/{ident}")
def update_topic(ident: int,item: TopicIn):
    with connection() as db:
        one(db,"topics",ident)
        db.execute("UPDATE topics SET name=?,description=?,page=?,position=? WHERE id=?",
            (item.name,item.description,json.dumps(item.page,ensure_ascii=False),item.position,ident))
        return one(db,"topics",ident)

@app.delete("/api/topics/{ident}")
def delete_topic(ident: int):
    with connection() as db:
        one(db,"topics",ident)
        db.execute("DELETE FROM topics WHERE id=?",(ident,))
        return {"ok":True}

@app.get("/api/dcells")
def list_dcells():
    with connection() as db:
        return [parse_row(r) for r in db.execute("SELECT * FROM dcells ORDER BY id DESC")]

@app.post("/api/dcells")
def create_dcell(item: DcellIn):
    with connection() as db:
        cur=db.execute("INSERT INTO dcells(name,description,template,page,mode,content) VALUES (?,?,?,?,?,?)",
            (item.name,item.description,item.template,json.dumps(item.page,ensure_ascii=False),item.mode,json.dumps(item.content or (DEFAULT_CONTENT if item.mode=="template" else {}),ensure_ascii=False)))
        return one(db,"dcells",cur.lastrowid)

@app.put("/api/dcells/{ident}")
def update_dcell(ident: int,item: DcellIn):
    with connection() as db:
        one(db,"dcells",ident)
        db.execute("UPDATE dcells SET name=?,description=?,template=?,page=?,mode=?,content=? WHERE id=?",
            (item.name,item.description,item.template,json.dumps(item.page,ensure_ascii=False),item.mode,json.dumps(item.content,ensure_ascii=False),ident))
        return one(db,"dcells",ident)

@app.delete("/api/dcells/{ident}")
def delete_dcell(ident: int):
    with connection() as db:
        one(db,"dcells",ident)
        db.execute("DELETE FROM dcells WHERE id=?",(ident,))
        shutil.rmtree(PACKAGES/str(ident),ignore_errors=True)
        return {"ok":True}


@app.get("/api/templates")
def available_templates():
    return {"templates":[{"id":key,**value} for key,value in TEMPLATES.items()],
            "default_content":DEFAULT_CONTENT}

@app.post("/api/dcells/{ident}/clone")
def clone_dcell(ident: int):
    with connection() as db:
        source=one(db,"dcells",ident)
        cur=db.execute("""INSERT INTO dcells(name,description,template,page,mode,content)
            VALUES (?,?,?,?,?,?)""",(
            source["name"]+"（副本）",source["description"],source["template"],
            json.dumps(source["page"],ensure_ascii=False),
            source["mode"],
            json.dumps(source.get("content",{}),ensure_ascii=False)))
        new_id=cur.lastrowid
        if source["mode"]=="package":
            path=PACKAGES/str(ident)
            if path.exists():
                shutil.copytree(path,PACKAGES/str(new_id))
        return one(db,"dcells",new_id)

@app.get("/api/dcells/{ident}/preview",response_class=HTMLResponse)
def preview_template(ident:int):
    with connection() as db:
        d=one(db,"dcells",ident)
        theme=db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()[0]
    if d["mode"]!="template":
        raise HTTPException(400,"This dcell does not use a data template")
    tpl=d["template"] if d["template"] in TEMPLATES else "overview"
    return HTMLResponse(render_document(d["name"],d["description"],
        render_template(d["name"],d["description"],tpl,d.get("content",{})),
        '<a href="/admin">返回管理</a>',theme,TEMPLATE_CSS))

@app.get("/api/topics/{ident}/dcells")
def topic_dcells(ident: int):
    with connection() as db:
        one(db,"topics",ident)
        return [dict(r) for r in db.execute("""
          SELECT d.id,d.name,d.description,x.alias,x.position
          FROM topic_dcells x JOIN dcells d ON d.id=x.dcell_id
          WHERE x.topic_id=? ORDER BY x.position,d.id""",(ident,))]

@app.put("/api/topics/{ident}/dcells")
def set_topic_dcells(ident: int,items: list[RelationIn]):
    ids=[x.dcell_id for x in items]
    if len(set(ids))!=len(ids):
        raise HTTPException(400,"Duplicate dcell")
    with connection() as db:
        one(db,"topics",ident)
        for did in ids: one(db,"dcells",did)
        db.execute("DELETE FROM topic_dcells WHERE topic_id=?",(ident,))
        db.executemany("INSERT INTO topic_dcells(topic_id,dcell_id,alias,position) VALUES (?,?,?,?)",
            [(ident,x.dcell_id,x.alias,x.position) for x in items])
    return {"ok":True}

@app.get("/api/dcells/{ident}/topics")
def dcell_topics(ident: int):
    with connection() as db:
        one(db,"dcells",ident)
        return [dict(r) for r in db.execute("""
          SELECT t.id,t.name,x.alias FROM topic_dcells x
          JOIN topics t ON t.id=x.topic_id WHERE x.dcell_id=? ORDER BY t.position,t.id""",(ident,))]



PACKAGE_EXT={".html",".htm",".css",".js",".mjs",".json",".png",".jpg",".jpeg",".webp",".gif",".svg",".woff",".woff2",".ttf",".ico",".txt",".csv"}
@app.post("/api/dcells/{ident}/package")
async def upload_page_package(ident: int,file: UploadFile=File(...)):
    with connection() as db: one(db,"dcells",ident)
    raw=await file.read(50*1024*1024+1)
    if len(raw)>50*1024*1024: raise HTTPException(413,"ZIP exceeds 50MB")
    try:
        archive=zipfile.ZipFile(io.BytesIO(raw))
        entries=[]
        total=0
        infos=archive.infolist()
        if not 0<len(infos)<=300: raise ValueError("Invalid file count")
        for info in infos:
            if info.is_dir():continue
            path=Path(info.filename)
            if (info.filename.startswith("/") or chr(92) in info.filename or
                ".." in path.parts or ":" in info.filename or
                path.suffix.lower() not in PACKAGE_EXT):
                raise ValueError("Unsafe ZIP path or type")
            mode=(info.external_attr>>16)&0o170000
            if mode not in (0,0o100000):raise ValueError("Special file not allowed")
            if info.file_size>15*1024*1024:raise ValueError("Entry too large")
            total+=info.file_size
            if total>50*1024*1024:raise ValueError("Uncompressed package too large")
            entries.append((info,path))
        if not any(str(p)=="index.html" for _,p in entries):
            raise ValueError("Root index.html required")
        stage=PACKAGES/(str(ident)+"-staging")
        shutil.rmtree(stage,ignore_errors=True)
        stage.mkdir(parents=True)
        for info,path in entries:
            destination=stage/path
            destination.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(info) as src,destination.open("wb") as dst:
                shutil.copyfileobj(src,dst)
        target=PACKAGES/str(ident)
        previous=PACKAGES/(str(ident)+"-old")
        shutil.rmtree(previous,ignore_errors=True)
        if target.exists():target.rename(previous)
        stage.rename(target)
        shutil.rmtree(previous,ignore_errors=True)
    except (OSError,ValueError,zipfile.BadZipFile) as exc:
        raise HTTPException(400,str(exc))
    with connection() as db:
        db.execute("UPDATE dcells SET mode='package' WHERE id=?",(ident,))
    return {"ok":True,"count":len(entries),"preview":f"/package/{ident}/index.html"}


class DirectoryImportIn(BaseModel):
    path: str = Field(min_length=1,max_length=500)

@app.post("/api/dcells/{ident}/import-directory")
def import_directory(ident:int, request:DirectoryImportIn):
    """Copy a static page directory from an explicitly configured import root."""
    with connection() as db: one(db,"dcells",ident)
    configured=os.environ.get("NEXVAIN_IMPORT_ROOT","")
    if not configured:
        raise HTTPException(403,"Set NEXVAIN_IMPORT_ROOT to enable directory import")
    root=Path(configured).resolve()
    if not root.is_dir():raise HTTPException(400,"Invalid import root")
    candidate=Path(request.path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(400,"Only a relative path under the import root is allowed")
    source=(root/candidate).resolve()
    if not source.is_relative_to(root) or not source.is_dir() or source==root:
        raise HTTPException(400,"Directory outside import root")
    entries=[]
    size=0
    for path in source.rglob("*"):
        if path.is_symlink():raise HTTPException(400,"Symbolic links not allowed")
        if not path.is_file():continue
        relative=path.relative_to(source)
        if path.suffix.lower() not in PACKAGE_EXT:
            raise HTTPException(400,"Unsupported file type: "+str(relative))
        length=path.stat().st_size
        if length>15*1024*1024:raise HTTPException(413,"File exceeds 15MB")
        size+=length
        if size>50*1024*1024 or len(entries)>=300:
            raise HTTPException(413,"Directory exceeds import limits")
        entries.append((path,relative))
    if not (source/"index.html").is_file():raise HTTPException(400,"index.html required")
    stage=PACKAGES/(str(ident)+"-staging")
    shutil.rmtree(stage,ignore_errors=True)
    stage.mkdir(parents=True)
    for path,relative in entries:
        dest=stage/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,dest)
    target=PACKAGES/str(ident)
    previous=PACKAGES/(str(ident)+"-old")
    shutil.rmtree(previous,ignore_errors=True)
    if target.exists():target.rename(previous)
    stage.rename(target)
    shutil.rmtree(previous,ignore_errors=True)
    with connection() as db:
        db.execute("UPDATE dcells SET mode='package' WHERE id=?",(ident,))
    return {"ok":True,"count":len(entries),"preview":f"/package/{ident}/index.html"}


# Source workspace: a dcell package is a sandboxed, self-contained static website.
SOURCE_EDIT_EXT={".html",".htm",".css",".js",".mjs",".json",".svg",".txt",".csv"}
SOURCE_EDIT_MAX=1024*1024
class SourceIn(BaseModel):
    content: str = Field(max_length=SOURCE_EDIT_MAX)

def package_root(ident:int):
    with connection() as db:
        d=one(db,"dcells",ident)
    if d["mode"]!="package":
        raise HTTPException(409,"Convert to an independent page first")
    root=PACKAGES/str(ident)
    if not (root/"index.html").is_file():
        raise HTTPException(409,"No page package installed")
    return root

def editable_path(root:Path,filename:str):
    relative=Path(filename)
    if not filename or filename.startswith(("/",chr(92))) or chr(92) in filename or ":" in filename or ".." in relative.parts or relative.suffix.lower() not in SOURCE_EDIT_EXT:
        raise HTTPException(400,"Invalid editable file path")
    dest=(root/relative).resolve()
    if not dest.is_relative_to(root.resolve()) or dest.is_symlink():
        raise HTTPException(400,"Path outside page package")
    return dest

def zip_package(root:Path):
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(root.rglob("*")):
            if file.is_symlink():
                raise HTTPException(400,"Symlinks not allowed")
            if file.is_file():
                archive.write(file,file.relative_to(root).as_posix())
    out.seek(0)
    return out

def standalone_html(d,theme):
    if d["mode"]=="template":
        tpl=d["template"] if d["template"] in TEMPLATES else "overview"
        content=render_template(d["name"],d["description"],tpl,d.get("content",{}))
        css=TEMPLATE_CSS
    else:
        content=published_fragment(d["page"])
        css=safe_css(d["page"].get("css",""))
    return render_document(d["name"],d["description"],content,
                           '<a href="index.html">首页</a>',theme,css)

def standalone_assets(root:Path,page_html:str):
    # Package only locally-managed media explicitly referenced in generated HTML.
    for match in set(re.findall(r"media/([a-f0-9]{32}\.(?:png|svg))", page_html)):
        source=MEDIA/match
        if source.is_file():
            (root/"media").mkdir(exist_ok=True)
            shutil.copy2(source,root/"media"/match)

@app.get("/api/dcells/{ident}/source")
def source_index(ident:int):
    root=package_root(ident)
    files=[]
    for file in sorted(root.rglob("*")):
        if file.is_file():
            rel=file.relative_to(root).as_posix()
            files.append({"path":rel,"size":file.stat().st_size,
                          "editable":file.suffix.lower() in SOURCE_EDIT_EXT and file.stat().st_size<=SOURCE_EDIT_MAX})
    return {"files":files,"preview":f"/package/{ident}/index.html"}

@app.get("/api/dcells/{ident}/source/file")
def get_source_file(ident:int,path:str):
    root=package_root(ident)
    file=editable_path(root,path)
    if not file.is_file():raise HTTPException(404,"File not found")
    if file.stat().st_size>SOURCE_EDIT_MAX:raise HTTPException(413,"File too large to edit")
    try: value=file.read_text(encoding="utf-8")
    except UnicodeError:raise HTTPException(400,"Text file must use UTF-8")
    return {"path":path,"content":value}

@app.put("/api/dcells/{ident}/source/file")
def save_source_file(ident:int,path:str,item:SourceIn):
    root=package_root(ident)
    file=editable_path(root,path)
    # Do not allow growing a package beyond the ZIP import limits.
    encoded=item.content.encode("utf-8")
    if len(encoded)>SOURCE_EDIT_MAX:raise HTTPException(413,"Source file exceeds 1 MB")
    size=sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    count=sum(1 for f in root.rglob("*") if f.is_file())
    if size-(file.stat().st_size if file.exists() else 0)+len(encoded)>50*1024*1024:
        raise HTTPException(413,"Package exceeds 50 MB")
    if not file.exists() and count>=300:
        raise HTTPException(413,"Package exceeds 300 files")
    file.parent.mkdir(parents=True,exist_ok=True)
    temporary=file.with_name(file.name+".writing")
    temporary.write_bytes(encoded)
    temporary.replace(file)
    return {"ok":True,"path":path,"size":len(encoded)}

@app.get("/api/dcells/{ident}/generated-source")
def generated_source(ident:int):
    with connection() as db:
        d=one(db,"dcells",ident)
        theme=db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()[0]
    if d["mode"]=="package":
        raise HTTPException(409,"Use the source workspace file API")
    return {"path":"index.html","content":standalone_html(d,theme),"read_only":True}

@app.post("/api/dcells/{ident}/detach")
def detach_to_source(ident:int):
    with connection() as db:
        d=one(db,"dcells",ident)
        theme=db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()[0]
    if d["mode"]=="package":
        return {"ok":True,"mode":"package","preview":f"/package/{ident}/index.html"}
    rendered=standalone_html(d,theme)
    # Original editor/template data remains intact in DB for future reference.
    # Only the current dcell switches to independent source mode.
    stage=PACKAGES/(str(ident)+"-source-staging")
    shutil.rmtree(stage,ignore_errors=True)
    stage.mkdir(parents=True)
    css=re.search(r'<style>(.*?)</style>',rendered,re.S)
    if css:
        rendered=rendered[:css.start()]+'<link rel="stylesheet" href="style.css">'+rendered[css.end():]
        (stage/"style.css").write_text(css.group(1),encoding="utf-8")
    rendered=rendered.replace("</body>",'<script src="app.js"></script></body>')
    (stage/"app.js").write_text("// 自定义 JavaScript，保存后预览即可生效。\\n",encoding="utf-8")
    (stage/"index.html").write_text(rendered,encoding="utf-8")
    standalone_assets(stage,rendered)
    target=PACKAGES/str(ident)
    old=PACKAGES/(str(ident)+"-source-old")
    shutil.rmtree(old,ignore_errors=True)
    if target.exists():target.rename(old)
    stage.rename(target)
    shutil.rmtree(old,ignore_errors=True)
    with connection() as db:
        db.execute("UPDATE dcells SET mode='package' WHERE id=?",(ident,))
    return {"ok":True,"mode":"package","preview":f"/package/{ident}/index.html"}

@app.get("/api/dcells/{ident}/export")
def export_dcell(ident:int):
    with connection() as db:
        d=one(db,"dcells",ident)
        theme=db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()[0]
    if d["mode"]=="package":
        root=package_root(ident)
        payload=zip_package(root)
    else:
        page=standalone_html(d,theme)
        with io.BytesIO() as mem:
            with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as z:
                z.writestr("index.html",page)
                for filename in set(re.findall(r"media/([a-f0-9]{32}\.(?:png|svg))", page)):
                    asset=MEDIA/filename
                    if asset.is_file():z.write(asset,"media/"+filename)
            mem.seek(0)
            payload=io.BytesIO(mem.getvalue())
    return StreamingResponse(payload,media_type="application/zip",
        headers={"Content-Disposition":f'attachment; filename="nexvain-dcell-{ident}.zip"'})

@app.get("/package/{ident}/{path:path}")
def preview_package(ident:int,path:str):
    root=(PACKAGES/str(ident)).resolve()
    target=(root/path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(404,"Not found")
    return FileResponse(target,headers={"Content-Security-Policy":"sandbox allow-scripts; default-src 'self' data: blob:; connect-src 'none'; object-src 'none'"})

@app.post("/api/assets")
async def upload_asset(file: UploadFile = File(...)):
    """Only decoded and re-encoded image pixels are retained, dropping EXIF."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    payload = await file.read(10 * 1024 * 1024 + 1)
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(413,"File exceeds 10MB")
    try:
        image = Image.open(io.BytesIO(payload))
        image.verify()
        image = Image.open(io.BytesIO(payload))
        if image.width * image.height > 30_000_000:
            raise HTTPException(413,"Image exceeds 30MP")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2560, 2560))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "Not a supported image")
    name = uuid.uuid4().hex + ".png"
    image.save(MEDIA / name, format="PNG", optimize=True)
    return {"url": "/media/" + name, "name": name}

@app.post("/api/charts")
def create_chart(chart: ChartIn):
    """Generate a self-contained static SVG chart with no remote runtime."""
    if chart.kind not in ("bar","line"):
        raise HTTPException(400,"Supported chart types: bar, line")
    if len(chart.labels) != len(chart.values):
        raise HTTPException(400,"Number of labels and values must match")
    if not all(math.isfinite(n) for n in chart.values):
        raise HTTPException(400,"Values must be finite")
    labels=[html.escape(str(v)[:28],quote=True) for v in chart.labels]
    vals=chart.values
    maxval=max([0]+vals)
    minval=min([0]+vals)
    span=max(maxval-minval,1e-9)
    left,top,width,height=72,55,820,270
    base=top+height*(maxval/span)
    spacing=width/len(vals)
    parts=[
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 420" role="img">',
      '<rect width="960" height="420" rx="14" fill="#102b45"/>',
      '<text x="36" y="34" fill="#e6f5ff" font-size="22">'+html.escape(chart.title)+'</text>'
    ]
    for i in range(5):
        y=top+i*height/4
        label=maxval-i*span/4
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="910" y2="{y:.1f}" stroke="#31506b"/>')
        parts.append(f'<text x="65" y="{y+4:.1f}" text-anchor="end" fill="#a5c4d7" font-size="12">{label:.2g}</text>')
    points=[]
    for i,(label,val) in enumerate(zip(labels,vals)):
        x=left+(i+.5)*spacing
        y=top+(maxval-val)*height/span
        points.append((x,y))
        parts.append(f'<text x="{x:.1f}" y="360" text-anchor="middle" fill="#c9dce8" font-size="12">{label}</text>')
        if chart.kind=="bar":
            w=min(spacing*.65,72)
            parts.append(f'<rect x="{x-w/2:.1f}" y="{min(y,base):.1f}" width="{w:.1f}" height="{max(abs(y-base),1):.1f}" rx="3" fill="#38b6e9"/>')
    if chart.kind=="line":
        path=" ".join(("M" if i==0 else "L")+f"{x:.1f},{y:.1f}" for i,(x,y) in enumerate(points))
        parts.append(f'<path d="{path}" fill="none" stroke="#38b6e9" stroke-width="4"/>')
        for x,y in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#7de0ff"/>')
    parts.append("</svg>")
    name=uuid.uuid4().hex+".svg"
    (MEDIA/name).write_text("".join(parts),encoding="utf-8")
    return {"url":"/media/"+name,"name":name}

@app.get("/media/{filename}")
def media(filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.(png|svg)",filename):
        raise HTTPException(404,"Not found")
    path=MEDIA/filename
    if not path.is_file(): raise HTTPException(404,"Not found")
    return FileResponse(path,media_type="image/svg+xml" if filename.endswith(".svg") else "image/png")

@app.get("/api/settings")
def settings():
    with connection() as db:
        return {"theme":db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()[0]}

@app.put("/api/settings")
def save_settings(item: SettingsIn):
    if item.theme not in ("blue","dark","light"):
        raise HTTPException(400,"Invalid theme")
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('theme',?)",(item.theme,))
    return {"theme":item.theme}

# Page designs persist as JSON {html, css} produced by GrapesJS.
# Sanitization here is deliberately restrictive for static publishing.
# Untrusted HTML is NOT published directly; use trusted editors only and
# do not expose admin endpoints without authentication.
def fragment(page):
    import bleach
    raw = page.get("html","") if isinstance(page,dict) else ""
    return bleach.clean(raw,tags=[
        "div","section","article","header","footer","main","p","b","strong",
        "em","i","span","h1","h2","h3","h4","ul","ol","li",
        "table","thead","tbody","tr","th","td","img","br","hr"
    ],attributes={"*":["class","title"],"img":["src","alt","width","height"]},
    protocols=["https","http"],strip=True)

def published_fragment(page):
    """Reference the exported local media, not the admin-only /media endpoint."""
    value = fragment(page)
    return re.sub(
        r'(?<=src=")/media/([a-f0-9]{32}\.(?:png|svg))(?=")',
        r'media/\1',
        value
    )

THEMES = {
"blue": ("#081a2c","#14334f","#dcefff","#3dbde9"),
"dark": ("#171b24","#2b3445","#edf2f7","#b3c5e0"),
"light": ("#f0f4f8","#ffffff","#1d3045","#1873ac")
}
BASE_CSS = """
*{box-sizing:border-box}
html{width:1920px;height:1080px;margin:0}
body{width:1920px;height:1080px;margin:0;font-family:Inter,'Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text)}
.shell{display:flex;width:1920px;height:1080px;overflow:hidden}
.nav{width:300px;height:1080px;flex:0 0 300px;overflow-y:auto;background:var(--panel);padding:24px 15px}
.nav h2{font-size:22px;margin:0 0 28px}
.nav a{display:block;color:var(--text);padding:14px 16px;text-decoration:none;border-radius:7px;font-size:17px}
.nav a:hover,.nav a.current{background:var(--accent);color:#061422}
.nav .sub{padding-left:27px;font-size:16px}
.nav .group{margin-top:14px;font-weight:700}
.stage{width:1620px;height:1080px;flex:0 0 1620px;min-width:0;overflow-y:auto;overflow-x:hidden;padding:38px 48px}
h1{font-size:30px}.intro{opacity:.75}.content{margin-top:24px}
.panel{padding:26px;background:var(--panel);border-radius:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:15px}
.card{padding:24px;background:var(--panel);border-radius:12px;text-decoration:none;color:var(--text)}
.card:hover{outline:1px solid var(--accent)}
img{max-width:100%;height:auto}
"""

def safe_css(value):
    import tinycss2
    allowed = {"color","background","background-color","font-size","font-weight","font-family","line-height","text-align","margin","padding","width","height","max-width","min-height","display","flex","flex-direction","gap","align-items","justify-content","grid-template-columns","border","border-radius","box-shadow","opacity"}
    rules = []
    for rule in tinycss2.parse_stylesheet(value or "", skip_whitespace=True, skip_comments=True):
        if rule.type != "qualified-rule": continue
        selector = tinycss2.serialize(rule.prelude).strip()
        if not re.fullmatch(r"[a-zA-Z0-9_ .,#>:+-]{1,180}", selector): continue
        props = []
        for item in tinycss2.parse_declaration_list(rule.content, skip_comments=True, skip_whitespace=True):
            if item.type != "declaration" or item.lower_name not in allowed: continue
            val = tinycss2.serialize(item.value).strip()
            if len(val)>220 or any(x in val.lower() for x in ("url(", "expression(", "@import", "<", ">", "{", "}", ";", "\\")): continue
            props.append(item.lower_name + ":" + val)
        if props: rules.append(selector + "{" + ";".join(props) + "}")
    return chr(10).join(rules)

def render_document(title, intro, content, nav, theme, custom_css=""):
    bg,panel,fg,accent=THEMES[theme]
    style=f":root{{--bg:{bg};--panel:{panel};--text:{fg};--accent:{accent}}}"+BASE_CSS+custom_css
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(title)} · NexVain</title><style>{style}</style></head>
    <body><div class="shell"><aside class="nav"><h2>NexVain</h2>{nav}</aside>
    <main class="stage"><h1>{html.escape(title)}</h1>
    <p class="intro">{html.escape(intro)}</p><section class="content">{content}</section>
    </main></div>
    </body></html>"""

@app.get("/api/publish/check")
def check_current_publish():
    return publish_checks.check(PUBLIC)

@app.get("/api/assets/library")
def assets_library():
    return [{"url":"/media/"+p.name,"name":p.name,"bytes":p.stat().st_size}
            for p in sorted(MEDIA.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True)
            if p.is_file() and re.fullmatch(r"[a-f0-9]{32}\.(?:png|svg)",p.name)][:300]

@app.get("/api/publish/status")
def publish_status():
    with connection() as db:
        draft=int((db.execute("SELECT value FROM settings WHERE key='draft_revision'").fetchone() or ["0"])[0])
        published=int((db.execute("SELECT value FROM settings WHERE key='published_revision'").fetchone() or ["-1"])[0])
        unlinked=db.execute("""SELECT COUNT(*) FROM dcells d WHERE NOT EXISTS
            (SELECT 1 FROM topic_dcells td WHERE td.dcell_id=d.id)""").fetchone()[0]
        return {"draft_revision":draft,"published_revision":published,
                "needs_publish":draft!=published or not (PUBLIC/"index.html").exists(),
                "unlinked_dcells":unlinked}

@app.post("/api/publish")
def publish():
    # Atomic swap is intentionally limited to a local temp directory; keep
    # previous published directory if generation raises an exception.
    with connection() as db:
        topics=[parse_row(r) for r in db.execute("SELECT * FROM topics ORDER BY position,id")]
        dcells=[parse_row(r) for r in db.execute("SELECT * FROM dcells ORDER BY id")]
        links=[dict(r) for r in db.execute("SELECT * FROM topic_dcells ORDER BY position,dcell_id")]
        theme=db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()[0]
        draft_revision=int((db.execute("SELECT value FROM settings WHERE key='draft_revision'").fetchone() or ["0"])[0])
    by_id={x["id"]:x for x in dcells}
    nav=['<a href="index.html">专题库首页</a>']
    for topic in topics:
        nav.append(f'<a class="group" href="topic-{topic["id"]}.html">{html.escape(topic["name"])}</a>')
        for relation in links:
            if relation["topic_id"]==topic["id"] and relation["dcell_id"] in by_id:
                d=by_id[relation["dcell_id"]]
                alias=relation["alias"] or d["name"]
                nav.append(f'<a class="sub" href="dcell-{d["id"]}.html">{html.escape(alias)}</a>')
    nav_html="".join(nav)
    staging=ROOT / ".published-staging"
    if staging.exists(): shutil.rmtree(staging)
    staging.mkdir()
    for d in dcells:
        if d.get("mode")=="package":
            source=PACKAGES/str(d["id"])
            if not (source/"index.html").is_file():
                raise HTTPException(409,"No package for dcell "+str(d["id"]))
            destination=staging/"custom"/("dcell-"+str(d["id"]))
            shutil.copytree(source,destination)
            # Repair previously detached template pages whose media subdirectory
            # was absent due to the old managed-asset filename regex.
            for page_file in destination.rglob("*.html"):
                page_html=page_file.read_text(encoding="utf-8")
                for match in re.findall(r"""(?:src|href)=["']media/([a-f0-9]{32}\.(?:png|svg))""",page_html):
                    local=page_file.parent/"media"/match
                    managed=MEDIA/match
                    if not local.exists() and managed.is_file():
                        local.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(managed,local)

    # Export only re-encoded managed assets, never upload originals or DB files.
    shutil.copytree(MEDIA, staging / "media")
    try:
        cards="".join(f'<a class="card" href="topic-{t["id"]}.html"><h2>{html.escape(t["name"])}</h2><p>{html.escape(t["description"])}</p></a>' for t in topics)
        (staging/"index.html").write_text(render_document("专题库首页","农业专题数据资源展示",f'<div class="cards">{cards}</div>',nav_html,theme),encoding="utf-8")
        for t in topics:
            owned=[r for r in links if r["topic_id"]==t["id"] and r["dcell_id"] in by_id]
            cards="".join(f'<a class="card" href="dcell-{r["dcell_id"]}.html">{html.escape(r["alias"] or by_id[r["dcell_id"]]["name"])}</a>' for r in owned)
            content=published_fragment(t["page"])+f'<div class="cards">{cards}</div>'
            (staging/f'topic-{t["id"]}.html').write_text(render_document(t["name"],t["description"],content,nav_html,theme,safe_css(t["page"].get("css",""))),encoding="utf-8")
        for d in dcells:
            if d.get("mode")=="package":
                content=('<iframe title="'+html.escape(d["name"],quote=True)+'" src="custom/dcell-'+str(d["id"])+'/index.html" sandbox="allow-scripts" referrerpolicy="no-referrer" style="width:100%;height:calc(100vh - 180px);border:0"></iframe>')
            elif d.get("mode")=="template":
                tpl=d["template"] if d["template"] in TEMPLATES else "overview"
                content=render_template(d["name"],d["description"],tpl,d.get("content",{}))
            else:
                content=published_fragment(d["page"]) or '<div class="panel"><p>'+html.escape(d["description"])+'</p></div>'
            style=TEMPLATE_CSS if d.get("mode")=="template" else safe_css(d["page"].get("css",""))
            (staging/f'dcell-{d["id"]}.html').write_text(render_document(d["name"],d["description"],content,nav_html,theme,style),encoding="utf-8")
        report=publish_checks.check(staging)
        if not report["ok"]:
            raise HTTPException(409,detail={"message":"Publish resource validation failed","report":report})
        old=ROOT/".published-old"
        if old.exists(): shutil.rmtree(old)
        if PUBLIC.exists(): PUBLIC.rename(old)
        staging.rename(PUBLIC)
        if old.exists(): shutil.rmtree(old)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('published_revision',?)",(str(draft_revision),))
    return {"ok":True,"topics":len(topics),"dcells":len(dcells),"url":"/","published_revision":draft_revision,"validation":report}

@app.get("/admin")
def admin():
    return FileResponse(ASSETS/"admin.html")

app.mount("/web",StaticFiles(directory=ASSETS),name="web")
app.mount("/",StaticFiles(directory=PUBLIC,html=True),name="published")

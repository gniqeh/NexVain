from __future__ import annotations
import html
import json
import os
import re
import shutil
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("NEXVAIN_DATA", str(ROOT / "data")))
DB = DATA / "nexvain.sqlite3"
PUBLIC = ROOT / "published"
ASSETS = ROOT / "web"
DATA.mkdir(parents=True, exist_ok=True)
PUBLIC.mkdir(exist_ok=True)
app = FastAPI(title="NexVain", version="0.1.0")

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

class RelationIn(BaseModel):
    dcell_id: int
    alias: str = ""
    position: int = 0

class SettingsIn(BaseModel):
    theme: str

def parse_row(row):
    obj = dict(row)
    if "page" in obj:
        obj["page"] = json.loads(obj["page"])
    return obj

def one(db, table, ident):
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (ident,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{table} not found")
    return parse_row(row)

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
        cur=db.execute("INSERT INTO dcells(name,description,template,page) VALUES (?,?,?,?)",
            (item.name,item.description,item.template,json.dumps(item.page,ensure_ascii=False)))
        return one(db,"dcells",cur.lastrowid)

@app.put("/api/dcells/{ident}")
def update_dcell(ident: int,item: DcellIn):
    with connection() as db:
        one(db,"dcells",ident)
        db.execute("UPDATE dcells SET name=?,description=?,template=?,page=? WHERE id=?",
            (item.name,item.description,item.template,json.dumps(item.page,ensure_ascii=False),ident))
        return one(db,"dcells",ident)

@app.delete("/api/dcells/{ident}")
def delete_dcell(ident: int):
    with connection() as db:
        one(db,"dcells",ident)
        db.execute("DELETE FROM dcells WHERE id=?",(ident,))
        return {"ok":True}

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

THEMES = {
"blue": ("#081a2c","#14334f","#dcefff","#3dbde9"),
"dark": ("#171b24","#2b3445","#edf2f7","#b3c5e0"),
"light": ("#f0f4f8","#ffffff","#1d3045","#1873ac")
}
BASE_CSS = """
*{box-sizing:border-box}body{margin:0;font-family:Inter,'Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text)}
.shell{display:flex;min-height:100vh}.nav{width:260px;flex-shrink:0;background:var(--panel);padding:24px 15px}
.nav h2{font-size:22px;margin:0 0 28px}.nav a{display:block;color:var(--text);padding:10px 12px;text-decoration:none;border-radius:7px}
.nav a:hover,.nav a.current{background:var(--accent);color:#061422}.nav .sub{padding-left:27px;font-size:14px}
.nav .group{margin-top:14px;font-weight:700}.stage{flex:1;min-width:0;padding:32px}
h1{font-size:30px}.intro{opacity:.75}.content{margin-top:24px}.panel{padding:26px;background:var(--panel);border-radius:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:15px}
.card{padding:24px;background:var(--panel);border-radius:12px;text-decoration:none;color:var(--text)}
.card:hover{outline:1px solid var(--accent)}img{max-width:100%;height:auto}
"""

def safe_css(value):
    import tinycss2
    allowed = {"color","background","background-color","font-size","font-weight","font-family","line-height","text-align","margin","padding","width","height","max-width","min-height","display","flex","flex-direction","gap","align-items","justify-content","grid-template-columns","border","border-radius","box-shadow","opacity"}
    rules = []
    for rule in tinycss2.parse_stylesheet(value or "", skip_whitespace=True, skip_comments=True):
        if rule.type != "qualified-rule": continue
        selector = tinycss2.serialize(rule.prelude).strip()
        if not re.fullmatch(r"[\\w .,#>:+-]{1,180}", selector): continue
        props = []
        for item in tinycss2.parse_declaration_list(rule.content, skip_comments=True, skip_whitespace=True):
            if item.type != "declaration" or item.lower_name not in allowed: continue
            val = tinycss2.serialize(item.value).strip()
            if len(val)>220 or re.search(r"url\\s*\\(|expression\\s*\\(|[{};<>@]|\\\\", val, re.I): continue
            props.append(item.lower_name + ":" + val)
        if props: rules.append(selector + "{" + ";".join(props) + "}")
    return "\\n".join(rules)

def render_document(title, intro, content, nav, theme, custom_css=""):
    bg,panel,fg,accent=THEMES[theme]
    style=f":root{{--bg:{bg};--panel:{panel};--text:{fg};--accent:{accent}}}"+BASE_CSS+custom_css
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(title)} · NexVain</title><style>{style}</style></head>
    <body><div class="shell"><aside class="nav"><h2>NexVain</h2>{nav}</aside>
    <main class="stage"><h1>{html.escape(title)}</h1>
    <p class="intro">{html.escape(intro)}</p><section class="content">{content}</section>
    </main></div></body></html>"""

@app.post("/api/publish")
def publish():
    # Atomic swap is intentionally limited to a local temp directory; keep
    # previous published directory if generation raises an exception.
    with connection() as db:
        topics=[parse_row(r) for r in db.execute("SELECT * FROM topics ORDER BY position,id")]
        dcells=[parse_row(r) for r in db.execute("SELECT * FROM dcells ORDER BY id")]
        links=[dict(r) for r in db.execute("SELECT * FROM topic_dcells ORDER BY position,dcell_id")]
        theme=db.execute("SELECT value FROM settings WHERE key='theme'").fetchone()[0]
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
    try:
        cards="".join(f'<a class="card" href="topic-{t["id"]}.html"><h2>{html.escape(t["name"])}</h2><p>{html.escape(t["description"])}</p></a>' for t in topics)
        (staging/"index.html").write_text(render_document("专题库首页","农业专题数据资源展示",f'<div class="cards">{cards}</div>',nav_html,theme),encoding="utf-8")
        for t in topics:
            owned=[r for r in links if r["topic_id"]==t["id"] and r["dcell_id"] in by_id]
            cards="".join(f'<a class="card" href="dcell-{r["dcell_id"]}.html">{html.escape(r["alias"] or by_id[r["dcell_id"]]["name"])}</a>' for r in owned)
            content=fragment(t["page"])+f'<div class="cards">{cards}</div>'
            (staging/f'topic-{t["id"]}.html').write_text(render_document(t["name"],t["description"],content,nav_html,theme,safe_css(t["page"].get("css",""))),encoding="utf-8")
        for d in dcells:
            content=fragment(d["page"]) or '<div class="panel"><p>'+html.escape(d["description"])+'</p></div>'
            (staging/f'dcell-{d["id"]}.html').write_text(render_document(d["name"],d["description"],content,nav_html,theme,safe_css(d["page"].get("css",""))),encoding="utf-8")
        old=ROOT/".published-old"
        if old.exists(): shutil.rmtree(old)
        if PUBLIC.exists(): PUBLIC.rename(old)
        staging.rename(PUBLIC)
        if old.exists(): shutil.rmtree(old)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    return {"ok":True,"topics":len(topics),"dcells":len(dcells),"url":"/"}

@app.get("/admin")
def admin():
    return FileResponse(ASSETS/"admin.html")

app.mount("/web",StaticFiles(directory=ASSETS),name="web")
app.mount("/",StaticFiles(directory=PUBLIC,html=True),name="published")

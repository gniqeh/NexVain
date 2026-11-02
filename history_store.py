"""Local snapshot history for the single-admin NexVain installation.

A checkpoint includes SQLite, imported page packages and current published site.
Managed media is append-only and shared across revisions; it is not deleted on restore.
"""
from __future__ import annotations
import io
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

LOCK=threading.RLock()
MAX_SNAPSHOTS=15
MAX_MEMBER=1024*1024*100

def paths(data:Path,public:Path):
    history=data/"history"
    history.mkdir(parents=True,exist_ok=True)
    return history,data/"nexvain.sqlite3",data/"packages",public

def audit(data:Path,event:dict):
    directory=data/"history"
    directory.mkdir(parents=True,exist_ok=True)
    line={"at":datetime.now(timezone.utc).isoformat(timespec="seconds"),**event}
    with LOCK:
        with (directory/"events.jsonl").open("a",encoding="utf-8") as f:
            f.write(json.dumps(line,ensure_ascii=False)+"\n")

def recent(data:Path,limit:int=50):
    file=data/"history"/"events.jsonl"
    if not file.exists():return []
    # bounded by the number of logged events, not arbitrary file contents
    lines=file.read_text(encoding="utf-8").splitlines()[-limit:]
    output=[]
    for line in reversed(lines):
        try:output.append(json.loads(line))
        except json.JSONDecodeError:continue
    return output

def checkpoints(data:Path):
    root=data/"history"
    return [{"id":p.stem,"bytes":p.stat().st_size,"time":p.stat().st_mtime}
            for p in sorted(root.glob("*.zip"),key=lambda x:x.stat().st_mtime,reverse=True)
            if p.stem.isalnum() or "-" in p.stem]

def create(data:Path,public:Path,reason:str)->str:
    with LOCK:
        directory,db,packages,published=paths(data,public)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ident=stamp+"-"+uuid.uuid4().hex[:8]
        target=directory/(ident+".zip")
        temporary=target.with_suffix(".tmp")
        db_copy=directory/(ident+".sqlite3.tmp")
        try:
            source=sqlite3.connect(db)
            dest=sqlite3.connect(db_copy)
            try:source.backup(dest)
            finally:dest.close();source.close()
            with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
                z.write(db_copy,"database.sqlite3")
                for prefix,root in (("packages",packages),("published",published)):
                    if not root.exists():continue
                    for file in root.rglob("*"):
                        if file.is_symlink():raise ValueError("Snapshot cannot include symlinks")
                        if file.is_file():
                            z.write(file,prefix+"/"+file.relative_to(root).as_posix())
            temporary.replace(target)
            snapshots=sorted(directory.glob("*.zip"),key=lambda p:p.stat().st_mtime,reverse=True)
            for old in snapshots[MAX_SNAPSHOTS:]:old.unlink()
        finally:
            db_copy.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
        audit(data,{"action":"checkpoint","snapshot":ident,"detail":reason})
        return ident

def restore(data:Path,public:Path,ident:str):
    with LOCK:
        directory,db,packages,published=paths(data,public)
        if not ident or not all(c.isalnum() or c=="-" for c in ident):
            raise ValueError("Invalid checkpoint id")
        path=directory/(ident+".zip")
        if not path.is_file():raise FileNotFoundError("Checkpoint not found")
        # Validate all entries before modifying live data.
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            stage=Path(temp)
            with zipfile.ZipFile(path) as z:
                members=z.infolist()
                if not any(i.filename=="database.sqlite3" for i in members):
                    raise ValueError("Missing database backup")
                for member in members:
                    rel=Path(member.filename)
                    if member.filename.startswith("/") or "\\" in member.filename or ".." in rel.parts or member.file_size>MAX_MEMBER or (rel.parts[0] not in ("packages","published","database.sqlite3")):
                        raise ValueError("Unsafe snapshot member")
                    if member.is_dir():continue
                    out=stage/rel
                    out.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(member) as src,out.open("wb") as dst:
                        shutil.copyfileobj(src,dst)
            src=sqlite3.connect(stage/"database.sqlite3")
            try:
                check=src.execute("PRAGMA integrity_check").fetchone()
                if check[0]!="ok":raise ValueError("Invalid SQLite backup")
                dest=sqlite3.connect(db)
                try:src.backup(dest)
                finally:dest.close()
            finally:src.close()
            for name,target in (("packages",packages),("published",published)):
                staged=stage/name
                if not staged.exists():staged.mkdir()
                previous=target.with_name(target.name+"-restore-old")
                if previous.exists():shutil.rmtree(previous)
                if target.exists():target.rename(previous)
                shutil.copytree(staged,target)
                if previous.exists():shutil.rmtree(previous)
        audit(data,{"action":"restore","snapshot":ident,"detail":"Restored all tracked content"})

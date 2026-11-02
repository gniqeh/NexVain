"""Check locally referenced resources before swapping the published site."""
from __future__ import annotations
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote,urlsplit

class References(HTMLParser):
    def __init__(self):
        super().__init__();self.refs=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        for field in (("src",) if tag in ("img","script","iframe","video","audio","source") else ("href",) if tag=="link" else ()):
            if a.get(field):self.refs.append((tag,a[field]))

def check(root:Path):
    root=root.resolve(); errors=[]; checked=0
    pages=list(root.rglob("*.html"))
    for file in pages:
        parser=References()
        try:parser.feed(file.read_text(encoding="utf-8"))
        except (OSError,UnicodeError,ValueError) as exc:
            errors.append({"file":file.relative_to(root).as_posix(),"error":str(exc)});continue
        refs=parser.refs
        # Relative CSS image/font dependencies and local @import references.
        for url in re.findall(r"""url\(\s*['"]?([^)'"]+)""",file.read_text(encoding="utf-8")):
            refs.append(("style",url))
        for tag,url in refs:
            if url.startswith(("#","data:","blob:","mailto:","javascript:","//")):continue
            parsed=urlsplit(url)
            if parsed.scheme or parsed.netloc:continue
            path=unquote(parsed.path)
            if not path:continue
            relative=Path(path.lstrip("/")) if path.startswith("/") else (file.parent/root).joinpath(path) if False else file.parent.joinpath(path).relative_to(root)
            candidate=(root/relative).resolve()
            checked+=1
            if not candidate.is_relative_to(root) or not candidate.is_file():
                errors.append({"file":file.relative_to(root).as_posix(),"reference":url,"error":"Missing or invalid local resource"})
    for file in root.rglob("*.css"):
        try:css=file.read_text(encoding="utf-8")
        except (OSError,UnicodeError):continue
        refs=re.findall(r"""url\(\s*['"]?([^)'"]+)""",css)
        refs+=re.findall(r"""@import\s+['"]([^'"]+)""",css)
        for url in refs:
            if url.startswith(("#","data:","blob:","//")):continue
            parsed=urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path:continue
            candidate=(root/parsed.path.lstrip("/")).resolve() if parsed.path.startswith("/") else (file.parent/parsed.path).resolve()
            checked+=1
            if not candidate.is_relative_to(root) or not candidate.is_file():
                errors.append({"file":file.relative_to(root).as_posix(),"reference":url,"error":"Missing CSS resource"})
    return {"ok":not errors,"pages":len(pages),"checked_references":checked,"errors":errors[:100]}

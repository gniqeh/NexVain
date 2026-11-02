"""Validate the standalone admin JavaScript syntax using Node when available."""
from pathlib import Path
import shutil
import subprocess
import tempfile

source=(Path(__file__).resolve().parent.parent/"web"/"admin.html").read_text(encoding="utf-8")
start=source.rfind("<script>")+len("<script>")
end=source.find("</script>",start)
assert start>=len("<script>") and end>start, "Missing inline admin JS"
node=shutil.which("node")
if not node:
    raise SystemExit("Node.js is needed for syntax validation")
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/"admin.js"
    path.write_text(source[start:end],encoding="utf-8")
    subprocess.run([node,"--check",str(path)],check=True)
print("Admin JavaScript syntax OK")

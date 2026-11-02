"""Chromium visual smoke tests at 1920x1080 with screenshots.

Run: pip install playwright; python -m playwright install chromium;
     python scripts/visual_smoke.py
"""
from __future__ import annotations
import os
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="nexvain-visual-") as temp:
    os.environ["NEXVAIN_DATA"]=str(Path(temp)/"data")
    os.environ["NEXVAIN_DEV_MODE"]="1"

    from fastapi.testclient import TestClient
    from app import app,PUBLIC
    client=TestClient(app)

    topic=client.post("/api/topics",json={"name":"黑龙江寒地农业遥感专题","description":"1920 × 1080 大屏展示验收"}).json()
    dcell=client.post("/api/dcells",json={
        "name":"玉米长势与图像数据集","description":"农业专题数据",
        "mode":"template","template":"metrics",
        "content":{"summary":"用于检验核心指标、分类柱形图和说明文本在大屏上的可读性。",
          "metrics":[{"label":"图像数量","value":"18,240","note":"张"},
                    {"label":"覆盖地区","value":"黑龙江省","note":"省域"},
                    {"label":"采集年份","value":"2026","note":"年"}],
          "chart":[{"label":"玉米","value":30},{"label":"水稻","value":42},{"label":"大豆","value":28}],
          "sections":[{"title":"采集方法","text":"无人机与地面采样协同进行。"}]}
    }).json()
    linked=client.put(f"/api/topics/{topic['id']}/dcells",json=[{"dcell_id":dcell["id"]}])
    assert linked.status_code==200,linked.text
    result=client.post("/api/publish")
    assert result.status_code==200,result.text
    assert result.json()["validation"]["ok"]

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self,*args):
            pass

    server=ThreadingHTTPServer(("127.0.0.1",0),partial(QuietHandler,directory=str(PUBLIC)))
    server_thread=threading.Thread(target=server.serve_forever,daemon=True)
    server_thread.start()
    base=f"http://127.0.0.1:{server.server_address[1]}"
    out=Path("visual_artifacts")
    out.mkdir(parents=True,exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=["--disable-gpu","--no-sandbox"])
            page=browser.new_page(viewport={"width":1920,"height":1080},device_scale_factor=1)
            for filename,title in [("index.html","专题库首页"),
                                    (f"topic-{topic['id']}.html","黑龙江寒地农业遥感专题"),
                                    (f"dcell-{dcell['id']}.html","玉米长势与图像数据集")]:
                page.goto(base+"/"+filename,wait_until="networkidle")
                assert page.get_by_role("heading",name=title).count()>0,filename
                assert page.locator(".nav").is_visible(),filename
                assert page.locator("#nv-full").count()==0,filename
                assert page.locator("#nv-play").count()==0,filename
                canvas=page.locator(".shell").bounding_box()
                assert round(canvas["width"])==page.viewport_size["width"] and round(canvas["height"])==page.viewport_size["height"],canvas
                dimensions=page.evaluate("""() => ({
                   scrollWidth:document.documentElement.scrollWidth,
                   viewportWidth:window.innerWidth,
                   scrollHeight:document.documentElement.scrollHeight,
                   viewportHeight:window.innerHeight
                })""")
                assert dimensions["scrollWidth"]<=1920 and dimensions["scrollHeight"]<=1080, f"{filename}: viewport overflow: {dimensions}"
                screenshot=out/(filename.replace(".html","")+".png")
                page.screenshot(path=str(screenshot),full_page=True)
                print(filename,dimensions,"screenshot:",screenshot)
            page.goto(base+f"/dcell-{dcell['id']}.html")
            assert page.locator(".dcell-metric").count()==3
            assert page.locator(".dcell-bar").count()==3
            assert page.locator("#nv-play").count()==0
            page.set_viewport_size({"width":1366,"height":768})
            page.reload(wait_until="networkidle")
            canvas=page.locator(".shell").bounding_box()
            assert round(canvas["width"])==page.viewport_size["width"] and round(canvas["height"])==page.viewport_size["height"],canvas
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth && document.documentElement.scrollHeight<=innerHeight")
            page.screenshot(path=str(out/"dcell-1366.png"))
            browser.close()
        print("1920x1080 browser smoke check passed")
    finally:
        server.shutdown()
        server.server_close()

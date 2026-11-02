import os
from pathlib import Path
import base64

os.environ["NEXVAIN_DATA"] = "/tmp/nexvain-test-data"
os.environ["NEXVAIN_ADMIN_PASSWORD"] = "test-only-pass"
from fastapi.testclient import TestClient
from app import app

client = TestClient(app,headers={"Authorization":"Basic "+base64.b64encode(b"admin:test-only-pass").decode(),"X-NexVain-Confirm":"test-only-pass"})

def test_topic_dcell_publish():
    t = client.post("/api/topics", json={"name":"病害专题"}).json()
    d = client.post("/api/dcells", json={"name":"玉米病害","page":{"html":"<h2>成果概况</h2><script>alert(1)</script>"}}).json()
    assert client.put(f"/api/topics/{t['id']}/dcells",json=[{"dcell_id":d["id"]}]).status_code == 200
    assert len(client.get(f"/api/dcells/{d['id']}/topics").json()) == 1
    assert client.post("/api/publish").status_code == 200
    html = client.get(f"/dcell-{d['id']}.html").text
    assert "成果概况" in html
    assert "<script>alert(1)</script>" not in html

def test_chart_creation_and_static_export():
    topic = client.post("/api/topics", json={"name":"示范专题"}).json()
    chart = client.post("/api/charts", json={
        "title":"结构统计", "kind":"bar", "labels":["玉米","水稻"],"values":[10,20]
    })
    assert chart.status_code == 200
    url=chart.json()["url"]
    assert client.get(url).status_code==200
    dcell=client.post("/api/dcells", json={"name":"示范数据集",
        "page":{"html":'<div><img src="'+url+'" alt="统计图"></div>'}}).json()
    assert client.put(f"/api/topics/{topic['id']}/dcells",json=[{"dcell_id":dcell["id"]}]).status_code==200
    assert client.post("/api/publish").status_code==200
    assert url.lstrip("/") in client.get(f"/dcell-{dcell['id']}.html").text
    assert client.get(url).status_code==200

def test_image_upload_removes_exif():
    import io
    from PIL import Image
    image=Image.new("RGB",(10,10),(150,120,80))
    buff=io.BytesIO()
    image.save(buff,format="JPEG")
    r=client.post("/api/assets",files={"file":("input.jpg",buff.getvalue(),"image/jpeg")})
    assert r.status_code==200
    assert r.json()["url"].endswith(".png")
    assert client.get(r.json()["url"]).status_code==200

def test_custom_package_publish_and_traversal_rejection():
    import io, zipfile
    d=client.post("/api/dcells",json={"name":"外部设计","mode":"package"}).json()
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("index.html","<html><body><h1>自制页面</h1><script src='js/app.js'></script></body></html>")
        z.writestr("js/app.js","document.body.dataset.ok='1'")
    result=client.post(f"/api/dcells/{d['id']}/package",files={"file":("site.zip",archive.getvalue(),"application/zip")})
    assert result.status_code==200,result.text
    assert client.get(f"/package/{d['id']}/index.html").status_code==200
    assert client.post("/api/publish").status_code==200
    outer=client.get(f"/dcell-{d['id']}.html").text
    assert 'sandbox="allow-scripts"' in outer
    assert f"custom/dcell-{d['id']}/index.html" in outer
    assert "自制页面" in client.get(f"/custom/dcell-{d['id']}/index.html").text
    malicious=io.BytesIO()
    with zipfile.ZipFile(malicious,"w") as z:
        z.writestr("index.html","hello")
        z.writestr("../escape.js","bad")
    bad=client.post(f"/api/dcells/{d['id']}/package",files={"file":("bad.zip",malicious.getvalue(),"application/zip")})
    assert bad.status_code==400


def test_password_protection(monkeypatch):
    import base64
    monkeypatch.setenv("NEXVAIN_ADMIN_PASSWORD","secret-test")
    assert client.get("/api/topics").status_code==401
    hdr={"Authorization":"Basic "+base64.b64encode(b"admin:secret-test").decode()}
    assert client.get("/api/topics",headers=hdr).status_code==200
    monkeypatch.delenv("NEXVAIN_ADMIN_PASSWORD")

def test_directory_import(monkeypatch,tmp_path):
    root=tmp_path/"sources"
    page=root/"sample"
    page.mkdir(parents=True)
    (page/"index.html").write_text("<h1>服务器目录页面</h1>",encoding="utf-8")
    (page/"main.js").write_text("document.body.dataset.ready='yes'",encoding="utf-8")
    monkeypatch.setenv("NEXVAIN_IMPORT_ROOT",str(root))
    d=client.post("/api/dcells",json={"name":"目录导入"}).json()
    invalid=client.post(f"/api/dcells/{d['id']}/import-directory",json={"path":"../outside"})
    assert invalid.status_code==400
    valid=client.post(f"/api/dcells/{d['id']}/import-directory",json={"path":"sample"})
    assert valid.status_code==200,valid.text
    assert client.post("/api/publish").status_code==200
    assert "服务器目录页面" in client.get(f"/custom/dcell-{d['id']}/index.html").text

def test_nav_requires_relation_and_republish():
    d=client.post("/api/dcells",json={"name":"导航更新回归用例"}).json()
    t=client.post("/api/topics",json={"name":"导航测试专题"}).json()
    status=client.get("/api/publish/status").json()
    assert status["needs_publish"] is True
    assert status["unlinked_dcells"]>=1
    assert client.post("/api/publish").status_code==200
    assert "导航更新回归用例" not in client.get("/").text
    assert client.put(f"/api/topics/{t['id']}/dcells",json=[{"dcell_id":d["id"]}]).status_code==200
    assert client.get("/api/publish/status").json()["needs_publish"] is True
    assert client.post("/api/publish").status_code==200
    page=client.get("/").text
    assert "导航更新回归用例" in page
    assert f'dcell-{d["id"]}.html' in page
    assert client.get("/").headers["cache-control"]=="no-store"
    assert client.get("/api/publish/status").json()["needs_publish"] is False

def test_uploaded_image_is_accessible_and_published_without_backend():
    import io
    from PIL import Image
    image=Image.new("RGB",(16,16),"blue")
    data=io.BytesIO()
    image.save(data,format="PNG")
    response=client.post("/api/assets",files={"file":("sample.png",data.getvalue(),"image/png")})
    assert response.status_code==200,response.text
    source_url=response.json()["url"]
    preview=client.get(source_url)
    assert preview.status_code==200,preview.text
    assert preview.headers["content-type"].startswith("image/png")
    dcell=client.post("/api/dcells",json={
        "name":"图片发布验证",
        "page":{"html":'<div><img src="'+source_url+'" alt="图片验证"></div>'}
    }).json()
    assert client.post("/api/publish").status_code==200
    published=client.get(f"/dcell-{dcell['id']}.html").text
    assert 'src="media/' in published
    assert 'src="/media/' not in published
    from app import PUBLIC
    assert (PUBLIC / "media" / response.json()["name"]).is_file()

def test_data_driven_templates_clone_preview_and_publish():
    listed=client.get("/api/templates")
    assert listed.status_code==200
    assert len(listed.json()["templates"])>=4
    d=client.post("/api/dcells",json={
        "name":"寒地作物图像", "description":"科研数据示例",
        "mode":"template","template":"overview",
        "content":{
            "summary":"黑龙江农业数据展示",
            "metrics":[{"label":"图片数量","value":"12800","note":"张"}],
            "chart":[{"label":"玉米","value":30},{"label":"大豆","value":55}],
            "sections":[{"title":"采集方法","text":"无人机与地面采样"}],
            "images":[]
        }
    }).json()
    assert d["mode"]=="template"
    assert d["content"]["metrics"][0]["value"]=="12800"
    preview=client.get(f"/api/dcells/{d['id']}/preview")
    assert preview.status_code==200
    assert "黑龙江农业数据展示" in preview.text
    assert "图片数量" in preview.text
    assert "dcell-bars" in preview.text
    clone=client.post(f"/api/dcells/{d['id']}/clone").json()
    assert clone["name"].endswith("（副本）")
    assert clone["content"]==d["content"]
    assert clone["mode"]=="template"
    assert client.post("/api/publish").status_code==200
    page=client.get(f"/dcell-{clone['id']}.html").text
    assert "12800" in page
    assert "dcell-grid" in page
    assert "dcell-bars" in page
    assert "无人机与地面采样" in page

def test_template_escapes_user_content():
    d=client.post("/api/dcells",json={
        "name":"安全模板","template":"research","mode":"template",
        "content":{"summary":"<script>alert(1)</script>",
                   "metrics":[{"label":"<img src=x onerror=alert(1)>","value":"1"}],
                   "sections":[]}
    }).json()
    response=client.get(f"/api/dcells/{d['id']}/preview")
    assert response.status_code==200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text

def test_new_template_has_default_content():
    result=client.post("/api/dcells",json={
        "name":"拆封即用","template":"metrics","mode":"template"
    }).json()
    assert result["content"]["metrics"]
    assert "dcell-metric" in client.get(f"/api/dcells/{result['id']}/preview").text

def test_source_workspace_template_to_editable_zip():
    import io,zipfile
    d=client.post("/api/dcells",json={"name":"源码测试","mode":"template","template":"metrics",
      "content":{"summary":"可编辑内容","metrics":[{"label":"图像","value":"123"}]}}).json()
    generated=client.get(f"/api/dcells/{d['id']}/generated-source")
    assert generated.status_code==200
    assert "可编辑内容" in generated.json()["content"]
    download=client.get(f"/api/dcells/{d['id']}/export")
    assert download.status_code==200
    with zipfile.ZipFile(io.BytesIO(download.content)) as z:
        assert "index.html" in z.namelist()
        assert "可编辑内容" in z.read("index.html").decode()
    result=client.post(f"/api/dcells/{d['id']}/detach")
    assert result.status_code==200,result.text
    assert client.get(f"/api/dcells/{d['id']}/source").status_code==200
    original=client.get(f"/api/dcells/{d['id']}/source/file",params={"path":"index.html"})
    assert original.status_code==200
    assert "可编辑内容" in original.json()["content"]
    saved=client.put(f"/api/dcells/{d['id']}/source/file",params={"path":"style.css"},
      json={"content":"body{font-size:20px}"})
    assert saved.status_code==200,saved.text
    saved=client.put(f"/api/dcells/{d['id']}/source/file",params={"path":"app.js"},
      json={"content":"document.body.dataset.test='ok'"})
    assert saved.status_code==200
    assert client.put(f"/api/dcells/{d['id']}/source/file",
      params={"path":"../outside.js"},json={"content":"bad"}).status_code==400
    assert client.post("/api/publish").status_code==200
    assert "可编辑内容" in client.get(f"/custom/dcell-{d['id']}/index.html").text
    assert "font-size:20px" in client.get(f"/custom/dcell-{d['id']}/style.css").text
    zip_response=client.get(f"/api/dcells/{d['id']}/export")
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
        assert z.read("app.js").decode()=="document.body.dataset.test='ok'"
        assert z.read("style.css").decode()=="body{font-size:20px}"


def test_source_workspace_package_edit_in_place():
    import io,zipfile
    d=client.post("/api/dcells",json={"name":"外部页面","mode":"package"}).json()
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("index.html","<h1>旧页面</h1>")
        z.writestr("main.js","console.log('old')")
    assert client.post(f"/api/dcells/{d['id']}/package",
      files={"file":("site.zip",archive.getvalue(),"application/zip")}).status_code==200
    assert client.put(f"/api/dcells/{d['id']}/source/file",
      params={"path":"index.html"},json={"content":"<h1>新页面</h1>"}).status_code==200
    assert "新页面" in client.get(f"/package/{d['id']}/index.html").text

def test_history_restore_and_critical_confirmation():
    import sqlite3
    t=client.post("/api/topics",json={"name":"回滚前状态"}).json()
    assert client.get("/api/history").status_code==200
    checkpoint=client.post("/api/history/checkpoint").json()["snapshot"]
    assert checkpoint
    assert client.put(f"/api/topics/{t['id']}",json={"name":"已经修改"}).status_code==200
    unauthorized=client.post(f"/api/history/restore/{checkpoint}",headers={"X-NexVain-Confirm":"wrong"})
    assert unauthorized.status_code==403
    restored=client.post(f"/api/history/restore/{checkpoint}")
    assert restored.status_code==200,restored.text
    assert restored.json()["rescue_checkpoint"]
    assert any(x["name"]=="回滚前状态" for x in client.get("/api/topics").json())
    assert not any(x["name"]=="已经修改" for x in client.get("/api/topics").json())
    assert any(x["action"]=="restore" for x in client.get("/api/history").json()["events"])

def test_confirmation_required_for_publish_and_delete():
    item=client.post("/api/topics",json={"name":"受保护内容"}).json()
    wrong=client.delete(f"/api/topics/{item['id']}",headers={"X-NexVain-Confirm":"wrong"})
    assert wrong.status_code==403
    assert client.post("/api/publish",headers={"X-NexVain-Confirm":"wrong"}).status_code==403
    assert client.delete(f"/api/topics/{item['id']}").status_code==200

def test_publish_checker_catches_missing_assets(tmp_path):
    from publish_checks import check
    root=tmp_path/"site"
    root.mkdir()
    (root/"index.html").write_text('<link rel="stylesheet" href="lost.css"><img src="missing.png">')
    result=check(root)
    assert result["ok"] is False
    assert len(result["errors"])==2
    (root/"lost.css").write_text("body{color:white}")
    (root/"missing.png").write_bytes(b"image")
    assert check(root)["ok"] is True

def test_dashboard_fullscreen_controls_and_large_screen_css():
    from app import render_document
    html=render_document("大屏","介绍","<p>正文</p>",'<a href="index.html">主页</a>',"blue")
    assert "nv-full" in html and "nv-play" in html
    assert "min-width:1920px" in html

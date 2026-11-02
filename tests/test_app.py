import os
from pathlib import Path

os.environ["NEXVAIN_DATA"] = "/tmp/nexvain-test-data"
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_topic_dcell_publish():
    t = client.post("/api/topics", json={"name":"病害专题"}).json()
    d = client.post("/api/dcells", json={"name":"玉米病害","page":{"html":"<h2>成果概况</h2><script>alert(1)</script>"}}).json()
    assert client.put(f"/api/topics/{t['id']}/dcells",json=[{"dcell_id":d["id"]}]).status_code == 200
    assert len(client.get(f"/api/dcells/{d['id']}/topics").json()) == 1
    assert client.post("/api/publish").status_code == 200
    html = client.get(f"/dcell-{d['id']}.html").text
    assert "成果概况" in html
    assert "<script>" not in html

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
    assert url in client.get(f"/dcell-{dcell['id']}.html").text
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
    assert client.get(source_url.lstrip("/")).status_code==200
    assert client.get("/media/"+response.json()["name"]).status_code==200

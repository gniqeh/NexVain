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

"""Showcase fixture must be idempotent and preserve user changes."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def command(tmp_path, *args):
    env={**os.environ,"NEXVAIN_DATA":str(tmp_path/"seed-data"),"NEXVAIN_DEV_MODE":"1"}
    return subprocess.run([sys.executable,"-m","scripts.seed_showcase",*args],
                          cwd=ROOT,env=env,capture_output=True,text=True,check=True)


def test_showcase_seed_creates_exact_3_topics_12_dcells_and_homepage(tmp_path):
    preview=command(tmp_path,"--dry-run")
    assert "寒地作物遥感" in preview.stdout
    result=command(tmp_path)
    assert "12 个 dcell" in result.stdout

    import sqlite3
    db=sqlite3.connect(tmp_path/"seed-data"/"nexvain.sqlite3")
    try:
        assert db.execute("SELECT COUNT(*) FROM topics").fetchone()[0]==3
        assert db.execute("SELECT COUNT(*) FROM dcells").fetchone()[0]==12
        assert db.execute("SELECT COUNT(*) FROM topic_dcells").fetchone()[0]==12
        assert set(r[0] for r in db.execute("SELECT template FROM dcells"))=={"overview","metrics","gallery","research"}
        page=json.loads(db.execute("SELECT value FROM settings WHERE key='home_page'").fetchone()[0])
        assert "农业专题数据展示" in page["html"]
        assert "showcase-grid" in page["css"]
        assert db.execute("SELECT value FROM settings WHERE key='published_revision'").fetchone() is None
        db.execute("UPDATE dcells SET name='我的真实数据集' WHERE id=1")
        db.commit()
    finally:
        db.close()

    second=command(tmp_path)
    assert "已初始化过" in second.stdout
    db=sqlite3.connect(tmp_path/"seed-data"/"nexvain.sqlite3")
    try:
        assert db.execute("SELECT COUNT(*) FROM dcells").fetchone()[0]==12
        assert db.execute("SELECT name FROM dcells WHERE id=1").fetchone()[0]=="我的真实数据集"
    finally:
        db.close()


def test_showcase_seed_does_not_replace_existing_homepage(tmp_path):
    command(tmp_path)
    import sqlite3
    db=sqlite3.connect(tmp_path/"seed-data"/"nexvain.sqlite3")
    try:
        db.execute("UPDATE settings SET value=? WHERE key='home_page'",
                   (json.dumps({"html":"<h2>我的首页</h2>"}),))
        db.execute("DELETE FROM settings WHERE key='showcase_seed_3topics_12dcells_v1'")
        db.execute("DELETE FROM topic_dcells")
        db.execute("DELETE FROM dcells")
        db.execute("DELETE FROM topics")
        db.commit()
    finally:db.close()
    command(tmp_path)
    db=sqlite3.connect(tmp_path/"seed-data"/"nexvain.sqlite3")
    try:
        page=json.loads(db.execute("SELECT value FROM settings WHERE key='home_page'").fetchone()[0])
        assert "我的首页" in page["html"]
    finally:db.close()

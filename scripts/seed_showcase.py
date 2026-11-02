#!/usr/bin/env python3
"""Create a non-destructive agricultural demo: 3 topics, 12 dcells, one landing page.

Run from the NexVain project directory:
    python -m scripts.seed_showcase
Optional:
    python scripts/seed_showcase.py --dry-run

No fabricated observations are presented as real data. This script does NOT publish.
It records created record IDs, so a second run leaves even renamed/edited items untouched.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path

from app import DATA, PUBLIC, PACKAGES, connection
import history_store

SEED_KEY = "showcase_seed_3topics_12dcells_v1"

TOPICS = [
    {
        "name": "寒地作物遥感",
        "description": "卫星、无人机与地面观测协同展示寒地农业遥感数据资源。",
        "category": "REMOTE SENSING",
        "datasets": [
            ("大豆物候遥感观测", "overview", "多时相卫星影像、物候阶段和田间观测信息的专题展示。", "时间范围", "影像数量"),
            ("水稻冠层温度场", "gallery", "无人机热红外及田间温度场的图像与实验资料展示。", "航飞批次", "观测区域"),
            ("玉米多光谱影像", "metrics", "玉米生育期多光谱影像和常用植被指数展示。", "影像规模", "传感器"),
            ("耕地遥感专题图", "research", "耕地分布、地块特征与专题地图成果的展示入口。", "空间分辨率", "覆盖范围"),
        ],
    },
    {
        "name": "农业气象与环境",
        "description": "长期气象、再分析数据与农田环境监测数据的专题展示。",
        "category": "AGROMETEOROLOGY",
        "datasets": [
            ("黑龙江逐日气象站观测", "metrics", "气温、降水和日照等逐日气象观测记录的展示。", "观测站点", "数据时段"),
            ("ERA5-Land 气温数据", "overview", "再分析近地面气温数据与站点观测对比的展示入口。", "时空分辨率", "数据时段"),
            ("积温栅格与积温带", "research", "不同积温阈值的空间分布与年际变化成果展示。", "积温阈值", "研究时段"),
            ("盐碱地物联网环境监测", "gallery", "土壤、气象及其他传感器监测数据的展示。", "监测点位", "采样频率"),
        ],
    },
    {
        "name": "农业视觉与病虫害",
        "description": "田间图像、病害标注与农业视觉数据生产成果的专题展示。",
        "category": "AGRICULTURAL VISION",
        "datasets": [
            ("玉米叶部病害图像", "gallery", "田间采集的玉米叶片症状图像及标注示例。", "图像数量", "病害类别"),
            ("大豆田间表型影像", "overview", "大豆群体与单株表型图像及分析结果展示。", "表型类型", "采集批次"),
            ("农作物病虫害标注样本", "metrics", "病虫害目标标注、区域标注及数据质量样例展示。", "标注数量", "标注类型"),
            ("农业视觉数据生产成果", "research", "辅助标注算法、协同生产流程与平台成果展示。", "生产环节", "成果类型"),
        ],
    },
]

HOMEPAGE_HTML = """
<section class="showcase-hero">
  <span class="showcase-eyebrow">NEXVAIN / AGRICULTURAL DATA SHOWCASE</span>
  <h2>农业专题数据展示</h2>
  <p>面向寒地农业遥感、农业气象与环境、农业视觉与病虫害的统一专题展示入口。</p>
  <p class="showcase-hint">当前为演示架构。请从左侧专题导航进入各数据集，并在后台逐步填充真实数据和图像。</p>
</section>
<section class="showcase-grid">
  <div class="showcase-panel">
    <span>01 / REMOTE SENSING</span><h2>寒地作物遥感</h2>
    <p>卫星遥感、无人机影像、冠层温度场、耕地专题图。</p>
  </div>
  <div class="showcase-panel">
    <span>02 / AGROMETEOROLOGY</span><h2>农业气象与环境</h2>
    <p>气象站逐日观测、ERA5-Land、积温分析与物联网监测。</p>
  </div>
  <div class="showcase-panel">
    <span>03 / AGRICULTURAL VISION</span><h2>农业视觉与病虫害</h2>
    <p>病害图像、作物表型、智能标注与视觉数据生产成果。</p>
  </div>
</section>
<section class="showcase-footer"><h3>演示站点 · 待填充</h3>
<p>本页及全部 12 个数据集目前只提供展示结构，不包含经过核验的业务统计结果。</p></section>
""".strip()

HOME_CSS = """
.showcase-hero{background:#153650;padding:42px;border-radius:18px;margin-bottom:22px}
.showcase-eyebrow{font-size:13px;color:#64cdf2;letter-spacing:1.5px}
.showcase-hero h2{font-size:42px;margin:22px 0;color:#f0f8ff}
.showcase-hero p{font-size:18px;color:#c8dded;line-height:1.8}
.showcase-hint{font-size:15px;color:#83adc8}
.showcase-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.showcase-panel{background:#1b405c;border:1px solid #39647e;border-radius:16px;padding:28px;min-height:235px}
.showcase-panel span{font-size:12px;color:#61c6f2}
.showcase-panel h2{font-size:23px;color:#f0f8ff}
.showcase-panel p{font-size:16px;line-height:1.7;color:#bed8e8}
.showcase-footer{background:#102d43;border-radius:12px;padding:18px 26px;margin-top:20px}
.showcase-footer h3{font-size:18px;color:#edf8ff}
.showcase-footer p{font-size:15px;color:#aac8db}
""".strip()


def _content(title, description, metric_a, metric_b):
    return {
        "summary": description + " 当前页面为演示占位，实际数据请通过后台灌注。",
        "metrics": [
            {"label": metric_a, "value": "待填充", "note": "请填入真实数据"},
            {"label": metric_b, "value": "待填充", "note": "请填入真实数据"},
            {"label": "数据状态", "value": "演示", "note": "非正式统计"},
        ],
        "chart": [],
        "images": [],
        "sections": [
            {"title": "数据简介", "text": description},
            {"title": "数据来源与采集方式", "text": "待填充：原始数据来源、采集设备或处理流程。"},
            {"title": "数据范围与质量", "text": "待填充：时间范围、空间范围、字段说明和质量控制信息。"},
            {"title": "展示与应用", "text": "待填充：图表、专题地图、分析案例或研究成果。"},
        ],
    }


def seed():
    with connection() as db:
        saved = db.execute("SELECT value FROM settings WHERE key=?", (SEED_KEY,)).fetchone()
        if saved:
            registry = json.loads(saved["value"])
            print("已初始化过，保留已有编辑，不进行任何覆盖。")
            print(json.dumps(registry, ensure_ascii=False, indent=2))
            return registry

    # A real checkpoint of all managed content before creating anything.
    checkpoint = history_store.create(DATA, PUBLIC, "Before showcase seed: 3 topics, 12 dcells, homepage")
    registry = {"version": 1, "checkpoint": checkpoint, "topics": [], "dcells": []}
    try:
        with connection() as db:
            db.execute("BEGIN")
            existing_position = db.execute("SELECT COALESCE(MAX(position),-1) FROM topics").fetchone()[0]
            for order, topic in enumerate(TOPICS):
                topic_page = {
                    "html": (
                        '<section class="panel"><h2>'+topic["name"]+'</h2>'
                        '<p>'+topic["description"]+'</p>'
                        '<p>本专题共设四个演示数据集。请从左侧导航选择具体数据集。</p></section>'
                    ),
                    "css": "",
                }
                cur = db.execute(
                    "INSERT INTO topics(name,description,page,position) VALUES(?,?,?,?)",
                    (topic["name"], topic["description"],
                     json.dumps(topic_page, ensure_ascii=False), existing_position + order + 1),
                )
                topic_id = cur.lastrowid
                registry["topics"].append({"id": topic_id, "name": topic["name"]})
                for pos, (name, template, description, metric_a, metric_b) in enumerate(topic["datasets"]):
                    content = _content(name, description, metric_a, metric_b)
                    cur = db.execute(
                        "INSERT INTO dcells(name,description,template,page,mode,content) VALUES(?,?,?,?,?,?)",
                        (name, description, template, "{}", "template",
                         json.dumps(content, ensure_ascii=False)),
                    )
                    dcell_id = cur.lastrowid
                    db.execute(
                        "INSERT INTO topic_dcells(topic_id,dcell_id,alias,position) VALUES(?,?,?,?)",
                        (topic_id, dcell_id, "", pos),
                    )
                    registry["dcells"].append(
                        {"id": dcell_id, "topic_id": topic_id, "name": name, "template": template}
                    )
            existing_home = db.execute("SELECT value FROM settings WHERE key='home_page'").fetchone()
            if not existing_home or json.loads(existing_home["value"]) == {}:
                db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('home_page',?)",
                           (json.dumps({"html": HOMEPAGE_HTML, "css": HOME_CSS}, ensure_ascii=False),))
                registry["home_created"] = True
            else:
                registry["home_created"] = False
                print("检测到你已有自定义总首页：原样保留，没有覆盖。")
            db.execute("INSERT INTO settings(key,value) VALUES(?,?)",
                       (SEED_KEY, json.dumps(registry, ensure_ascii=False)))
            db.execute(
                """INSERT INTO settings(key,value) VALUES('draft_revision','1')
                   ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1"""
            )
    except Exception:
        print(f"初始化失败，操作前恢复点：{checkpoint}")
        raise

    print(f"已创建 3 个专题、12 个 dcell；总首页 {'已创建' if registry['home_created'] else '保留原有'}。")
    print("没有自动发布。请启动 NexVain，到 /admin 修改内容，然后点击「发布静态站点」。")
    print(f"操作前恢复点：{checkpoint}")
    for topic in registry["topics"]:
        print(f"  专题 #{topic['id']}  {topic['name']}")
        for d in registry["dcells"]:
            if d["topic_id"] == topic["id"]:
                print(f"    dcell #{d['id']}  {d['name']} [{d['template']}]")
    return registry


def main():
    parser = argparse.ArgumentParser(description="NexVain 3 topics / 12 dcells demo seed")
    parser.add_argument("--dry-run", action="store_true", help="Only preview scaffold names")
    args = parser.parse_args()
    if args.dry_run:
        print("计划创建以下专题和 dcell（不会写入数据库）：")
        for topic in TOPICS:
            print("  "+topic["name"])
            for name, template, *_ in topic["datasets"]:
                print(f"    - {name} [{template}]")
        return
    seed()


if __name__ == "__main__":
    main()

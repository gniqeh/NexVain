"""Data-driven dcell page templates. No CDN and no executable user markup."""
from __future__ import annotations
import html
import re
from urllib.parse import urlsplit

TEMPLATES = {
    "overview": {"name": "数据集概览", "description": "摘要、指标、分类统计、研究说明"},
    "metrics": {"name": "指标看板", "description": "突出核心数字和对比柱状图"},
    "gallery": {"name": "图像图集", "description": "代表性图像、图注与数据概况"},
    "research": {"name": "科研成果", "description": "研究简介、成果亮点和方法说明"},
}
DEFAULT_CONTENT = {
    "summary": "在这里填写数据集的简要介绍，发布时自动套用当前模板。",
    "metrics": [
        {"label": "记录数量", "value": "12,480", "note": "演示数据"},
        {"label": "覆盖区域", "value": "黑龙江", "note": "可修改"},
        {"label": "采集年份", "value": "2025", "note": "可修改"},
    ],
    "chart": [
        {"label": "玉米", "value": 42}, {"label": "水稻", "value": 63},
        {"label": "大豆", "value": 51},
    ],
    "images": [],
    "sections": [
        {"title": "数据说明", "text": "这里介绍数据来源、采集方法、字段和展示价值。"}
    ],
}
CSS = """
.dcell-kit{--k-accent:var(--accent,#37bee6);font-family:inherit}
.dcell-kit *{box-sizing:border-box}
.dcell-hero{padding:28px 30px;background:linear-gradient(115deg,var(--panel,#193f60),transparent);border:1px solid #5784a13a;border-radius:15px;margin-bottom:20px}
.dcell-eyebrow{font-size:12px;letter-spacing:2px;color:var(--k-accent);font-weight:700}
.dcell-lead{font-size:16px;line-height:1.8;opacity:.85;max-width:1050px}
.dcell-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:16px 0 24px}
.dcell-metric,.dcell-card{padding:24px;border:1px solid #7ca6bc34;background:var(--panel,#173550);border-radius:13px;min-width:0}
.dcell-metric span,.dcell-metric small{display:block;opacity:.7}
.dcell-metric strong{display:block;font-size:31px;margin:12px 0 6px;overflow-wrap:anywhere}
.dcell-card{margin:16px 0}.dcell-card h2{font-size:20px;margin:0 0 18px}
.dcell-bars{display:flex;gap:20px;align-items:flex-end;min-height:240px;padding:20px 14px 30px;border-bottom:1px solid #6485a35c}
.dcell-bar{position:relative;flex:1;max-width:120px;min-width:18px;background:linear-gradient(0deg,#177dae,var(--k-accent));height:var(--bar-height);border-radius:8px 8px 0 0}
.dcell-bar span{position:absolute;left:-10px;right:-10px;text-align:center;bottom:-27px;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dcell-bar:hover{filter:brightness(1.2)}
.dcell-gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}
.dcell-gallery figure{margin:0;border:1px solid #7ca6bc34;background:var(--panel,#173550);border-radius:12px;overflow:hidden}
.dcell-gallery img{display:block;width:100%;height:210px;object-fit:contain;background:#0d2336}
.dcell-gallery figcaption{padding:12px 16px;font-size:14px}
.dcell-empty{opacity:.55;font-size:14px}
.dcell-sections{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.dcell-sections .dcell-card{margin:0}.dcell-sections p{white-space:pre-line;line-height:1.75;opacity:.83}
.dcell-kit.gallery .dcell-gallery img{height:300px}
.dcell-kit.metrics .dcell-metric strong{font-size:40px}
@media(max-width:650px){.dcell-hero{padding:18px}.dcell-sections{grid-template-columns:1fr}}
"""

def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)

def safe_image_url(value):
    """Only administrator-uploaded relative assets. Never embed arbitrary external URLs."""
    url = str(value or "").strip()
    if re.fullmatch(r"/?media/[a-f0-9]{32}\.(?:png|svg)", url):
        return url.lstrip("/")
    return None

def _items(content, key, maximum):
    val = content.get(key, [])
    return val[:maximum] if isinstance(val, list) else []

def render_template(name, description, template, content):
    if template not in TEMPLATES:
        raise ValueError("Unknown template")
    if not isinstance(content, dict):
        content = {}
    summary = content.get("summary") or description
    title = f'<div class="dcell-hero"><span class="dcell-eyebrow">NEXVAIN · DATASET</span><p class="dcell-lead">{esc(summary)}</p></div>'
    metrics = _items(content,"metrics",12)
    metric_html = ''.join(
        f'<div class="dcell-metric"><span>{esc(item.get("label","指标"))}</span>'
        f'<strong>{esc(item.get("value","—"))}</strong><small>{esc(item.get("note",""))}</small></div>'
        for item in metrics if isinstance(item,dict))
    metric_block = f'<section class="dcell-grid">{metric_html}</section>' if metric_html else ""
    chart = [x for x in _items(content,"chart",18) if isinstance(x,dict)]
    chart_values = []
    for item in chart:
        try:
            v = float(item.get("value", 0))
            if v >= 0 and v < 1e15:
                chart_values.append((esc(item.get("label","")),v))
        except (TypeError,ValueError,OverflowError):
            pass
    top = max((v for _,v in chart_values),default=0) or 1
    columns = ''.join(
        f'<div class="dcell-bar" style="--bar-height:{max(1,v/top*100):.1f}%;" title="{label}: {v:g}">'
        f'<span>{label}</span></div>' for label,v in chart_values)
    graph = f'<section class="dcell-card"><h2>分类统计</h2><div class="dcell-bars">{columns}</div></section>' if columns else ""
    images = []
    for item in _items(content,"images",18):
        if not isinstance(item,dict):continue
        src=safe_image_url(item.get("src",""))
        if src:
            images.append(f'<figure><img src="{esc(src)}" alt="{esc(item.get("caption","展示图片"))}" loading="lazy"><figcaption>{esc(item.get("caption","代表性图像"))}</figcaption></figure>')
    gallery = ('<section class="dcell-card"><h2>代表性图像</h2><div class="dcell-gallery">'+''.join(images)+'</div></section>') if images else ""
    sections = ''.join(f'<article class="dcell-card"><h2>{esc(x.get("title","说明"))}</h2><p>{esc(x.get("text",""))}</p></article>'
                       for x in _items(content,"sections",12) if isinstance(x,dict))
    notes = '<section class="dcell-sections">'+sections+'</section>' if sections else ""
    if template=="gallery":
        blocks=[gallery or '<section class="dcell-card dcell-empty">暂无图片，可在后台上传并添加。</section>',metric_block,notes,graph]
    elif template=="metrics":
        blocks=[metric_block,graph,notes,gallery]
    elif template=="research":
        blocks=[notes,metric_block,gallery,graph]
    else:
        blocks=[metric_block,graph,gallery,notes]
    return '<div class="dcell-kit '+template+'">'+title+''.join(blocks)+'</div>'

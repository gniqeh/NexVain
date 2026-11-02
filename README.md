# NexVain

面向农业大屏的专题库与 dcell 内容管理系统（开发原型）。

## 快速启动（Python 3.11+）

```bash
git clone https://github.com/gniqeh/NexVain.git
cd NexVain
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

- 管理后台：<http://127.0.0.1:8000/admin>
- 静态大屏：<http://127.0.0.1:8000/>（首次需要在后台点击「发布静态站点」）

## 使用顺序

1. 在「专题管理」创建一级专题，进入「设计首页」。
2. 在「dcell 管理」创建独立的 dcell，选择起始模板并编辑页面。
3. 回到专题编辑，勾选要关联的 dcell，设置可选的导航别名。
4. 在「外观设置」选取全局主题。
5. 点击「发布静态站点」，生成 `published/` 静态文件。

同一 dcell 可以被多个专题引用，不复制数据集页面。

## 技术

FastAPI + SQLite + GrapesJS + HTML/CSS/JavaScript。SQLite 文件自动创建于 `data/nexvain.sqlite3`。

## 当前原型的限制

- **管理 API 尚未加身份认证，仅限本机开发使用。请勿将 8000 端口或 /admin、/api 暴露公网。**
- GrapesJS 编辑器当前通过外部 CDN 加载；断网时回退为 HTML 文本编辑。离线部署需将编辑器依赖打包到本地；已发布 SVG 图表和 PNG 图片离线可用。
- 现在支持图片上传（图片重新编码为 PNG，剥离 EXIF），以及通过输入名称/数值生成柱状图、折线图 SVG，并将其插入页面。图表目前为静态 SVG，不是 ECharts 交互图表。地图、复杂模板还未接入。
- 发布过程保留白名单 HTML/CSS 属性，不支持任意脚本；编辑器中的部分高级样式和交互可能不能输出。发布生成的 SVG 和 PNG 文件与静态站点一同复制。
- 当前是 **可运行代码原型，并非经过完整部署验收的生产版本**。上线前还需完善登录、数据校验、素材脱敏审查和发布隔离。
- `published/` 为导出静态站点，可以单独部署到 Nginx；管理服务和 SQLite 不需要一起部署。

## 本地测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

此仓库已配置 GitHub Actions 进行基础语法和接口测试。

## 本轮新增

- 进入「设计页面」可上传 JPG/PNG/WebP（每张最高 10MB、解码不超过 3000 万像素），服务器重新编码为 PNG，删除照片 EXIF 信息。
- 可输入两列「名称,数值」，生成柱状图或折线图并插入专题/dcell 页面。SVG 文件可随发布结果复制到静态服务器。
- 这些统计图为静态 SVG，尚不支持 ECharts 悬浮提示或缩放。
- 全部上传图片请先检查是否包含可见敏感信息；去 EXIF **不等于**完成业务脱敏。

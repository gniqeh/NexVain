# NexVain dcell 外部页面导入示例

这是一个**可直接上传**的独立静态网页示例。演示数据都是虚构的。

- [下载 ZIP 直接导入](https://github.com/gniqeh/NexVain/raw/refs/heads/main/examples/import-demo.zip)
- [查看源代码](https://github.com/gniqeh/NexVain/tree/main/examples/import-demo)

## 上传 ZIP

1. 在后台创建一个 dcell，页面来源选「外部静态页面包 ZIP」并保存。
2. 上传 `examples/import-demo.zip`。
3. 点击「预览当前页面包」，确认图片和柱状图显示。
4. 在「专题管理」中关联刚创建的 dcell。
5. 点击「发布静态站点」，然后打开前台。

## 本地目录导入

也可以直接在服务器上配置 `NEXVAIN_IMPORT_ROOT` 指向仓库的 `examples` 目录，然后在后台输入相对目录 `import-demo`，使用「导入服务器目录」。

## 文件

- `index.html`：页面入口，ZIP 的**根目录**必须包含这个文件。
- `style.css`：深蓝色大屏外观。
- `app.js`：切换模拟统计数据的交互功能。
- `assets/field.svg`：本地农业示意图。

页面依赖全部本地化，不使用 CDN 或外部 API。上传后生成静态目录；无需对 GrapesJS 进行任何操作。

> 注意：外部页面 iframe 有沙箱限制。该示例使用原生 JS 操作 DOM，可以在沙箱中运行。用户自制页面如果需要跨域 API、弹窗、下载等能力，需要另行评估权限和隔离方案。

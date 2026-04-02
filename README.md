# 语雀 Lakebook 转换工具

将语雀（Yuque）导出的 `.lakebook` 文件批量转换为 **Markdown**、**CSV** 或 **Obsidian Sheet Plus** 格式，完整保留知识库的文件夹层级结构。

---

## 目录

1. [项目简介](#1-项目简介)
2. [安装](#2-安装)
3. [快速开始](#3-快速开始)
4. [命令行参考](#4-命令行参考)
5. [项目结构](#5-项目结构)
6. [模块架构与调用关系](#6-模块架构与调用关系)
7. [完整解析流程](#7-完整解析流程)
   - [7.1 .lakebook 文件的物理结构](#71-lakebook-文件的物理结构)
   - [7.2 元数据解析：$meta.json → TOC 列表](#72-元数据解析metamjson--toc-列表)
   - [7.3 目录层级还原算法](#73-目录层级还原算法)
   - [7.4 普通文档解析：HTML → Markdown](#74-普通文档解析html--markdown)
   - [7.5 LaTeX 公式还原](#75-latex-公式还原)
   - [7.6 表格文档解析：lakesheet → 行列矩阵](#76-表格文档解析lakesheet--行列矩阵)
   - [7.7 表格输出：行列矩阵 → CSV / Sheet Plus](#77-表格输出行列矩阵--csv--sheet-plus)
8. [输出格式详解](#8-输出格式详解)
9. [依赖说明](#9-依赖说明)
10. [常见问题](#10-常见问题)

---

## 1. 项目简介

语雀提供了知识库导出功能，将整个知识库打包为 `.lakebook` 文件。该文件是一个 **tar 归档**，内部以私有 JSON 格式存储所有文档。本工具对这个格式进行逆向解析，将其还原为通用格式。

**支持的转换类型：**

| 原始文档类型 | 输出格式 | 说明 |
|---|---|---|
| 普通富文本文档（Doc） | `.md` | HTML 转 Markdown，含 LaTeX 公式还原 |
| 表格文档（Sheet） | `.csv` | 通用 CSV，可用 Excel / pandas 打开 |
| 表格文档（Sheet） | `.md` | Obsidian Sheet Plus / excel-pro 插件格式 |

**核心特性：**

- 完整还原知识库的文件夹层级结构
- LaTeX 数学公式从图片还原为 `$...$` / `$$...$$` 文本
- 可选下载外链图片到本地 `attachments/` 目录
- Excel 日期序列号自动转换为 `YYYY-MM-DD` 字符串
- 批量处理多个 `.lakebook` 文件或整个目录

---

## 2. 安装

**环境要求：** Python 3.10+（推荐 3.12+）

```bash
# 安装全部依赖（推荐）
pip install markdownify beautifulsoup4 pyyaml requests

# 或使用 uv（项目自带 uv.lock）
uv sync
```

各依赖的具体用途见 [第 9 节：依赖说明](#9-依赖说明)。

---

## 3. 快速开始

```bash
# 转换单个文件，输出到 output/ 目录
python lakebook_converter.py 我的知识库.lakebook output/

# 同时转换表格文档（默认只转换普通文档）
python lakebook_converter.py 我的知识库.lakebook output/ --convert-sheets

# 表格转为 Obsidian Sheet Plus 格式，并下载图片到本地
python lakebook_converter.py 我的知识库.lakebook output/ \
    --convert-sheets --sheet-format sheet --download-image

# 批量处理目录下的所有 .lakebook 文件
python lakebook_converter.py /path/to/exports/ output/ --convert-sheets
```

**示例输出目录结构：**

```
output/
└── 我的知识库/                ← 以 lakebook 文件名命名
    ├── 第一章_基础知识/        ← 还原知识库文件夹层级
    │   ├── HTML入门.md
    │   ├── CSS入门.md
    │   └── attachments/       ← 图片（需 --download-image）
    │       ├── HTML入门_001.png
    │       └── CSS入门_001.jpg
    ├── 第二章_进阶/
    │   ├── JavaScript.md
    │   └── 数据处理.csv        ← 表格文档（需 --convert-sheets）
    └── 项目总览.md
```

---

## 4. 命令行参考

```
python lakebook_converter.py <lakebook...> <output> [选项]
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `lakebook` | 位置参数（1 个或多个） | `.lakebook` 文件路径，或包含 `.lakebook` 文件的目录 |
| `output` | 位置参数 | 输出根目录，不存在时自动创建 |
| `--download-image` | 开关 | 将文档中的外链图片下载到 `attachments/` 子目录 |
| `--convert-sheets` | 开关 | 转换表格文档；不加此选项时表格文档会被跳过 |
| `--sheet-format {csv,sheet}` | 可选值，默认 `csv` | 表格输出格式：`csv` 或 `sheet`（Obsidian Sheet Plus）|

---

## 5. 项目结构

```
lakebook/                      ← 根目录
├── lakebook_converter.py      ← 命令行入口（薄包装，调用 lakebook.cli.main）
├── pyproject.toml             ← 项目元信息与依赖声明
├── uv.lock                    ← uv 依赖锁定文件
├── README.md                  ← 本文档
│
└── lakebook/                  ← Python 包
    ├── __init__.py            ← 包初始化，暴露公开 API
    ├── constants.py           ← 全局常量
    ├── dependencies.py        ← 可选依赖检测
    ├── utils.py               ← 通用工具函数
    ├── metadata.py            ← 元数据与 TOC 解析
    ├── doc_converter.py       ← 普通文档 → Markdown
    ├── sheet_converter.py     ← 表格文档 → CSV / Sheet Plus
    ├── converter.py           ← 顶层流程编排
    └── cli.py                 ← 命令行参数解析
```

---

## 6. 模块架构与调用关系

### 6.1 依赖图（从上至下为调用方向）

```
lakebook_converter.py
        │
        ▼
  lakebook/cli.py          解析命令行参数，收集文件列表
        │
        ▼
  lakebook/converter.py    流程编排：解压→读元数据→遍历TOC→路由文档
        ├──────────────────────────────────────────────────┐
        │                                                  │
        ▼                                                  ▼
lakebook/doc_converter.py                   lakebook/sheet_converter.py
  普通文档转换流程                               表格文档转换流程
  ├─ extract_latex_from_asl()                  ├─ parse_lakesheet()
  ├─ replace_latex_images()                    ├─ _decompress_sheet()
  ├─ download_images_and_patch_html()          ├─ _extract_rows_from_sheet_json()
  ├─ html_to_markdown()                        ├─ _excel_serial_to_date()
  └─ convert_doc_to_markdown()  ◄─ 对外接口    ├─ rows_to_sheet_plus_format()
                                               ├─ _make_cell_style()
                                               ├─ convert_sheet_to_csv()      ◄─ 对外接口
                                               └─ convert_sheet_to_sheet_plus() ◄─ 对外接口

        ▲  converter.py 还调用以下基础模块：
        │
  lakebook/metadata.py      读取 $meta.json，解析 TOC 和书名
  lakebook/utils.py         sanitize_file_name / pretty_md / extract_tar
  lakebook/constants.py     TYPE_DOC / TYPE_SHEET / TMP_DIR 等常量
  lakebook/dependencies.py  HAS_BS4 / HAS_YAML / BeautifulSoup 等
```

### 6.2 各模块职责一览

| 模块 | 职责 | 对外函数 |
|---|---|---|
| [`constants.py`](lakebook/constants.py) | 集中存放所有魔法字符串和配置值，避免散落各处 | 无（仅常量） |
| [`dependencies.py`](lakebook/dependencies.py) | 统一检测可选依赖，输出友好的安装提示；其他模块从此处导入库对象 | 无（仅变量） |
| [`utils.py`](lakebook/utils.py) | 无业务逻辑的纯工具函数 | `sanitize_file_name` · `pretty_md` · `extract_tar` |
| [`metadata.py`](lakebook/metadata.py) | 解析 `$meta.json`，从两层嵌套 JSON 中提取 TOC YAML 和书名 | `read_toc_and_book_info` |
| [`doc_converter.py`](lakebook/doc_converter.py) | 普通文档从原始 JSON 到 `.md` 文件的完整转换链 | `convert_doc_to_markdown`（及其三个步骤函数） |
| [`sheet_converter.py`](lakebook/sheet_converter.py) | 表格文档的解压/解析/格式转换 | `parse_lakesheet` · `convert_sheet_to_csv` · `convert_sheet_to_sheet_plus` |
| [`converter.py`](lakebook/converter.py) | 调度中心：解压 `.lakebook`、读元数据、遍历 TOC、路由到各转换器 | `process_single_lakebook` · `extract_repos` |
| [`cli.py`](lakebook/cli.py) | `argparse` 参数定义、文件收集逻辑、成功/失败统计输出 | `main` |
| [`__init__.py`](lakebook/__init__.py) | 包版本和公开 API 声明 | 再导出 `process_single_lakebook` · `main` |

### 6.3 数据在模块间的流转

```
用户执行命令
      │
      ▼ cli.py: _collect_lakebook_files()
  [文件路径列表]
      │
      ▼ converter.py: process_single_lakebook()
  .lakebook 文件
      │ utils.py: extract_tar()
      ▼
  临时目录（tar 解压内容）
      │ metadata.py: read_toc_and_book_info()
      ▼
  toc (list[dict]) + book_name (str)
      │
      ▼ converter.py: extract_repos()
  对每个 TOC 条目循环：
      ├─ 普通文档 ──► doc_converter.py: convert_doc_to_markdown()
      │                   输入: doc dict (含 body HTML + body_asl)
      │                   输出: 写入 .md 文件
      │
      └─ 表格文档 ──► sheet_converter.py: convert_sheet_to_csv()
                      或                  convert_sheet_to_sheet_plus()
                          输入: .json 文件路径
                          输出: 写入 .csv 或 .md 文件
```

---

## 7. 完整解析流程

本节以真实数据结构为例，逐步追踪一个 `.lakebook` 文件从磁盘读取到最终输出文件的全过程。

### 7.1 .lakebook 文件的物理结构

`.lakebook` 文件是一个标准的 **tar 归档**（无压缩或 gzip 压缩），解压后得到如下目录：

```
<知识库ID>/                   ← tar 包内的根子目录，作为 repo_dir
├── $meta.json                ← 知识库元数据（书名 + TOC）
├── abc123def.json            ← 普通文档，文件名 = TOC 中的 url 字段
├── 9f8e7d6c5.json            ← 另一篇普通文档
├── b2c3d4e5f.json            ← 表格文档
└── ...
```

**相关代码：** [`converter.py` → `process_single_lakebook()`](lakebook/converter.py) 中调用 [`utils.py` → `extract_tar()`](lakebook/utils.py) 完成解压，随后用 `os.scandir()` 找到内层子目录。

---

### 7.2 元数据解析：$meta.json → TOC 列表

**相关代码：** [`metadata.py` → `read_toc_and_book_info()`](lakebook/metadata.py)

`$meta.json` 有两层 JSON 嵌套：外层是普通 JSON 文件，其 `meta` 字段的**值**本身又是一个 JSON 字符串。

**原始文件示例（`$meta.json`）：**

```json
{
  "meta": "{\"book\":{\"name\":\"前端开发笔记\",\"path\":\"https://www.yuque.com/zhangsan/frontend\",\"tocYml\":\"- title: 第一章\\n  type: TITLE\\n  url: \\\"\\\"\\n  level: 0\\n- title: HTML入门\\n  type: DOC\\n  url: abc123def\\n  level: 1\\n- title: CSS入门\\n  type: DOC\\n  url: 9f8e7d6c5\\n  level: 1\\n\"}}"
}
```

**第一层解析（JSON）→ 取 `meta` 字段再次解析：**

```python
meta_file = json.loads(open("$meta.json").read())
# meta_file == {"meta": "{...字符串...}"}

meta = json.loads(meta_file["meta"])
# meta == {
#   "book": {
#     "name":    "前端开发笔记",
#     "path":    "https://www.yuque.com/zhangsan/frontend",
#     "tocYml":  "- title: 第一章\n  type: TITLE\n  url: \"\"\n  ..."
#   }
# }
```

**第二层：`tocYml` 字段是 YAML 字符串，再次解析：**

```yaml
# tocYml 解析后的 TOC 结构示例
- title: 第一章
  type: TITLE       # 分组标题，不对应实际文件
  url: ""
  level: 0

- title: HTML入门
  type: DOC         # 普通文档
  url: abc123def    # 对应 repo_dir/abc123def.json
  level: 1

- title: CSS入门
  type: DOC
  url: 9f8e7d6c5
  level: 1

- title: 数据统计表
  type: DOC
  url: b2c3d4e5f    # 实际上是 Sheet 类型，type 字段在文档 JSON 内部
  level: 1
```

**解析结果：**

```python
toc = [
    {"title": "第一章",    "type": "TITLE", "url": "",          "level": 0},
    {"title": "HTML入门",  "type": "DOC",   "url": "abc123def", "level": 1},
    {"title": "CSS入门",   "type": "DOC",   "url": "9f8e7d6c5", "level": 1},
    {"title": "数据统计表", "type": "DOC",   "url": "b2c3d4e5f", "level": 1},
]
book_name = "前端开发笔记"
```

> **书名提取优先级：** `book.name` > URL 路径末段（`frontend`）> `"未命名知识库"`

---

### 7.3 目录层级还原算法

**相关代码：** [`converter.py` → `extract_repos()`](lakebook/converter.py)

`extract_repos()` 维护一个 `path_prefixed` **栈**，根据相邻 TOC 条目的 `level` 变化决定如何更新栈，从而将扁平的 TOC 列表还原为树状文件夹结构。

**算法规则：**

| `current_level` 变化 | 对栈的操作 | 含义 |
|---|---|---|
| `current > last` | 将**上一个条目的名称**压栈 | 当前条目是上一条目的子节点 |
| `current < last` | 弹出 `(last - current)` 个栈帧 | 回退到更高层级 |
| `current == last` | 不变 | 同级节点 |

**完整示例：**

```
TOC 条目                       level   path_prefixed 栈变化         输出路径
─────────────────────────────  ─────   ──────────────────────────   ─────────────────────────
第一章（TITLE）                  0      []                           （TITLE 不写文件）
  ├─ HTML入门（DOC）             1      ["第一章"] ← 上一条目压栈     output/第一章/HTML入门.md
  └─ CSS入门（DOC）              1      ["第一章"] ← level不变        output/第一章/CSS入门.md
第二章（TITLE）                  0      [] ← 弹出1帧（1-0=1）        （TITLE 不写文件）
  ├─ 进阶语法（DOC）             1      ["第二章"]                    output/第二章/进阶语法.md
  │   └─（注：TITLE不入栈，
  │         DOC 才是"上一条目"）
  └─ 框架选型（TITLE）           1      ["第二章"]                    （TITLE 不写文件）
      ├─ React（DOC）            2      ["第二章","框架选型"]          output/第二章/框架选型/React.md
      └─ Vue（DOC）              2      ["第二章","框架选型"]          output/第二章/框架选型/Vue.md
附录（DOC）                      0      [] ← 弹出2帧（2-0=2）        output/附录.md
```

> **注意：** TITLE 类型条目不对应文件，但它会作为下一层级 DOC 的父目录名被压栈。

---

### 7.4 普通文档解析：HTML → Markdown

**相关代码：** [`doc_converter.py`](lakebook/doc_converter.py)

每个 DOC 文档的 JSON 文件（如 `abc123def.json`）结构如下：

```json
{
  "doc": {
    "type": "Doc",
    "format": "lake",
    "body": "<h1>HTML 入门</h1><p>HTML 是 <strong>HyperText Markup Language</strong> 的缩写。</p><img src=\"https://cdn.nlark.com/formula_abc.png\"/><ul><li>标签（Tag）</li><li>属性（Attribute）</li></ul>",
    "body_asl": "<h1>HTML 入门</h1><p>...</p><card name=\"math\" value=\"data:%7B%22src%22%3A%22https%3A%2F%2Fcdn.nlark.com%2Fformula_abc.png%22%2C%22code%22%3A%22E%3Dmc%5E2%22%7D\"/><ul>...</ul>"
  }
}
```

`convert_doc_to_markdown()` 按以下步骤处理：

**步骤 1 → 2：提取 LaTeX（见 [7.5](#75-latex-公式还原)），获取正文 HTML**

```
body_asl → extract_latex_from_asl() → latex_dict
body     → 作为待转换的 HTML
```

**步骤 3：替换公式图片为 LaTeX**

```
输入 HTML（含图片）：
  <img src="https://cdn.nlark.com/formula_abc.png"/>

替换后 HTML：
  $E=mc^2$
```

**步骤 4（可选）：下载图片**

```
输入：<img src="https://example.com/photo.jpg"/>
下载：photo.jpg → attachments/HTML入门_001.jpg
输出：<img src="./attachments/HTML入门_001.jpg"/>
```

**步骤 5：HTML → Markdown（`markdownify` 库）**

```html
<!-- 输入 HTML -->
<h1>HTML 入门</h1>
<p>HTML 是 <strong>HyperText Markup Language</strong> 的缩写。</p>
$E=mc^2$
<ul>
  <li>标签（Tag）</li>
  <li>属性（Attribute）</li>
</ul>
```

```markdown
<!-- 输出 Markdown（步骤 5 结果） -->
# HTML 入门

HTML 是 **HyperText Markup Language** 的缩写。

$E=mc^2$

- 标签（Tag）
- 属性（Attribute）
```

**步骤 6：Markdown 美化（`pretty_md()`）**

```markdown
<!-- 美化前（可能含多余空行和行尾空格）   -->
# HTML 入门


HTML 是 **HyperText Markup Language** 的缩写。


$E=mc^2$

<!-- 美化后（去除行尾空白、压缩多余空行）-->
# HTML 入门

HTML 是 **HyperText Markup Language** 的缩写。

$E=mc^2$
```

**步骤 7：写入 `HTML入门.md`**

---

### 7.5 LaTeX 公式还原

**相关代码：** [`doc_converter.py` → `extract_latex_from_asl()` 和 `replace_latex_images()`](lakebook/doc_converter.py)

语雀在导出文档时，对数学公式做了两份记录：

| 位置 | 内容 | 用途 |
|---|---|---|
| `body`（正文 HTML） | `<img src="https://cdn.nlark.com/formula_xxx.png"/>` | 渲染用的公式图片 |
| `body_asl`（语法树） | `<card name="math" value="data:{JSON}"/>` | 保存了 LaTeX 原始源码 |

**`body_asl` 中的 `<card>` 节点详解：**

```html
<card
  name="math"
  value="data:%7B%22src%22%3A%22https%3A%2F%2Fcdn.nlark.com%2Fformula_xxx.png%22%2C%22code%22%3A%22%5Cfrac%7B1%7D%7B2%7D%20mv%5E2%22%7D"
/>
```

`value` 属性的值 = `"data:"` + **URL 编码的 JSON 字符串**。

URL 解码后得到：

```json
{
  "src":  "https://cdn.nlark.com/formula_xxx.png",
  "code": "\\frac{1}{2} mv^2"
}
```

**`extract_latex_from_asl()` 构建的字典：**

```python
latex_dict = {
    "https://cdn.nlark.com/formula_xxx.png": "\\frac{1}{2} mv^2",
    "https://cdn.nlark.com/formula_yyy.png": "E = mc^2",
    # ...
}
```

**`replace_latex_images()` 替换规则（行内 vs 块级）：**

```python
# 判断依据：
is_block = ("\n" in raw_latex.strip()) or (parent_tag in ("p", "div", "center"))

# 行内公式（父元素是 span、a 等，且 LaTeX 不含换行）：
$E = mc^2$

# 块级公式（LaTeX 含换行，或父元素是 p / div / center）：
$$
\frac{1}{2} mv^2
$$
```

**完整替换示例：**

```html
<!-- body 原文（含公式图片）-->
<p>动能公式：<img src="https://cdn.nlark.com/formula_xxx.png"/></p>
<div><img src="https://cdn.nlark.com/formula_yyy.png"/></div>
```

```html
<!-- replace_latex_images() 替换后 -->
<p>动能公式：$\frac{1}{2} mv^2$</p>
<div>
$$
E = mc^2
$$
</div>
```

```markdown
<!-- 最终 Markdown 输出 -->
动能公式：$\frac{1}{2} mv^2$

$$
E = mc^2
$$
```

---

### 7.6 表格文档解析：lakesheet → 行列矩阵

**相关代码：** [`sheet_converter.py` → `parse_lakesheet()`](lakebook/sheet_converter.py)

表格文档（`type: "Sheet"` 或 `format: "lakesheet"`）的 JSON 文件结构有**三层嵌套**：

```
文档 JSON 文件
└── doc.body (str)               ← 第一层：JSON 字符串
    └── body.sheet (str)         ← 第二层：zlib/gzip 压缩的字节流（latin-1 编码为字符串）
        └── 解压后的 sheet JSON   ← 第三层：实际表格数据
            └── data             ← 行列结构
```

**第一层：`doc.body` 的 JSON 内容**

```json
{
  "format": "lakesheet",
  "sheet": "\u0078\u009c..."
}
```

`sheet` 字段的值是用 **latin-1 编码**还原为字符串的压缩字节流。

**第二层：解压后的表格 JSON**

`parse_lakesheet()` 依次尝试 **zlib → gzip → 直接 JSON**（见 `_decompress_sheet()`）。

解压后得到：

```json
{
  "data": {
    "0": {
      "0": {"v": "姓名"},
      "1": {"v": "入职日期"},
      "2": {"v": "部门"}
    },
    "1": {
      "0": {"v": "张三"},
      "1": {"v": 45292},
      "2": {"v": "技术部"}
    },
    "2": {
      "0": {"v": "李四"},
      "1": {"v": 3942259200},
      "2": {"v": "产品部"}
    }
  }
}
```

**`_extract_rows_from_sheet_json()` 的处理逻辑：**

1. 收集所有字符串形式的行号 `"0"`, `"1"`, `"2"` → 转为整数并**排序**（保证行顺序）
2. 找出最大列号（此处为 `2`），统一各行列数
3. 提取每个单元格的 `v` 字段
4. 若 `v` 是字典（如超链接 `{"text": "点击", "url": "..."}`），取 `text` 或 `url`

**输出的行列矩阵（`List[List[str]]`）：**

```python
rows = [
    ["姓名",  "入职日期",   "部门"],    # 行 0：表头
    ["张三",  "45292",     "技术部"],  # 行 1：数字未转换，下一步处理
    ["李四",  "3942259200","产品部"],  # 行 2
]
```

---

### 7.7 表格输出：行列矩阵 → CSV / Sheet Plus

#### 7.7.1 CSV 输出

**相关代码：** [`sheet_converter.py` → `convert_sheet_to_csv()`](lakebook/sheet_converter.py)

直接使用 `csv.writer` 写出，**原样输出**数字（不做日期转换）：

```csv
姓名,入职日期,部门
张三,45292,技术部
李四,3942259200,产品部
```

#### 7.7.2 Sheet Plus 输出与日期处理

**相关代码：** [`sheet_converter.py` → `rows_to_sheet_plus_format()` 和 `_excel_serial_to_date()`](lakebook/sheet_converter.py)

生成 Obsidian Sheet Plus 格式时，会对**非表头行**的数字尝试转换为 ISO 日期：

**`_excel_serial_to_date()` 的转换规则：**

| 输入范围 | 含义 | 示例 | 转换结果 |
|---|---|---|---|
| `0 < n < 100000` | Excel 天数序列（起点 1899-12-30） | `45292` | `2024-01-01` |
| `3×10⁹ ≤ n ≤ 5×10⁹` | 秒数序列（起点 1899-12-30） | `3942259200` | `2024-11-01` |
| 其他数字 | 普通数值，不转换 | `3.14` | `3.14`（保持原样） |

> **为什么起点是 1899-12-30？**
> Excel 1.0 将 1900 年错误地当作闰年处理（存在 1900-02-29），导致实际计数起点比正确的 1900-01-01 提前了一天，即 1899-12-30。

转换后 `rows_to_sheet_plus_format()` 的输入变为：

```python
[
    ["姓名",  "入职日期",   "部门"],
    ["张三",  "2024-01-01","技术部"],
    ["李四",  "2024-11-01","产品部"],
]
```

**最终生成的 `.md` 文件结构（Obsidian Sheet Plus 格式）：**

```markdown
---

excel-pro-plugin: parsed

---
```sheet
{"id":"aB3xYz","sheetOrder":["kR9mP2qLsT4uVwXy"],"name":"数据统计表","appVersion":"0.15.0","locale":"enUS","styles":{"hd1Xy2":{"ff":"Arial","fs":9,"bl":1,"bd":{"l":{"cl":{"rgb":"rgb(204,204,204)"},"s":1},...}},"dt5Pq6":{"ff":"Calibri","fs":11,"bl":0,...}},"sheets":{"kR9mP2qLsT4uVwXy":{"id":"kR9mP2qLsT4uVwXy","name":"Sheet1","rowCount":1000,"columnCount":20,"cellData":{"0":{"0":{"s":"hd1Xy2","v":"姓名","t":1},"1":{"s":"hd1Xy2","v":"入职日期","t":1},"2":{"s":"hd1Xy2","v":"部门","t":1}},"1":{"0":{"s":"dt5Pq6","v":"张三","t":1},"1":{"s":"dt5Pq6","v":"2024-01-01","t":1},"2":{"s":"dt5Pq6","v":"技术部","t":1}},...},...}},...}
```

```multiSheet
{"tabs":[{"key":"sheet","type":"sheet","label":"Sheet"}],"defaultActiveKey":"sheet"}
```
```

**JSON 结构说明（`sheet` 代码块内）：**

```jsonc
{
  "id":         "aB3xYz",               // 工作簿 ID（随机6位）
  "sheetOrder": ["kR9mP2qLsT4uVwXy"],  // 工作表顺序
  "name":       "数据统计表",             // 文件名（去 .md 后缀）
  "styles": {
    "hd1Xy2": { /* 表头样式：Arial 9pt 加粗 + 灰色框线 */ },
    "dt5Pq6": { /* 数据样式：Calibri 11pt 普通 */ }
  },
  "sheets": {
    "kR9mP2qLsT4uVwXy": {
      "cellData": {
        "0": {                          // 行号（字符串）
          "0": {"s": "hd1Xy2", "v": "姓名",       "t": 1},  // t=1 文本
          "1": {"s": "hd1Xy2", "v": "入职日期",   "t": 1},
          "2": {"s": "hd1Xy2", "v": "部门",       "t": 1}
        },
        "1": {
          "0": {"s": "dt5Pq6", "v": "张三",       "t": 1},
          "1": {"s": "dt5Pq6", "v": "2024-01-01", "t": 1},  // 已转换
          "2": {"s": "dt5Pq6", "v": "技术部",     "t": 1}
        }
      }
    }
  }
}
```

---

## 8. 输出格式详解

### 8.1 Markdown 文档

- 编码：UTF-8
- 标题：ATX 风格（`#` 号）
- 公式：`$...$`（行内）、`$$...$$`（块级）
- 图片：若启用 `--download-image`，`src` 改为 `./attachments/文件名`

### 8.2 目录层级映射

语雀知识库 TOC 结构 → 输出文件夹层级（一一对应）：

```
语雀知识库                           输出目录
─────────────────────────            ─────────────────────────────────
📁 第一章（TITLE, level=0）          output/书名/第一章/
   📄 HTML入门（DOC,  level=1）      output/书名/第一章/HTML入门.md
   📄 CSS入门（DOC,   level=1）      output/书名/第一章/CSS入门.md
📁 第二章（TITLE, level=0）          output/书名/第二章/
   📁 框架（TITLE,   level=1）       output/书名/第二章/框架/
      📄 React（DOC, level=2）       output/书名/第二章/框架/React.md
📄 附录（DOC,         level=0）      output/书名/附录.md
```

### 8.3 文件命名规则

文档标题经过 `sanitize_file_name()` 处理，以下字符被替换为 `_`：

```
/  \  ?  *  <  >  |  "  :  （空格）
```

示例：`"研发/2024 Q1:总结"` → `"研发_2024_Q1_总结.md"`

若输出目录下已存在同名文件，会追加随机数字后缀（如 `研发_2024_Q1_总结_427.md`）以避免覆盖。

### 8.4 图片附件

启用 `--download-image` 时，每篇文档会在其输出目录下创建 `attachments/` 子目录：

```
文件命名格式：<清理后的文档标题>_<序号3位>.扩展名

示例：
  HTML入门_001.png    ← 第 1 张图
  HTML入门_002.jpg    ← 第 2 张图
  HTML入门_003.svg    ← 第 3 张图
```

扩展名根据 HTTP 响应的 `Content-Type` 决定：

| Content-Type | 扩展名 |
|---|---|
| `image/png` | `.png` |
| `image/jpeg` | `.jpg` |
| `image/gif` | `.gif` |
| `image/svg+xml` | `.svg` |
| 其他 | `.jpg`（默认） |

---

## 9. 依赖说明

**相关代码：** [`dependencies.py`](lakebook/dependencies.py)

所有依赖均在模块顶层统一检测，缺失时打印友好提示并降级运行（非致命）。

| 依赖包 | 是否必须 | 用途 | 缺失时的降级行为 |
|---|---|---|---|
| `pyyaml` | **必须** | 解析 `tocYml` 字段（YAML 格式的目录结构） | 抛出 `ImportError`，**无法运行** |
| `markdownify` | 推荐 | HTML → Markdown 转换（保留格式） | 降级为正则剥除 HTML 标签，**丢失所有格式** |
| `beautifulsoup4` | 推荐 | HTML 解析（LaTeX 提取、图片下载） | 跳过 LaTeX 还原和图片下载 |
| `requests` | 可选 | 下载外链图片（仅 `--download-image` 时需要） | 图片保留外链，不下载到本地 |

---

## 10. 常见问题

**Q：为什么表格文档默认不转换？**

A：表格文档（Sheet）需要额外的解压和格式转换，处理时间较长。加 `--convert-sheets` 选项明确启用。

**Q：`--sheet-format sheet` 和 `csv` 有什么区别？**

A：`csv` 输出通用 CSV 文件，但不包含样式信息，日期可能以数字形式存储。`sheet` 输出 Obsidian Sheet Plus 格式，会自动转换日期序列号，并在 Obsidian 中以完整电子表格界面展示（需安装 [excel-pro 插件](https://github.com/ljcoder2015/obsidian-excel-pro)）。

**Q：转换后 LaTeX 公式显示为 `$...$` 文本而非渲染效果？**

A：需要 Markdown 渲染器支持 LaTeX。Obsidian、Typora、MkDocs 等工具均支持。若使用 GitHub 预览，可考虑安装 MathJax 插件。

**Q：运行时提示"未安装 beautifulsoup4"，但我不需要下载图片，可以忽略吗？**

A：可以忽略图片下载相关警告，但 **beautifulsoup4 同时用于 LaTeX 公式还原**。缺少它时，文档中的数学公式将以 `<img>` 标签形式保留在 Markdown 中，而非 `$...$` 格式。建议安装。

**Q：输出目录中出现了 `_427.md` 这样带数字后缀的文件？**

A：知识库中存在同名文档，工具为避免覆盖自动追加了随机后缀。这是正常行为。

**Q：如何以 Python 库方式调用而非命令行？**

```python
from lakebook import process_single_lakebook

process_single_lakebook(
    lakebook_path  = "我的知识库.lakebook",
    base_output_dir= "output/",
    download_image = False,
    convert_sheets = True,
    sheet_format   = "csv",
)
```

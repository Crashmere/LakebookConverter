# -*- coding: utf-8 -*-
"""
常量定义

存放项目中所有全局常量，包括文档类型标识、文件命名配置、
MIME 类型映射等。将魔法字符串集中在此处，避免散落于各模块，
便于统一修改和查找。
"""

import tempfile

# ── 语雀 TOC 条目 type 字段的可能值 ──────────────────────────────────────────
TYPE_TITLE = "TITLE"   # 分组标题节点：仅用于在目录中显示层级，不对应实际文档
TYPE_DOC   = "DOC"     # 普通富文本文档（HTML / Markdown 格式）
TYPE_SHEET = "Sheet"   # 表格文档（lakesheet 格式，类似 Excel）

# ── Lakebook 内部文件名 ───────────────────────────────────────────────────────
# Lakebook 解压后，知识库元数据（TOC、书名等）存储在此 JSON 文件中
META_JSON = "$meta.json"

# ── 临时目录 ─────────────────────────────────────────────────────────────────
# 解压 .lakebook tar 包时使用系统临时目录，处理完毕后自动清理
TMP_DIR = tempfile.gettempdir()

# ── Markdown 生成配置 ─────────────────────────────────────────────────────────
# markdownify 库生成标题的风格：
#   ATX  = 井号风格（如 # 一级标题  ## 二级标题）
#   SETEXT = 下划线风格（较少用）
DEFAULT_HEADING_STYLE = "ATX"

# ── 图片 Content-Type → 文件扩展名映射 ───────────────────────────────────────
# 下载图片时，根据 HTTP 响应的 Content-Type 头决定保存的文件扩展名。
# 若 Content-Type 不在此映射中，将回退到 .jpg。
CONTENT_TYPE_TO_EXTENSION: dict[str, str] = {
    "image/gif":     ".gif",
    "image/jpeg":    ".jpg",
    "image/svg+xml": ".svg",
    "image/png":     ".png",
}

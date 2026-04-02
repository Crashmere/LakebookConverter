# -*- coding: utf-8 -*-
"""
可选依赖检测与统一导入

在模块顶层尝试导入所有可选依赖，用 HAS_* 布尔标志记录结果，
并在缺失时打印友好的安装提示。

其他模块统一从此处导入依赖对象（如 BeautifulSoup、yaml），
无需重复编写 try/except，也使依赖状态一目了然。

依赖说明：
  markdownify   将 HTML 转为 Markdown（推荐，无则降级为正则剥标签）
  beautifulsoup4 HTML 解析，用于 LaTeX 提取和图片下载（推荐安装）
  pyyaml        解析 TOC 中的 YAML 格式目录结构（必须安装）
  requests      下载外链图片到本地（仅 --download-image 时需要）
"""

# ── markdownify ───────────────────────────────────────────────────────────────
try:
    from markdownify import markdownify as md_convert  # type: ignore
    HAS_MARKDOWNIFY = True
except ImportError:
    md_convert = None          # type: ignore
    HAS_MARKDOWNIFY = False
    print("警告: 未安装 markdownify，HTML 转换效果可能不佳。建议运行: pip install markdownify")

# ── beautifulsoup4 ────────────────────────────────────────────────────────────
try:
    from bs4 import BeautifulSoup  # type: ignore
    HAS_BS4 = True
except ImportError:
    BeautifulSoup = None       # type: ignore
    HAS_BS4 = False
    print("警告: 未安装 beautifulsoup4，无法解析 HTML。建议运行: pip install beautifulsoup4")

# ── pyyaml ────────────────────────────────────────────────────────────────────
try:
    import yaml                # type: ignore
    HAS_YAML = True
except ImportError:
    yaml = None                # type: ignore
    HAS_YAML = False
    print("错误: 未安装 pyyaml，无法解析目录结构。请运行: pip install pyyaml")

# ── requests ─────────────────────────────────────────────────────────────────
try:
    from requests import get as http_get  # type: ignore
    HAS_REQUESTS = True
except ImportError:
    http_get = None            # type: ignore
    HAS_REQUESTS = False
    print("警告: 未安装 requests，无法下载图片。建议运行: pip install requests")

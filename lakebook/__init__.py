# -*- coding: utf-8 -*-
"""
lakebook 包

语雀 Lakebook 转换工具，支持将 .lakebook 导出文件转换为：
  - Markdown (.md)          普通富文本文档
  - CSV (.csv)              表格文档（通用格式）
  - Obsidian Sheet Plus     表格文档（Obsidian excel-pro 插件格式）

模块结构：
  constants.py      全局常量（文档类型、MIME 映射等）
  dependencies.py   可选依赖检测（markdownify / bs4 / yaml / requests）
  utils.py          通用工具函数（文件名清理、Markdown 美化、tar 解压）
  metadata.py       元数据与 TOC 目录结构解析
  doc_converter.py  普通文档 → Markdown 转换（含 LaTeX 还原、图片下载）
  sheet_converter.py 表格文档 → CSV / Obsidian Sheet Plus 转换
  converter.py      顶层流程编排（process_single_lakebook、extract_repos）
  cli.py            命令行入口（main）

对外公开的核心 API：
  process_single_lakebook() - 处理单个 .lakebook 文件
  main()                    - 命令行入口
"""

__version__ = "0.1.0"

# 对外暴露最常用的两个入口，方便以库方式调用
from lakebook.converter import process_single_lakebook
from lakebook.cli import main

__all__ = ["process_single_lakebook", "main"]

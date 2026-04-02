# -*- coding: utf-8 -*-
"""
元数据与目录结构解析

.lakebook 文件解压后，根目录下的 $meta.json 存储了整个知识库的元数据：
- 知识库基本信息（名称 name、访问路径 path 等）
- 目录结构 TOC（以 YAML 字符串嵌入 tocYml 字段）

$meta.json 结构示例（简化）：
{
  "meta": "{...JSON 字符串...}"    <-- 外层是 JSON 文件，meta 字段值是另一个 JSON 字符串
}

meta 字段解析后结构：
{
  "book": {
    "name":    "知识库名称",
    "path":    "https://www.yuque.com/username/repo",
    "tocYml":  "- title: 文档1\\n  url: abc123\\n  type: DOC\\n  ..."
  }
}

本模块负责完整解析上述结构，返回可直接使用的 TOC 列表和知识库名称。
"""

import json
import os
from typing import Any, List, Tuple

from lakebook.constants import META_JSON
from lakebook.dependencies import HAS_YAML, yaml


def read_toc_and_book_info(repo_dir: str) -> Tuple[List[Any], str]:
    """
    读取并解析知识库的目录结构（TOC）和基本信息。

    TOC 列表中每个条目是一个字典，常用字段：
      type  (str):  "DOC" | "TITLE"（文档类型）
      url   (str):  文档唯一标识，对应解压目录下的 <url>.json 文件
      level (int):  在目录树中的层级深度（0 为顶级）
      title (str):  文档显示标题

    Args:
        repo_dir: Lakebook 解压后的内层目录路径
                  （tar 包通常在根目录下放一个子目录，此处传入该子目录路径）

    Returns:
        (toc, book_name) 元组：
          - toc (list): TOC 条目列表，由 YAML 解析得到
          - book_name (str): 知识库名称，优先使用 name 字段，
                            其次从 URL path 末段提取，最后兜底为 "未命名知识库"

    Raises:
        ImportError: 未安装 pyyaml 时抛出，因为 TOC 以 YAML 格式存储
    """
    if not HAS_YAML:
        raise ImportError("需要安装 pyyaml 才能解析目录结构，请运行: pip install pyyaml")

    meta_file_path = os.path.join(repo_dir, META_JSON)
    with open(meta_file_path, "r", encoding="utf-8") as f:
        # $meta.json 本身是一个 JSON 对象，但其 "meta" 字段的值是
        # 另一个被 JSON 序列化为字符串的对象（二次编码），需要再解析一次
        meta_file = json.loads(f.read())

    meta_str = meta_file.get("meta", "")
    meta = json.loads(meta_str)
    book_info = meta.get("book", {})

    # TOC 以 YAML 字符串形式嵌在 tocYml 字段中，使用 unsafe_load 以支持
    # YAML 中可能出现的任意 Python 对象（语雀导出的 YAML 通常是安全的）
    toc_str = book_info.get("tocYml", "")
    toc = yaml.unsafe_load(toc_str)

    # ── 提取知识库名称（优先级：name > path 末段 > 默认值）──────────────────
    book_name = book_info.get("name", "").strip()

    if not book_name:
        # 从 path（通常是 https://www.yuque.com/username/repo 格式）提取最后一段
        book_path = book_info.get("path", "")
        if book_path:
            parts = book_path.rstrip("/").split("/")
            if parts:
                book_name = parts[-1]

    if not book_name:
        book_name = "未命名知识库"

    return toc, book_name

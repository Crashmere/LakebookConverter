# -*- coding: utf-8 -*-
"""
转换流程编排

本模块是各功能模块的"调度中心"，负责：

  process_single_lakebook()
    处理单个 .lakebook 文件的完整生命周期：
      解压 tar 包 → 读取元数据 → 创建输出目录 → 转换所有文档 → 清理临时文件

  extract_repos()
    遍历 TOC 目录树，对每个文档条目：
      - 根据 level 字段维护目录层级栈，复现知识库的文件夹结构
      - 根据文档类型（Doc / Sheet）路由到对应的转换器

业务逻辑（LaTeX 处理、CSV 生成等）均由 doc_converter 和 sheet_converter 负责，
本模块只做流程控制，不直接操作文档内容。
"""

import json
import os
import random
import shutil
import traceback

from lakebook.constants import TYPE_DOC, TYPE_SHEET, TMP_DIR
from lakebook.doc_converter import convert_doc_to_markdown
from lakebook.metadata import read_toc_and_book_info
from lakebook.sheet_converter import convert_sheet_to_csv, convert_sheet_to_sheet_plus
from lakebook.utils import extract_tar, sanitize_file_name


# ── 内部辅助函数 ──────────────────────────────────────────────────────────────

def _handle_sheet_doc(
    raw_path: str,
    output_dir_path: str,
    sanitized_title: str,
    title: str,
    convert_sheets: bool,
    sheet_format: str,
) -> None:
    """
    处理表格类文档：根据用户配置决定是否转换以及转换为哪种格式。

    Args:
        raw_path:         文档 JSON 文件路径
        output_dir_path:  输出目录
        sanitized_title:  清理后的标题（用作文件名前缀）
        title:            原始标题（用于日志和 Univer JSON 的 name 字段）
        convert_sheets:   是否转换表格（默认为 True，可通过 --nosheet 禁用）
        sheet_format:     输出格式，"csv" 或 "sheet"
    """
    if not convert_sheets:
        print(f"  跳过表格文档: {title}（使用 --nosheet 选项禁用了表格转换）")
        return

    if sheet_format == "sheet":
        output_path = os.path.join(output_dir_path, sanitized_title + ".md")
        convert_sheet_to_sheet_plus(raw_path, output_path, title)
    else:
        # 默认格式为 CSV
        output_path = os.path.join(output_dir_path, sanitized_title + ".csv")
        convert_sheet_to_csv(raw_path, output_path)


# ── 核心转换函数 ──────────────────────────────────────────────────────────────

def extract_repos(
    repo_dir: str,
    output: str,
    toc: list,
    download_image: bool,
    convert_sheets: bool,
    sheet_format: str,
    book_name: str = "",
) -> None:
    """
    遍历 TOC 目录树，提取并转换所有文档到输出目录。

    ── 目录层级算法 ─────────────────────────────────────────────────────────────

    path_prefixed 是一个栈，存储从根到当前节点路径上各父节点的清理后名称。
    根据相邻条目的 level 变化动态更新：

      level 增大（进入子层级）：
        将上一个节点名压栈，当前节点是其子节点
        示例：["父目录"] → ["父目录", "子目录"]

      level 减小（退回上层）：
        弹出多余的栈帧，数量为 level 差值
        示例：["父", "子", "孙"] level 减 2 → ["父"]

      level 不变：
        栈保持不变，当前节点与上一节点同级

    最终用 os.path.join(output, *path_prefixed) 构建输出目录路径，
    复现语雀知识库的文件夹层级结构。

    ── 文档类型路由 ─────────────────────────────────────────────────────────────

    每个 DOC 类型的条目对应解压目录下的 <url>.json 文件，读取后判断：
      - doc.type == "Sheet" 或 doc.format == "lakesheet" → 表格文档
      - 其他 → 普通富文本文档

    TITLE 类型条目仅用于构建目录层级，不对应实际文件，直接跳过。

    Args:
        repo_dir:      Lakebook 解压后的内层目录路径
        output:        输出根目录
        toc:           TOC 条目列表（由 read_toc_and_book_info 解析）
        download_image: 是否下载外链图片
        convert_sheets: 是否转换表格文档
        sheet_format:  表格输出格式（"csv" 或 "sheet"）
        book_name:     知识库名称（仅用于日志）
    """
    last_level          = 0
    last_sanitized_title = ""
    path_prefixed: list = []  # 当前节点的祖先目录名称栈

    for item in toc:
        t             = item.get("type", "")
        url           = str(item.get("url", ""))
        current_level = item.get("level", 0)
        title         = str(item.get("title", ""))

        # 无标题的条目通常是分隔线等装饰性节点，直接跳过
        if not title:
            continue

        sanitized_title = sanitize_file_name(title)

        # 若同名路径已存在（极少数情况），追加随机数避免覆盖
        while os.path.exists(os.path.join(output, sanitized_title)):
            sanitized_title = sanitize_file_name(title) + str(random.randint(0, 1000))

        # ── 更新目录层级栈 ──────────────────────────────────────────────────
        if current_level > last_level:
            # 进入更深一层：把上一节点名作为父目录名压栈
            path_prefixed = path_prefixed + [last_sanitized_title]
        elif current_level < last_level:
            # 回到上层：弹出对应数量的栈帧
            diff = last_level - current_level
            path_prefixed = path_prefixed[:-diff]
        # current_level == last_level：栈保持不变（同级节点）

        # ── 处理文档条目 ────────────────────────────────────────────────────
        if t == TYPE_DOC:
            raw_path = os.path.join(repo_dir, url + ".json")
            if not os.path.exists(raw_path):
                print(f"  警告: 文档文件不存在，跳过: {raw_path}")
                last_sanitized_title = sanitized_title
                last_level           = current_level
                continue

            # 读取文档 JSON，判断实际类型（普通文档 vs 表格）
            with open(raw_path, "r", encoding="utf-8") as f:
                doc_container = json.loads(f.read())
            doc = doc_container.get("doc", {})

            is_sheet = (
                doc.get("type", "")   == TYPE_SHEET or
                doc.get("format", "") == "lakesheet"
            )

            # 确保输出目录存在
            output_dir_path = os.path.join(output, *path_prefixed)
            if not os.path.exists(output_dir_path):
                os.makedirs(output_dir_path)

            if is_sheet:
                _handle_sheet_doc(
                    raw_path, output_dir_path,
                    sanitized_title, title,
                    convert_sheets, sheet_format,
                )
            else:
                convert_doc_to_markdown(doc, output_dir_path, sanitized_title, download_image)

        # 更新"上一节点"状态，供下一次迭代的层级计算使用
        last_sanitized_title = sanitized_title
        last_level           = current_level


def process_single_lakebook(
    lakebook_path: str,
    base_output_dir: str,
    download_image: bool,
    convert_sheets: bool,
    sheet_format: str,
) -> bool:
    """
    处理单个 .lakebook 文件的完整流程。

    ── 处理步骤 ─────────────────────────────────────────────────────────────────
    1. 验证文件存在
    2. 解压 tar 包到临时目录（路径含进程 ID + 随机数，避免并发冲突）
    3. 在解压目录中找到内层内容目录
    4. 读取 $meta.json，获取 TOC 和知识库名称
    5. 以 lakebook 文件名（去后缀）作为输出子目录名
    6. 调用 extract_repos() 转换所有文档
    7. （finally 块）无论成功与否，清理临时目录

    输出目录结构示例：
      <base_output_dir>/
        <lakebook文件名>/
          文档A.md
          子目录/
            文档B.md
            表格C.csv

    Args:
        lakebook_path:   .lakebook 文件路径
        base_output_dir: 所有知识库的输出根目录
        download_image:  是否下载外链图片
        convert_sheets:  是否转换表格文档
        sheet_format:    表格输出格式（"csv" 或 "sheet"）

    Returns:
        True 表示处理成功，False 表示出错
    """
    if not os.path.exists(lakebook_path):
        print(f"错误: Lakebook 文件不存在: {lakebook_path}")
        return False

    lakebook_filename = os.path.basename(lakebook_path)
    print(f"\n{'='*60}")
    print(f"处理: {lakebook_filename}")
    print(f"{'='*60}")

    # 以文件名（去 .lakebook 后缀）作为输出子目录名，清理非法字符
    book_dir_name = lakebook_filename
    if book_dir_name.endswith(".lakebook"):
        book_dir_name = book_dir_name[:-9]
    book_dir_name = sanitize_file_name(book_dir_name)

    # 创建唯一的临时目录，进程 ID + 随机数确保并发安全
    tmp_dir = os.path.join(
        TMP_DIR, f"lakebook_{os.getpid()}_{random.randint(1000, 9999)}"
    )
    extract_tar(lakebook_path, tmp_dir)

    # tar 包内通常有一个根子目录，找到它作为 repo_dir
    repo_dir = ""
    for entry in os.scandir(tmp_dir):
        if entry.is_dir():
            repo_dir = entry.path
            break

    if not repo_dir:
        print(f"错误: {lakebook_path} 格式无效（解压后未找到内容目录）")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False

    try:
        toc, book_name = read_toc_and_book_info(repo_dir)
        print(f"  知识库名称: {book_name}")
        print(f"  目录条目数: {len(toc)}")

        book_output_dir = os.path.join(base_output_dir, book_dir_name)
        if not os.path.exists(book_output_dir):
            os.makedirs(book_output_dir)

        extract_repos(
            repo_dir, book_output_dir, toc,
            download_image, convert_sheets, sheet_format,
            book_name,
        )

        print(f"\n✓ 输出目录: {book_output_dir}")
        return True

    except Exception as e:
        print(f"✗ 处理 {lakebook_path} 时出错: {e}")
        traceback.print_exc()
        return False

    finally:
        # 无论成功与否，都清理临时目录，避免占用磁盘空间
        shutil.rmtree(tmp_dir, ignore_errors=True)

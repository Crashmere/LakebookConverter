# -*- coding: utf-8 -*-
"""
普通文档 (Doc) 转换器

负责将语雀富文本文档转换为 Markdown 文件，完整流程如下：

  1. LaTeX 公式还原
     语雀将数学公式渲染为图片（<img>）存入 body HTML，但在 body_asl
     （文档语法树，AST）中以 <card name="math"> 节点保存了原始 LaTeX 源码。
     本模块先从 body_asl 中提取 img_src → latex_code 字典，再用 LaTeX
     表达式替换 body HTML 中对应的 <img> 占位符，生成可在 Obsidian 等
     工具中直接渲染的 $...$ / $$...$$ 语法。

  2. 图片下载（可选）
     若启用 --download-image，将 body HTML 中所有外链图片下载到
     <输出目录>/attachments/ 并更新 src 为相对路径。

  3. HTML → Markdown 转换
     优先使用 markdownify 库（效果更好），不可用时降级为正则剥标签。

  4. Markdown 美化
     去除行尾空白和多余空行，使输出更整洁。
"""

import json
import os
import urllib.parse
from typing import Dict

from lakebook.constants import DEFAULT_HEADING_STYLE, CONTENT_TYPE_TO_EXTENSION
from lakebook.dependencies import (
    HAS_MARKDOWNIFY, md_convert,
    HAS_BS4, BeautifulSoup,
    HAS_REQUESTS, http_get,
)
from lakebook.utils import pretty_md


# ── HTML → Markdown ───────────────────────────────────────────────────────────

def _extract_code_language(pre_tag) -> str:
    """
    从语雀导出的 <pre> 代码块中提取语言标记。

    语雀在 body HTML 中通常会以两种方式保存语言：
    - data-language="bash"
    - class="ne-codeblock language-bash"

    Args:
        pre_tag: markdownify 传入的 <pre> 标签对象

    Returns:
        代码块语言名；若缺失则返回空字符串
    """
    language = str(pre_tag.get("data-language", "")).strip()
    if language:
        return language

    class_names = pre_tag.get("class", [])
    if isinstance(class_names, str):
        class_names = [class_names]

    for class_name in class_names:
        if class_name.startswith("language-") and len(class_name) > len("language-"):
            return class_name[len("language-"):]

    return ""

def html_to_markdown(html: str) -> str:
    """
    将 HTML 字符串转换为 Markdown 格式。

    优先使用 markdownify 库（能正确处理表格、列表、链接等结构）；
    若库未安装，降级为简单的正则剥标签方案（仅保留纯文本，丢失格式）。

    Args:
        html: 输入 HTML 字符串

    Returns:
        Markdown 格式字符串
    """
    if HAS_MARKDOWNIFY:
        return md_convert(
            html,
            heading_style=DEFAULT_HEADING_STYLE,
            code_language_callback=_extract_code_language,
        )
    else:
        # 降级方案：用正则移除所有 HTML 标签，再反转义 HTML 实体
        from html import unescape
        import re
        text = re.sub(r"<[^>]+>", "", html)
        return unescape(text).strip()


# ── LaTeX 公式处理 ────────────────────────────────────────────────────────────

def extract_latex_from_asl(body_asl: str) -> Dict[str, str]:
    """
    从语雀文档的 AST（body_asl 字段）中提取 LaTeX 公式源码。

    语雀在导出 body_asl 时，每个数学公式以如下节点表示：
      <card name="math" value="data:{URL编码的JSON}" />

    value 属性中 JSON 的结构：
      {
        "src":  "https://cdn.nlark.com/.../math-formula.png",  // 公式图片 URL
        "code": "E = mc^2"                                      // LaTeX 源码
      }

    src 与 body HTML 中 <img src="..."> 的 src 属性一一对应，
    因此可以用此字典将图片替换回 LaTeX 源码。

    Args:
        body_asl: 语雀文档的 AST 表示（HTML-like 格式字符串）

    Returns:
        img_src → latex_code 的映射字典。
        若 beautifulsoup4 不可用或 body_asl 为空，返回空字典。
    """
    if not HAS_BS4 or not body_asl:
        return {}

    latex_dict: Dict[str, str] = {}
    asl_soup = BeautifulSoup(body_asl, "html.parser")

    for card in asl_soup.find_all("card", {"name": "math"}):
        val = card.get("value", "")
        # value 属性格式为 "data:{URL编码的JSON字符串}"
        if not val.startswith("data:"):
            continue
        try:
            # 去掉 "data:" 前缀，URL 解码后再解析 JSON
            json_str = urllib.parse.unquote(val[5:])
            card_data = json.loads(json_str)
            src  = card_data.get("src", "")
            code = card_data.get("code", "")
            if src and code:
                latex_dict[src] = code
        except Exception:
            # 个别格式异常的节点跳过，不影响整体转换
            pass

    return latex_dict


def replace_latex_images(html: str, latex_dict: Dict[str, str]) -> str:
    """
    将 body HTML 中表示 LaTeX 公式的 <img> 标签替换为 Markdown 数学公式语法。

    替换规则：
    - 行内公式（$...$）：单行 LaTeX 代码 且 父元素为行内元素（span、a 等）
    - 块级公式（$$...$$）：LaTeX 代码含换行符，或父元素为块级元素（p、div、center）

    Args:
        html:        原始 body HTML 字符串
        latex_dict:  由 extract_latex_from_asl() 生成的 img_src → latex_code 字典

    Returns:
        替换后的 HTML 字符串。若 beautifulsoup4 不可用或字典为空，原样返回。
    """
    if not HAS_BS4 or not latex_dict:
        return html

    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        img_src = img.get("src", "")
        if img_src not in latex_dict:
            continue

        raw_latex = latex_dict[img_src]
        parent_tag = img.parent.name if img.parent else ""

        # 判断块级 vs 行内：
        #   含换行符的 LaTeX 通常是多行公式（align、matrix 等） → 块级
        #   父元素是块级 HTML 元素 → 块级
        is_block = ("\n" in raw_latex.strip()) or (parent_tag in ("p", "div", "center"))

        if is_block:
            replacement = soup.new_string(f"\n$$\n{raw_latex.strip()}\n$$\n")
        else:
            replacement = soup.new_string(f"${raw_latex.strip()}$")

        img.replace_with(replacement)

    return str(soup)


# ── 图片下载 ──────────────────────────────────────────────────────────────────

def download_images_and_patch_html(
    output_dir_path: str,
    sanitized_title: str,
    html: str,
) -> str:
    """
    下载 HTML 中所有外链图片到本地，并将 src 属性更新为相对路径。

    图片保存位置：<output_dir_path>/attachments/<sanitized_title>_001.jpg
    编号从 001 递增，扩展名根据 HTTP 响应的 Content-Type 自动推断。

    若依赖库（beautifulsoup4 / requests）未安装，直接返回原 HTML 不做修改。

    Args:
        output_dir_path:  当前文档的输出目录（必须已存在）
        sanitized_title:  经过清理的文档标题，用作图片文件名前缀
        html:             待处理的 HTML 字符串

    Returns:
        更新了 img src 属性的 HTML 字符串
    """
    if not HAS_BS4 or not HAS_REQUESTS:
        return html

    bs = BeautifulSoup(html, "html.parser")
    img_tags = bs.find_all("img")
    if not img_tags:
        return html

    # 确保 attachments/ 目录存在
    attachments_dir = os.path.join(output_dir_path, "attachments")
    if not os.path.exists(attachments_dir):
        os.makedirs(attachments_dir)

    for no, image in enumerate(img_tags, start=1):
        src = image.get("src", "")
        if not src:
            continue
        try:
            print(f"  下载图片 ({no}/{len(img_tags)}): {src}")
            resp = http_get(src, timeout=10)
            # 根据 Content-Type 推断扩展名，默认 .jpg
            ext = CONTENT_TYPE_TO_EXTENSION.get(
                resp.headers.get("Content-Type", ""), ".jpg"
            )
            file_name = f"{sanitized_title}_{no:03d}{ext}"
            file_path = os.path.join(attachments_dir, file_name)
            with open(file_path, "wb") as f:
                f.write(resp.content)
            # 将 HTML 中的图片路径改为相对路径，确保离线可用
            image["src"] = f"./attachments/{file_name}"
        except Exception as e:
            print(f"  下载图片失败 ({src}): {e}")

    return str(bs)


# ── 顶层转换函数 ──────────────────────────────────────────────────────────────

def convert_doc_to_markdown(
    doc: dict,
    output_dir_path: str,
    sanitized_title: str,
    download_image: bool,
) -> None:
    """
    将语雀普通文档转换为 Markdown 文件并写入磁盘。

    此函数是本模块的唯一对外接口，按顺序调用各处理步骤：
      1. 从 body_asl 提取 LaTeX 公式字典
      2. 获取正文 HTML（优先 body，其次 body_asl）
      3. 用 LaTeX 源码替换公式图片
      4. 可选：下载外链图片到本地 attachments/ 目录
      5. HTML → Markdown 转换
      6. Markdown 美化（去除冗余空白）
      7. 写入 .md 文件

    Args:
        doc:              语雀文档对象（从文档 JSON 文件的 "doc" 字段解析）
        output_dir_path:  输出目录，必须已存在
        sanitized_title:  经过清理的文档标题，用作 .md 文件名（不含扩展名）
        download_image:   True 表示下载外链图片并更新路径
    """
    # 步骤 1：从语法树（body_asl）中提取 LaTeX 公式源码
    # body_asl 保留了原始公式代码，而 body 中公式已被渲染为图片
    body_asl = doc.get("body_asl", "")
    latex_dict = extract_latex_from_asl(body_asl)

    # 步骤 2：获取正文 HTML
    # body 是完整的渲染 HTML；若 body 为空（极少数情况），回退到 body_asl
    html = doc.get("body") or body_asl

    # 步骤 3：用 LaTeX 源码替换公式图片（仅在提取到公式时执行）
    if latex_dict:
        html = replace_latex_images(html, latex_dict)

    # 步骤 4：（可选）下载外链图片到本地
    if download_image:
        html = download_images_and_patch_html(output_dir_path, sanitized_title, html)

    # 步骤 5 & 6：转换并美化
    markdown_content = pretty_md(html_to_markdown(html))

    # 步骤 7：写入磁盘
    output_path = os.path.join(output_dir_path, sanitized_title + ".md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"  ✓ Markdown: {output_path}")

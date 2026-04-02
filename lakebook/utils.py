# -*- coding: utf-8 -*-
"""
通用工具函数

存放与业务逻辑无关的基础工具，供各模块复用：
- 文件名清理：移除跨平台非法字符
- Markdown 美化：去除冗余空行和行尾空白
- tar 归档解压：提取 .lakebook 压缩包
"""

import os
import tarfile


def sanitize_file_name(name: str) -> str:
    """
    清理文件名，移除或替换在各主流操作系统中不合法的字符。

    以下字符在 Windows / Linux / macOS 的文件系统中禁用或不推荐使用：
      /  \\  ?  *  <  >  |  "  :  （空格）
    本函数将上述字符统一替换为下划线 _，空格也一并替换以避免命令行歧义。

    示例：
      "报告/2024 Q1:总结" → "报告_2024_Q1_总结"

    Args:
        name: 原始文件名（不含目录路径）

    Returns:
        清理后的合法文件名
    """
    illegal_chars = '/\\?*<>|": '
    for ch in illegal_chars:
        name = name.replace(ch, "_")
    return name


def pretty_md(text: str) -> str:
    """
    美化 Markdown 文本输出。

    执行两类清理：
    1. 去除每行末尾的空白字符（trailing whitespace），避免 Markdown
       渲染器将行尾两个空格识别为强制换行（<br>）。
    2. 将连续三个及以上的空行压缩为两个（即保留最多一个空行），
       使段落间距在渲染后保持一致。

    Args:
        text: 原始 Markdown 字符串（通常由 html_to_markdown 生成）

    Returns:
        美化后的 Markdown 字符串
    """
    # 去除每行末尾空白
    lines = [line.rstrip() for line in text.split("\n")]
    output = "\n".join(lines)

    # 反复压缩多余的空行，直到不再有连续三个空行为止
    # 最多迭代 50 次，防止极端情况（实际几次就能收敛）
    for _ in range(50):
        output = output.replace("\n\n\n", "\n\n")
        if "\n\n\n" not in output:
            break

    return output


def extract_tar(tar_file: str, target_dir: str) -> None:
    """
    解压 tar 格式归档文件到目标目录。

    .lakebook 文件本质上是一个未压缩（或 gzip 压缩）的 tar 包，
    内部包含各文档的 JSON 文件和 $meta.json 元数据文件。

    Args:
        tar_file:   tar 文件路径（.lakebook 文件）
        target_dir: 解压目标目录路径（不存在时自动创建）
    """
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    with tarfile.open(tar_file) as tar:
        for name in tar.getnames():
            tar.extract(name, target_dir)

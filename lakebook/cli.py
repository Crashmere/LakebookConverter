# -*- coding: utf-8 -*-
"""
命令行入口

解析命令行参数，收集待处理的 .lakebook 文件，
依次调用 process_single_lakebook() 完成批量转换，
最后汇总输出成功/失败统计。

用法示例：
  # 转换单个文件，输出到 output/ 目录
  python lakebook_converter.py my_book.lakebook output/

  # 同时转换表格文档为 CSV，并下载图片
  python lakebook_converter.py my_book.lakebook output/ --convert-sheets --download-image

  # 表格转换为 Obsidian Sheet Plus 格式
  python lakebook_converter.py my_book.lakebook output/ --convert-sheets --sheet-format sheet

  # 批量处理目录下所有 .lakebook 文件
  python lakebook_converter.py /path/to/exports/ output/
"""

import argparse
import os
import sys

from lakebook.converter import process_single_lakebook


def _collect_lakebook_files(items: list[str]) -> list[str]:
    """
    从命令行参数列表中收集所有合法的 .lakebook 文件路径。

    支持三种输入形式：
    1. 单个 .lakebook 文件路径
    2. 包含 .lakebook 文件的目录（递归查找）
    3. 上述两种混合

    Args:
        items: 命令行传入的路径列表（可以是文件或目录）

    Returns:
        去重后的 .lakebook 文件绝对路径列表
    """
    collected: list[str] = []

    for item in items:
        if os.path.isfile(item):
            if item.endswith(".lakebook"):
                collected.append(item)
            else:
                print(f"跳过非 .lakebook 文件: {item}")

        elif os.path.isdir(item):
            # 递归遍历目录，收集所有 .lakebook 文件
            for root, _dirs, files in os.walk(item):
                for fname in files:
                    if fname.endswith(".lakebook"):
                        collected.append(os.path.join(root, fname))

        else:
            print(f"警告: 路径不存在，跳过: {item}")

    return collected


def main() -> None:
    """
    命令行主入口函数。

    解析参数 → 收集文件 → 批量转换 → 打印统计结果
    """
    parser = argparse.ArgumentParser(
        prog="lakebook_converter",
        description=(
            "语雀 Lakebook 转换工具\n"
            "将 .lakebook 导出文件转换为 Markdown（普通文档）或 CSV/Sheet Plus（表格文档）"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "lakebook",
        nargs="+",
        help="Lakebook 文件路径，可指定多个文件或目录（目录会递归搜索 .lakebook 文件）",
    )
    parser.add_argument(
        "output",
        help="输出根目录路径，每个 lakebook 文件会在此目录下创建对应的子目录",
    )
    parser.add_argument(
        "--download-image",
        action="store_true",
        help="将文档中的外链图片下载到本地 attachments/ 目录（需要安装 requests）",
    )
    parser.add_argument(
        "--convert-sheets",
        action="store_true",
        help="转换表格文档（默认跳过，仅转换普通文档为 Markdown）",
    )
    parser.add_argument(
        "--sheet-format",
        choices=["csv", "sheet"],
        default="csv",
        help=(
            "表格文档的输出格式：\n"
            "  csv   - 通用 CSV 文件，可直接用 Excel 等打开（默认）\n"
            "  sheet - Obsidian Sheet Plus 格式（.md 文件，需安装 excel-pro 插件）"
        ),
    )

    args = parser.parse_args()

    # 确保输出目录存在
    if not os.path.exists(args.output):
        os.makedirs(args.output)

    # 收集所有待处理的 .lakebook 文件
    # 注意：命令行参数 lakebook 是列表，最后一个位置参数 output 已被单独解析
    lakebook_files = _collect_lakebook_files(args.lakebook)

    if not lakebook_files:
        print("错误: 未找到任何 .lakebook 文件，请检查路径是否正确")
        sys.exit(1)

    print(f"找到 {len(lakebook_files)} 个 .lakebook 文件，开始转换...")

    # 逐个处理，统计成功/失败数量
    success_count = 0
    for lakebook_file in lakebook_files:
        if process_single_lakebook(
            lakebook_file,
            args.output,
            args.download_image,
            args.convert_sheets,
            args.sheet_format,
        ):
            success_count += 1

    # 汇总结果
    total = len(lakebook_files)
    failed = total - success_count
    print(f"\n{'='*60}")
    print(f"转换完成：成功 {success_count}/{total} 个文件", end="")
    if failed > 0:
        print(f"，失败 {failed} 个（详见上方错误信息）")
    else:
        print()
    print(f"输出目录: {os.path.abspath(args.output)}")

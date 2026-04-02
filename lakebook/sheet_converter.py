# -*- coding: utf-8 -*-
"""
表格文档 (Sheet) 转换器

负责解析语雀 lakesheet 格式的表格数据，并输出为两种格式：

  1. CSV (.csv)
     通用表格格式，可直接用 Excel、LibreOffice、Python pandas 等打开。

  2. Obsidian Sheet Plus (.md)
     兼容 Obsidian excel-pro / Sheet Plus 插件的 JSON 格式，嵌入 Markdown
     的 ```sheet``` 代码块中，可在 Obsidian 中以电子表格形式显示和编辑。

── lakesheet 格式说明 ─────────────────────────────────────────────────────────

文档 JSON 文件结构（简化）：
{
  "doc": {
    "type":   "Sheet",
    "format": "lakesheet",
    "body":   "{...JSON字符串...}"    <-- 表格数据，二次 JSON 编码
  }
}

body 解析后结构：
{
  "format": "lakesheet",
  "sheet":  "<zlib/gzip 压缩的字节数据>"    <-- 进一步压缩的表格 JSON
}

压缩数据解压后得到一个或多个工作表的 JSON，数据格式：
{
  "data": {
    "0": {                 // 行号（字符串）
      "0": {"v": "姓名"},  // 列号（字符串）→ 单元格对象，v 字段为值
      "1": {"v": "年龄"},
      ...
    },
    "1": {
      "0": {"v": "张三"},
      "1": {"v": 28},
      ...
    },
    ...
  }
}
"""

import csv
import gzip
import json
import os
import random
import string
import traceback
import zlib
from datetime import datetime, timedelta
from typing import List, Optional


# ── lakesheet 解析 ────────────────────────────────────────────────────────────

def parse_lakesheet(body: str) -> Optional[List[List[str]]]:
    """
    解析 lakesheet 格式的表格数据，返回二维字符串列表。

    解析步骤：
    1. 解析 body JSON，验证 format 字段为 "lakesheet"
    2. 获取 sheet 字段（压缩数据字符串）
    3. 依次尝试 zlib → gzip → 直接 JSON 解析
    4. 从解压后的 JSON 中提取 data 字段，构建行列矩阵
    5. 过滤全空行，返回二维字符串列表

    Args:
        body: 文档 JSON 中的 "body" 字段值（字符串形式的 JSON）

    Returns:
        二维字符串列表（行 × 列），解析失败返回 None
    """
    try:
        sheet_data = json.loads(body)

        # 验证格式标识
        if sheet_data.get("format") != "lakesheet":
            return None

        sheet_str = sheet_data.get("sheet", "")
        if not sheet_str:
            return None

        # 压缩数据以字符串形式存储，需先用 latin-1 编码还原字节序列
        # （latin-1 是唯一与 0x00-0xFF 一一对应的编码，不会丢失字节）
        sheet_bytes = sheet_str.encode("latin-1") if isinstance(sheet_str, str) else sheet_str

        # 按顺序尝试三种解压方式
        sheet_json = _decompress_sheet(sheet_bytes, sheet_str)
        if sheet_json is None:
            return None

        # 取第一个工作表（语雀导出通常只有一个）
        if isinstance(sheet_json, list):
            if not sheet_json:
                return None
            sheet_json = sheet_json[0]

        if not isinstance(sheet_json, dict):
            return None

        return _extract_rows_from_sheet_json(sheet_json)

    except Exception as e:
        print(f"解析表格数据失败: {e}")
        traceback.print_exc()
        return None


def _decompress_sheet(sheet_bytes: bytes, sheet_str: str) -> Optional[dict]:
    """
    尝试三种方式解压 sheet 压缩数据，返回解析后的 JSON 对象。

    语雀不同版本可能使用不同压缩方式，因此依次尝试：
      zlib → gzip → 原始 JSON 字符串

    Args:
        sheet_bytes: 用 latin-1 编码得到的字节序列
        sheet_str:   原始字符串（作为最后的 JSON 解析兜底）

    Returns:
        解析后的 Python 对象，失败返回 None
    """
    # 方案一：zlib 解压（lakesheet 最常见的压缩方式）
    try:
        decompressed = zlib.decompress(sheet_bytes)
        return json.loads(decompressed.decode("utf-8"))
    except Exception:
        pass

    # 方案二：gzip 解压
    try:
        decompressed = gzip.decompress(sheet_bytes)
        return json.loads(decompressed.decode("utf-8"))
    except Exception:
        pass

    # 方案三：数据本身就是 JSON 字符串（未压缩）
    try:
        return json.loads(sheet_str)
    except Exception:
        pass

    return None


def _extract_rows_from_sheet_json(sheet_json: dict) -> Optional[List[List[str]]]:
    """
    从解压后的单个工作表 JSON 中提取行列数据。

    数据格式（data 字段）：
      "data": {
        "行号(str)": {
          "列号(str)": {"v": 值, ...},
          ...
        },
        ...
      }

    Args:
        sheet_json: 解压并解析后的单个工作表 JSON 对象

    Returns:
        二维字符串列表，过滤掉全空行；无数据返回 None
    """
    data = sheet_json.get("data", {})
    if not data:
        return None

    # 收集所有数字行号并排序，保证行顺序正确
    row_indices = sorted(int(k) for k in data if k.isdigit())
    if not row_indices:
        return None

    # 找出最大列号，以便统一所有行的列数
    max_col = 0
    for row_idx in row_indices:
        row_data = data.get(str(row_idx), {})
        col_indices = [int(k) for k in row_data if k.isdigit()]
        if col_indices:
            max_col = max(max_col, max(col_indices))

    # 构建二维列表
    all_rows: List[List[str]] = []
    for row_idx in row_indices:
        row_data = data.get(str(row_idx), {})
        row: List[str] = []
        for col_idx in range(max_col + 1):
            cell = row_data.get(str(col_idx), {})
            value = cell.get("v", "")
            # 部分单元格的值是字典（如超链接），优先取 text，其次 url
            if isinstance(value, dict):
                value = value.get("text", value.get("url", ""))
            row.append(str(value) if value else "")

        # 仅保留非全空行
        if any(cell.strip() for cell in row):
            all_rows.append(row)

    return all_rows if all_rows else None


# ── Excel 日期序列号转换 ───────────────────────────────────────────────────────

def _excel_serial_to_date(num_value: float) -> Optional[str]:
    """
    将 Excel 日期序列号转换为 ISO 8601 日期字符串（YYYY-MM-DD）。

    Excel 中日期以数字形式存储，有两种常见格式：

    格式一：以"天"为单位（整数或浮点数，范围约 1~100000）
      起点为 1899-12-30（Excel 的历史 bug：1900 被错误地当成闰年处理，
      实际起点因此比标准 1900-01-01 提前了一天）
      示例：45292 → 2024-01-01

    格式二：以"秒"为单位（大整数，范围约 3×10⁹~5×10⁹）
      同样以 1899-12-30 为起点
      示例：3942259200 → 2024-11-01

    Args:
        num_value: 单元格中的数字值

    Returns:
        "YYYY-MM-DD" 格式的日期字符串，无法转换时返回 None
    """
    excel_epoch = datetime(1899, 12, 30)

    try:
        # 格式一：天数（1 ~ 100000，对应 1900-01-01 到 2173-10-14）
        if 0 < num_value < 100_000:
            dt = excel_epoch + timedelta(days=int(num_value))
            if 1900 <= dt.year <= 2100:
                return dt.strftime("%Y-%m-%d")

        # 格式二：秒数（3B ~ 5B，对应约 2025~2028 年前后）
        elif 3_000_000_000 <= num_value <= 5_000_000_000:
            dt = excel_epoch + timedelta(seconds=int(num_value))
            if 1900 <= dt.year <= 2100:
                return dt.strftime("%Y-%m-%d")

    except (ValueError, OSError, OverflowError):
        pass

    return None


# ── Obsidian Sheet Plus 格式生成 ──────────────────────────────────────────────

def rows_to_sheet_plus_format(
    rows: List[List[str]],
    title: str,
    file_path: str = "",
) -> str:
    """
    将二维字符串列表转换为 Obsidian Sheet Plus 插件格式。

    输出结果是一个 Markdown 文件，包含：
    1. YAML frontmatter（声明此文件由 excel-pro-plugin 解析）
    2. ```sheet``` 代码块，内含符合 Univer 格式的完整 JSON 数据
    3. ```multiSheet``` 代码块（多工作表导航，目前固定为单工作表）

    Univer JSON 结构（简化）：
    {
      "id":         "随机6位ID",
      "sheetOrder": ["随机16位工作表key"],
      "name":       "文件名",
      "styles":     {样式字典},
      "sheets": {
        "工作表key": {
          "cellData": {
            "行号": {"列号": {"s": "样式ID", "v": "值", "t": 类型}}
          },
          ...其他工作表属性
        }
      },
      "resources": [...]    // Univer 插件资源声明
    }

    Args:
        rows:      二维字符串列表，第一行视为表头（使用不同样式）
        title:     文档标题（用于 Univer JSON 的 name 字段）
        file_path: 输出文件路径（可选，用于从路径中提取更简洁的名称）

    Returns:
        完整的 Markdown 字符串，包含 frontmatter 和 sheet/multiSheet 代码块
    """
    if not rows:
        return ""

    # 补齐所有行到相同列数（确保矩形结构）
    max_cols = max(len(row) for row in rows)
    if max_cols == 0:
        return ""
    normalized_rows = [row + [""] * (max_cols - len(row)) for row in rows]

    # ── 生成随机 ID ──────────────────────────────────────────────────────────
    # sheet_id:  工作簿 ID（6位字母数字）
    # sheet_key: 工作表 Key（16位字母数字，用作 sheetOrder 和 sheets 的键）
    chars = string.ascii_letters + string.digits
    sheet_id  = "".join(random.choices(chars, k=6))
    sheet_key = "".join(random.choices(chars, k=16))

    # ── 构建样式 ─────────────────────────────────────────────────────────────
    # 表头样式：Arial 9pt 加粗，带四边细框线
    # 数据样式：Calibri 11pt 普通，无框线
    header_style_id = "".join(random.choices(chars, k=6))
    data_style_id   = "".join(random.choices(chars, k=6))

    styles = {
        header_style_id: _make_cell_style(is_header=True),
        data_style_id:   _make_cell_style(is_header=False),
    }

    # ── 构建 cellData ────────────────────────────────────────────────────────
    cell_data: dict = {}
    for row_idx, row in enumerate(normalized_rows):
        row_cells: dict = {}
        for col_idx, raw_value in enumerate(row):
            cell_str = str(raw_value).strip() if raw_value else ""

            # 非表头的数字单元格尝试转换为日期字符串
            display_value = cell_str
            if cell_str and row_idx > 0:
                try:
                    num = float(cell_str)
                    date_str = _excel_serial_to_date(num)
                    if date_str:
                        display_value = date_str
                except (ValueError, TypeError):
                    pass  # 非数字，保持原值

            # 第一行使用表头样式，其余使用数据样式
            style_id = header_style_id if row_idx == 0 else data_style_id

            row_cells[str(col_idx)] = {
                "s": style_id,       # style ID
                "v": display_value,  # value（展示值）
                "t": 1,              # type：1 = 文本
            }

        if row_cells:
            cell_data[str(row_idx)] = row_cells

    # ── 构建完整工作表 JSON ───────────────────────────────────────────────────
    sheet_data = {
        "id":              sheet_key,
        "name":            "Sheet1",
        "tabColor":        "",
        "hidden":          0,
        # rowCount/columnCount 至少为实际行列数，填充至常见的默认值
        "rowCount":        max(len(normalized_rows), 1000),
        "columnCount":     max(max_cols, 20),
        "zoomRatio":       1,
        "freeze":          {"xSplit": 0, "ySplit": 0, "startRow": -1, "startColumn": -1},
        "scrollTop":       0,
        "scrollLeft":      0,
        "defaultColumnWidth":  88,
        "defaultRowHeight":    24,
        "mergeData":       [],
        "cellData":        cell_data,
        "rowData":         {},
        "columnData":      {},
        "showGridlines":   1,
        "rowHeader":       {"width": 46, "hidden": 0},
        "columnHeader":    {"height": 20, "hidden": 0},
        "rightToLeft":     0,
    }

    # ── 从文件路径中提取简洁名称 ──────────────────────────────────────────────
    name = file_path if file_path else title
    # 取路径最后一段（去目录前缀）
    if "/" in name or "\\" in name:
        name = name.replace("\\", "/").split("/")[-1]
    # 去掉 .md 后缀
    if name.endswith(".md"):
        name = name[:-3]

    # ── 组装顶层 JSON ────────────────────────────────────────────────────────
    sheet_json = {
        "id":         sheet_id,
        "sheetOrder": [sheet_key],
        "name":       name,
        "appVersion": "0.15.0",
        "locale":     "enUS",
        "styles":     styles,
        "sheets":     {sheet_key: sheet_data},
        # resources 列表是 Univer 各插件的资源声明，按规范固定填写
        "resources": [
            {"name": "SHEET_UNIVER_THREAD_COMMENT_PLUGIN",      "data": "{}"},
            {"name": "SHEET_RANGE_PROTECTION_PLUGIN",           "data": ""},
            {"name": "SHEET_AuthzIoMockService_PLUGIN",         "data": "{}"},
            {"name": "SHEET_WORKSHEET_PROTECTION_PLUGIN",       "data": "{}"},
            {"name": "SHEET_WORKSHEET_PROTECTION_POINT_PLUGIN", "data": "{}"},
            {"name": "SHEET_DRAWING_PLUGIN",                    "data": "{}"},
            {"name": "SHEET_HYPER_LINK_PLUGIN",                 "data": f'{{\"{sheet_key}\":[]}}'},
            {"name": "SHEET_CONDITIONAL_FORMATTING_PLUGIN",     "data": ""},
            {"name": "SHEET_OUTGOING_LINK_PLUGIN",              "data": f'{{\"{sheet_key}\":[]}}'},
            {"name": "SHEET_NOTE_PLUGIN",                       "data": "{}"},
            {"name": "SHEET_DEFINED_NAME_PLUGIN",               "data": "{}"},
            {"name": "SHEET_RANGE_THEME_MODEL_PLUGIN",          "data": "{}"},
            {"name": "SHEET_DATA_VALIDATION_PLUGIN",            "data": f'{{\"{sheet_key}\":[]}}'},
            {"name": "SHEET_FILTER_PLUGIN",                     "data": "{}"},
            {"name": "SHEET_TABLE_PLUGIN",                      "data": "{}"},
        ],
    }

    # ── 拼接最终 Markdown 内容 ───────────────────────────────────────────────
    json_str   = json.dumps(sheet_json, ensure_ascii=False, separators=(",", ":"))
    frontmatter     = "---\n\nexcel-pro-plugin: parsed\n\n---"
    sheet_block     = f"```sheet\n{json_str}\n```"
    multisheet_block = (
        '```multiSheet\n'
        '{"tabs":[{"key":"sheet","type":"sheet","label":"Sheet"}],'
        '"defaultActiveKey":"sheet"}\n'
        '```'
    )

    return f"{frontmatter}\n{sheet_block}\n\n{multisheet_block}\n"


def _make_cell_style(is_header: bool) -> dict:
    """
    创建单元格样式字典，符合 Univer 电子表格的样式规范。

    表头样式（is_header=True）：
      - 字体：Arial 9pt 加粗
      - 四边细灰框线（rgb(204,204,204)，线型 1）

    数据样式（is_header=False）：
      - 字体：Calibri 11pt 普通
      - 无框线

    字段说明（Univer 内部格式）：
      ff  font-family     it  italic（0/1）     bl  bold（0/1）
      fs  font-size       ul  underline         st  strikethrough
      cl  color           ht  horizontal-align  vt  vertical-align
      tb  text-wrap       pd  padding           bd  border
      tr  text-rotation   td  text-direction    n   number-format

    Args:
        is_header: True 表示表头样式，False 表示普通数据样式

    Returns:
        符合 Univer 格式的样式字典
    """
    style: dict = {
        "ff": "Arial" if is_header else "Calibri",
        "fs": 9 if is_header else 11,
        "it": 0,                                          # 非斜体
        "bl": 1 if is_header else 0,                     # 表头加粗
        "ul": {"s": 0, "cl": {"rgb": "rgb(0,0,0)"}},     # 无下划线
        "st": {"s": 0, "cl": {"rgb": "rgb(0,0,0)"}},     # 无删除线
        "ol": {"s": 0, "cl": {"rgb": "rgb(0,0,0)"}},     # 无轮廓线
        "tr": {"a": 0, "v": 0},                           # 无文字旋转
        "td": 0,                                          # 从左到右方向
        "cl": {"rgb": "rgb(0,0,0)"},                      # 黑色文字
        "ht": 0,                                          # 左对齐
        "vt": 2,                                          # 垂直居中
        "tb": 1,                                          # 自动换行
        "pd": {"t": 0, "b": 2, "l": 2, "r": 2},          # 内边距
    }

    # 表头行加灰色细框线，增强视觉分隔
    if is_header:
        border = {"cl": {"rgb": "rgb(204,204,204)"}, "s": 1}
        style["bd"] = {"l": border, "r": border, "t": border, "b": border}

    return style


# ── 文件级转换函数 ─────────────────────────────────────────────────────────────

def convert_sheet_to_csv(sheet_file_path: str, output_path: str) -> bool:
    """
    读取语雀 Sheet 文档 JSON 文件，解析后写出为 CSV 文件。

    Args:
        sheet_file_path: 文档 JSON 文件路径（.lakebook 解压后的 <url>.json）
        output_path:     输出 CSV 文件的完整路径

    Returns:
        True 表示转换成功，False 表示失败（body 为空或解析失败）
    """
    try:
        with open(sheet_file_path, "r", encoding="utf-8") as f:
            doc_container = json.loads(f.read())

        body = doc_container.get("doc", {}).get("body", "")
        if not body:
            print(f"  警告: {sheet_file_path} 的 body 为空，跳过")
            return False

        rows = parse_lakesheet(body)
        if not rows:
            print(f"  警告: 无法解析 {sheet_file_path} 的表格数据，跳过")
            return False

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerows(rows)

        print(f"  ✓ CSV: {output_path} ({len(rows)} 行)")
        return True

    except Exception as e:
        print(f"  ✗ 转换 CSV 失败 ({sheet_file_path}): {e}")
        return False


def convert_sheet_to_sheet_plus(
    sheet_file_path: str,
    output_path: str,
    title: str,
) -> bool:
    """
    读取语雀 Sheet 文档 JSON 文件，解析后写出为 Obsidian Sheet Plus 格式。

    Args:
        sheet_file_path: 文档 JSON 文件路径（.lakebook 解压后的 <url>.json）
        output_path:     输出 .md 文件的完整路径
        title:           文档标题（用于 Univer JSON 的 name 字段）

    Returns:
        True 表示转换成功，False 表示失败
    """
    try:
        with open(sheet_file_path, "r", encoding="utf-8") as f:
            doc_container = json.loads(f.read())

        body = doc_container.get("doc", {}).get("body", "")
        if not body:
            print(f"  警告: {sheet_file_path} 的 body 为空，跳过")
            return False

        rows = parse_lakesheet(body)
        if not rows:
            print(f"  警告: 无法解析 {sheet_file_path} 的表格数据，跳过")
            return False

        content = rows_to_sheet_plus_format(rows, title, output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  ✓ Sheet Plus: {output_path} ({len(rows)} 行)")
        return True

    except Exception as e:
        print(f"  ✗ 转换 Sheet Plus 失败 ({sheet_file_path}): {e}")
        traceback.print_exc()
        return False

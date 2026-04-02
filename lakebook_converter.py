#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语雀 Lakebook 转换工具 - 命令行入口

此文件是向后兼容的入口点，实际逻辑已迁移至 lakebook/ 包中。
直接运行此文件或通过 `python lakebook_converter.py` 调用均可正常使用。

完整的模块说明请参阅 lakebook/ 包内各模块的文档字符串。
"""

from lakebook.cli import main

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
身份映射模块。

提供身份标准化功能，包括从 Excel 文件加载身份映射表和将原始身份
标准化为最终身份。本模块从 pipeline/draw_and_to_es.py、
pipeline/identity_juge.py 等管线文件中提取重复的身份映射逻辑，
消除代码重复。

使用示例::

    from utils.identity_mapper import load_identity_mapping, standardize_identity

    # 加载身份映射表
    identity_map = load_identity_mapping()

    # 标准化单个身份
    result = standardize_identity("记者", identity_map)
    # result: ["记者"] 或映射后的值

    # 标准化多个身份（逗号分隔）
    result = standardize_identity("记者,律师", identity_map)
    # result: ["记者", "律师"]（去重后的映射值列表）
"""

from typing import Dict, List, Union

import pandas as pd

from utils.path_resolver import get_path


def load_identity_mapping(excel_filename="final_stanterd.xlsx"):
    # type: (str) -> Dict[str, str]
    """
    从 Excel 文件加载身份标准化映射表。

    读取 Excel 文件中的"原始身份"和"最终身份"两列，
    构建原始身份到最终身份的映射字典。

    Args:
        excel_filename: Excel 文件名，相对于项目根目录的路径，
            默认为 ``final_stanterd.xlsx``

    Returns:
        原始身份 → 最终身份 的映射字典

    Raises:
        FileNotFoundError: 当 Excel 文件不存在时，由 path_resolver 抛出
    """
    excel_path = get_path(excel_filename)
    df = pd.read_excel(excel_path, engine='openpyxl')
    identity_map = dict(zip(df["原始身份"], df["最终身份"]))  # type: Dict[str, str]
    return identity_map


def standardize_identity(identity_raw, identity_map):
    # type: (object, Dict[str, str]) -> Union[str, List[str]]
    """
    将原始身份标准化为最终身份。

    处理规则：
    - 如果输入为 None 或空白字符串，返回空字符串
    - 如果输入为单个身份（不含逗号），返回包含映射值的单元素列表
    - 如果输入为多个身份（逗号分隔），返回去重后的映射值列表
    - 未在映射表中找到的身份默认映射为"其他"

    Args:
        identity_raw: 原始身份值，可以是字符串、列表或 None
        identity_map: 身份映射字典，由 :func:`load_identity_mapping` 返回

    Returns:
        标准化后的身份：空字符串（输入为空时）、单元素列表（单个身份）
        或去重列表（多个身份）
    """
    identity_str = str(identity_raw) if identity_raw is not None else ""
    if not identity_str.strip():
        return ""
    if identity_str == "":
        return ""
    if ',' not in identity_str:
        mapped = identity_map.get(identity_str.strip(), "其他")
        return [mapped]
    items = [x.strip() for x in identity_str.split(',') if x.strip()]
    mapped_list = [identity_map.get(item, "其他") for item in items]
    return list(set(mapped_list))

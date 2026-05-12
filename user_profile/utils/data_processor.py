# -*- coding: utf-8 -*-
"""
数据处理模块。

从原始数据中提取并转换字段，生成符合 ES 入库格式的标准化文档。
本模块从 pipeline/draw_and_to_es.py 和 pipeline/identity_juge.py 中提取，
消除重复代码。
"""

from datetime import datetime
import ujson as json

from typing import Any, Dict

# 字段映射：{ 输入字段名: 输出字段名 }
FIELD_MAPPING = {
    'id': 'uid',
    'sitename': 'site_name',
    'age': 'age',
    'identity': 'identity',
    'identity_standerd': 'identity_standerd',
    'user_name': 'name',
    'verified_reason': 'verified_reason',
    'description': 'description',
    'ip_region': 'ip_region',
    'gender': 'gender',
    'followers_count': 'followers_count',
    'three_new_identity': 'three_new_identity',
    'community': 'community',
}  # type: Dict[str, str]


def data_process(data):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """
    处理原始数据为 ES 入库格式。

    将输入数据按照 FIELD_MAPPING 进行字段映射和类型转换，
    生成包含 id 和 create_time 的标准化文档。

    处理规则：
    - None 值跳过
    - 空的 str/list/dict/set/tuple 跳过
    - list 类型用逗号拼接为字符串
    - dict/set/tuple 类型用 json.dumps 序列化
    - 其他类型转为字符串

    Args:
        data: 原始数据字典，需包含 'id'（uid）和 'sitename' 字段

    Returns:
        处理后的标准化数据字典，包含映射后的字段、复合 id 和 create_time
    """
    processed_data = {}  # type: Dict[str, Any]

    for src_key, dst_key in FIELD_MAPPING.items():
        value = data.get(src_key)

        # 跳过空值：None, "", [], {}, 空字符串等
        if value is None:
            continue
        if isinstance(value, (str, list, dict, set, tuple)) and len(value) == 0:
            continue

        # 类型处理
        if isinstance(value, list):
            processed_value = ",".join(str(item) for item in value)
        elif isinstance(value, (dict, set, tuple)):
            processed_value = json.dumps(value, ensure_ascii=False)
        else:
            processed_value = str(value)

        processed_data[dst_key] = processed_value

    processed_data['id'] = processed_data['site_name'] + '|' + processed_data['uid']
    processed_data['create_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return processed_data

# -*- coding: utf-8 -*-
"""
ScyllaDB字段变化追踪测试脚本
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
from datetime import datetime
from pipeline.draw_and_to_scylla_mq import ScyllaDBHandler

def test_field_changes():
    """测试字段变化追踪功能"""
    
    # 初始化ScyllaDB处理器
    scylla_handler = ScyllaDBHandler()
    
    # 测试数据1 - 初始数据
    test_data_1 = {
        'id': 'test_user_123',
        'sitename': '抖音',
        'user_name': '张三',
        'verified_reason': '个人认证',
        'description': '我是一个外卖员',
        'content': '今天送外卖很累',
        'gender': '男',
        'ip_region': '北京',
        'followers_count': '100',
        'friends_count': '50',
        'identity': ['外卖员'],
        'identity_standerd': ['外卖员'],
        'age': ['25岁'],
        'three_new_identity': '外卖员',
        'community': '外卖行业',
        'url': 'https://test.com/1'
    }
    
    print("=== 测试1: 插入初始数据 ===")
    success = scylla_handler.insert_or_update_data_cookie(test_data_1)
    print(f"插入结果: {success}")
    
    # 测试数据2 - 更新数据（身份变化）
    test_data_2 = {
        'id': 'test_user_123',
        'sitename': '抖音',
        'user_name': '张三',
        'verified_reason': '个人认证',
        'description': '我现在是网约车司机了',  # 描述变化
        'content': '今天开网约车赚了不少',
        'gender': '男',
        'ip_region': '北京',
        'followers_count': '120',  # 粉丝数变化
        'friends_count': '55',     # 关注数变化
        'identity': ['网约车司机'],  # 身份变化
        'identity_standerd': ['网约车司机'],
        'age': ['25岁'],
        'three_new_identity': '网约车司机',  # 三元组身份变化
        'community': '网约车行业',  # 社区变化
        'url': 'https://test.com/2'
    }
    
    print("\n=== 测试2: 更新数据（多个字段变化） ===")
    success = scylla_handler.insert_or_update_data_cookie(test_data_2)
    print(f"更新结果: {success}")
    
    # 测试数据3 - 再次更新（部分字段变化）
    test_data_3 = {
        'id': 'test_user_123',
        'sitename': '抖音',
        'user_name': '张三三',  # 姓名变化
        'verified_reason': '企业认证',  # 认证原因变化
        'description': '我现在是网约车司机了',  # 描述无变化
        'content': '今天开网约车赚了不少',
        'gender': '男',
        'ip_region': '上海',  # 地区变化
        'followers_count': '120',  # 粉丝数无变化
        'friends_count': '60',     # 关注数变化
        'identity': ['网约车司机'],  # 身份无变化
        'identity_standerd': ['网约车司机'],
        'age': ['26岁'],  # 年龄变化
        'three_new_identity': '网约车司机',
        'community': '网约车行业',
        'url': 'https://test.com/3'
    }
    
    print("\n=== 测试3: 再次更新（部分字段变化） ===")
    success = scylla_handler.insert_or_update_data_cookie(test_data_3)
    print(f"更新结果: {success}")
    
    # 查询历史记录
    print("\n=== 查询历史记录 ===")
    composite_id = "test_user_123|抖音"
    
    # 查询身份变化历史
    try:
        query = "SELECT * FROM identity_history WHERE id = ? ORDER BY uptime DESC"
        rows = list(scylla_handler.session.execute(query, (composite_id,)))
        print(f"身份变化历史 ({len(rows)} 条):")
        for row in rows:
            print(f"  时间: {row.uptime}, 值: {row.field_value}")
    except Exception as e:
        print(f"查询身份历史失败: {e}")
    
    # 查询描述变化历史
    try:
        query = "SELECT * FROM description_history WHERE id = ? ORDER BY uptime DESC"
        rows = list(scylla_handler.session.execute(query, (composite_id,)))
        print(f"描述变化历史 ({len(rows)} 条):")
        for row in rows:
            print(f"  时间: {row.uptime}, 值: {row.field_value}")
    except Exception as e:
        print(f"查询描述历史失败: {e}")
    
    # 查询粉丝数变化历史
    try:
        query = "SELECT * FROM followers_count_history WHERE id = ? ORDER BY uptime DESC"
        rows = list(scylla_handler.session.execute(query, (composite_id,)))
        print(f"粉丝数变化历史 ({len(rows)} 条):")
        for row in rows:
            print(f"  时间: {row.uptime}, 值: {row.field_value}")
    except Exception as e:
        print(f"查询粉丝数历史失败: {e}")
    
    # 关闭连接
    scylla_handler.close()
    print("\n测试完成!")

if __name__ == "__main__":
    test_field_changes()
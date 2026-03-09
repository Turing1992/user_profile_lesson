#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
身份自动识别系统测试脚本
"""

import sys
import os
import json
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_database():
    """测试数据库连接和表创建"""
    print("🔍 Testing database connection...")
    try:
        from identity_auto_get.database import IdentityAutoDatabase
        
        db = IdentityAutoDatabase()
        db.create_table()
        print("✅ Database connection and table creation successful")
        
        # 测试插入任务
        task_id = db.insert_task(
            prompt_text="测试提示词",
            match_keywords="测试关键词",
            identity_name="测试身份",
            creator="测试用户"
        )
        print(f"✅ Task insertion successful, ID: {task_id}")
        
        # 测试查询任务
        task = db.get_task_by_id(task_id)
        if task:
            print("✅ Task query successful")
            print(f"   Task details: {task['identity_name']} by {task['creator']}")
        else:
            print("❌ Task query failed")
            
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def test_data_processor():
    """测试数据处理器"""
    print("\n🔍 Testing data processor...")
    try:
        from identity_auto_get.data_processor import DataProcessor
        
        processor = DataProcessor()
        
        # 测试数据获取
        data = processor.data_get("网约车", 5)
        print(f"✅ Data retrieval successful, got {len(data)} records")
        
        # 测试单条数据处理
        if data:
            test_prompt = "测试提示词：判断是否为网约车司机"
            result = processor.process_single_item(test_prompt, data[0])
            print("✅ Single item processing successful")
            print(f"   Result keys: {list(result.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Data processor test failed: {e}")
        return False

def test_llm_integration():
    """测试LLM集成"""
    print("\n🔍 Testing LLM integration...")
    try:
        from utils.opinin_extract import identity_auto
        
        test_prompt = """测试提示词：判断用户身份
        输出格式：{"identity":"身份类别","identity2":"具体身份","log":"判断原因"}"""
        
        test_content = "我是一名网约车司机，每天开滴滴赚钱养家"
        
        result = identity_auto(test_prompt, test_content)
        print("✅ LLM integration successful")
        print(f"   Result: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        return True
        
    except Exception as e:
        print(f"❌ LLM integration test failed: {e}")
        print("   This might be due to API configuration or network issues")
        return False

def test_config():
    """测试配置文件"""
    print("\n🔍 Testing configuration...")
    try:
        from utils.config import sql_config
        from config.config import config
        
        print("✅ SQL config loaded:")
        print(f"   Host: {sql_config.get('host')}")
        print(f"   Database: {sql_config.get('database')}")
        
        print("✅ Main config loaded:")
        print(f"   OpenSearch hosts: {config['ESsearch']['hosts']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def test_directories():
    """测试目录结构"""
    print("\n🔍 Testing directory structure...")
    
    base_dir = Path(__file__).parent
    required_dirs = ['templates', 'static', 'results']
    required_files = ['api.py', 'database.py', 'data_processor.py', 'run.py']
    
    all_good = True
    
    for dir_name in required_dirs:
        dir_path = base_dir / dir_name
        if dir_path.exists():
            print(f"✅ Directory exists: {dir_name}")
        else:
            print(f"❌ Directory missing: {dir_name}")
            all_good = False
    
    for file_name in required_files:
        file_path = base_dir / file_name
        if file_path.exists():
            print(f"✅ File exists: {file_name}")
        else:
            print(f"❌ File missing: {file_name}")
            all_good = False
    
    return all_good

def main():
    """主测试函数"""
    print("🚀 Starting Identity Auto Recognition System Tests\n")
    
    tests = [
        ("Directory Structure", test_directories),
        ("Configuration", test_config),
        ("Database", test_database),
        ("Data Processor", test_data_processor),
        ("LLM Integration", test_llm_integration),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running {test_name} Test")
        print('='*50)
        
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # 总结
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print('='*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:<20} {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! System is ready to use.")
        print("   Run 'python run.py' to start the web interface.")
    else:
        print(f"\n⚠️  {total-passed} test(s) failed. Please check the issues above.")
        print("   Some features may not work properly.")
    
    return passed == total

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
# -*- coding: utf-8 -*-
"""
Oasis系统测试脚本（简化版，不依赖MySQL）
"""
import json
from llm_client import LLMClient
from profile_engine import ProfileEngine


def test_llm_client():
    """测试LLM客户端"""
    print("=" * 60)
    print("测试1: LLM客户端连接")
    print("=" * 60)
    
    client = LLMClient()
    test_prompt = "请用一句话介绍你自己"
    
    print(f"发送测试提示词: {test_prompt}")
    result, response_id, raw_response = client.call(test_prompt)
    
    print(f"\n响应ID: {response_id}")
    print(f"原始响应: {raw_response[:200]}...")
    print(f"解析结果: {result}")
    
    if response_id:
        print("\n✓ LLM客户端测试通过")
        return True
    else:
        print("\n✗ LLM客户端测试失败")
        return False


def test_single_profile():
    """测试单个账号画像推演"""
    print("\n" + "=" * 60)
    print("测试2: 单个账号画像推演")
    print("=" * 60)
    
    # 测试数据
    test_account = {
        "account_id": "test_001",
        "name": "科技小王",
        "identity": "互联网从业者",
        "description": "985毕业，现在某大厂做产品经理，关注AI和Web3",
        "verified_reason": "互联网公司产品经理"
    }
    
    print(f"\n测试账号: {json.dumps(test_account, ensure_ascii=False, indent=2)}")
    print("\n开始推演...")
    
    engine = ProfileEngine()
    
    try:
        result = engine.generate_full_profile(test_account)
        
        print("\n" + "=" * 60)
        print("推演结果摘要:")
        print("=" * 60)
        
        # 打印基础信息
        basic_info = result.get("profile", {}).get("basic_info", {}).get("data", {})
        if basic_info:
            print("\n【基础信息分析】")
            print(f"  真实姓名: {basic_info.get('real_name', 'N/A')}")
            print(f"  性别: {basic_info.get('gender', 'N/A')}")
            print(f"  年龄范围: {basic_info.get('age_range', 'N/A')}")
            print(f"  地域: {basic_info.get('location', 'N/A')}")
            print(f"  职业: {basic_info.get('occupation', 'N/A')}")
            print(f"  教育背景: {basic_info.get('education', 'N/A')}")
            print(f"  置信度: {basic_info.get('confidence', 'N/A')}")
        
        # 打印身份分析
        identity_analysis = result.get("profile", {}).get("identity_analysis", {}).get("data", {})
        if identity_analysis:
            print("\n【身份分析】")
            print(f"  主要身份: {identity_analysis.get('primary_identities', [])}")
            print(f"  隐藏身份: {identity_analysis.get('hidden_identities', [])}")
        
        # 打印行为预测
        behavior = result.get("profile", {}).get("behavior_prediction", {}).get("data", {})
        if behavior:
            print("\n【行为预测】")
            print(f"  活跃时间: {behavior.get('active_time', [])}")
            print(f"  发帖频率: {behavior.get('post_frequency', 'N/A')}")
            print(f"  内容类型: {behavior.get('content_types', [])}")
        
        # 打印风险评估
        risk = result.get("profile", {}).get("risk_assessment", {}).get("data", {})
        if risk:
            print("\n【风险评估】")
            print(f"  综合风险: {risk.get('overall_risk', 'N/A')}")
        
        # 保存完整结果
        output_file = "test_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n完整结果已保存到: {output_file}")
        print("\n✓ 单个账号推演测试通过")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_profile():
    """测试批量账号画像推演（简化版）"""
    print("\n" + "=" * 60)
    print("测试3: 批量账号画像推演（2个账号）")
    print("=" * 60)
    
    test_accounts = [
        {
            "account_id": "test_002",
            "name": "李医生",
            "identity": "医生",
            "description": "三甲医院心内科主治医师，从医10年",
            "verified_reason": "某市人民医院心内科医生"
        },
        {
            "account_id": "test_003",
            "name": "90后宝妈日记",
            "identity": "家长",
            "description": "90后全职妈妈，分享育儿经验和生活日常",
            "verified_reason": "个人账号"
        }
    ]
    
    engine = ProfileEngine()
    results = []
    
    for idx, account in enumerate(test_accounts, 1):
        print(f"\n[{idx}/{len(test_accounts)}] 处理账号: {account['name']}")
        try:
            result = engine.generate_full_profile(account)
            results.append(result)
            print(f"  ✓ 完成")
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            results.append({
                "account_id": account["account_id"],
                "status": "failed",
                "error": str(e)
            })
    
    # 保存批量结果
    output_file = "test_batch_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n批量结果已保存到: {output_file}")
    print("\n✓ 批量推演测试通过")
    return True


def main():
    """主测试函数"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "Oasis 系统测试" + " " * 15 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    tests = [
        ("LLM客户端测试", test_llm_client),
        ("单个账号推演", test_single_profile),
        ("批量账号推演", test_batch_profile)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n✗ {test_name} 异常: {e}")
            results.append((test_name, False))
    
    # 打印测试总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for test_name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"{status} - {test_name}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"\n总计: {passed}/{total} 测试通过")
    print("=" * 60)


if __name__ == "__main__":
    main()

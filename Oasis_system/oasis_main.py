# -*- coding: utf-8 -*-
"""
Oasis系统主程序
"""
import json
import sys
from profile_engine import ProfileEngine


def load_account_data(file_path=None):
    """
    加载账号数据
    
    Args:
        file_path: JSON文件路径，如果为None则使用示例数据
    
    Returns:
        list: 账号数据列表
    """
    if file_path:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        # 示例数据
        return [
            {
                "account_id": "test_001",
                "name": "科技小王",
                "identity": "互联网从业者",
                "description": "985毕业，现在某大厂做产品经理，关注AI和Web3",
                "verified_reason": "互联网公司产品经理"
            },
            {
                "account_id": "test_002",
                "name": "李医生",
                "identity": "医生",
                "description": "三甲医院心内科主治医师，从医10年",
                "verified_reason": "某市人民医院心内科医生"
            }
        ]


def save_results(results, output_path="oasis_results.json"):
    """
    保存分析结果
    
    Args:
        results: 分析结果列表
        output_path: 输出文件路径
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_path}")


def main():
    """主函数"""
    print("=" * 60)
    print("Oasis 账号画像推演系统")
    print("=" * 60)
    print()
    
    # 加载账号数据
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        print(f"从文件加载数据: {input_file}")
        account_list = load_account_data(input_file)
    else:
        print("使用示例数据（可通过命令行参数指定JSON文件）")
        account_list = load_account_data()
    
    print(f"共加载 {len(account_list)} 个账号\n")
    
    # 初始化推演引擎
    engine = ProfileEngine()
    
    # 批量处理
    results = []
    for idx, account_data in enumerate(account_list, 1):
        print(f"[{idx}/{len(account_list)}] 处理账号...")
        try:
            result = engine.generate_full_profile(account_data)
            results.append(result)
        except Exception as e:
            print(f"  错误: {e}")
            results.append({
                "account_id": account_data.get("account_id"),
                "status": "failed",
                "error": str(e)
            })
    
    # 保存结果
    output_file = sys.argv[2] if len(sys.argv) > 2 else "oasis_results.json"
    save_results(results, output_file)
    
    print("\n" + "=" * 60)
    print("分析完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()

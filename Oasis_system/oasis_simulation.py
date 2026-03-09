# -*- coding: utf-8 -*-
"""
OASIS 社交模拟主程序
"""
import json
import sys
import os
from simulation_engine import SimulationEngine
from social_platform import PlatformType


def load_profiles(file_path: str) -> list:
    """加载用户画像数据"""
    if not os.path.exists(file_path):
        print(f"错误: 找不到文件 {file_path}")
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 支持两种格式：列表或单个对象
    if isinstance(data, list):
        return data
    else:
        return [data]


def generate_sample_profiles(count: int = 20) -> list:
    """生成示例用户画像"""
    identities = [
        "互联网从业者", "医生", "教师", "学生", "自媒体博主",
        "程序员", "设计师", "产品经理", "运营", "创业者"
    ]
    
    interests_pool = [
        ["科技", "AI", "编程"],
        ["医疗", "健康", "养生"],
        ["教育", "学习", "成长"],
        ["娱乐", "电影", "音乐"],
        ["美食", "旅游", "摄影"],
        ["体育", "健身", "运动"],
        ["财经", "投资", "理财"],
        ["时尚", "美妆", "穿搭"],
        ["游戏", "电竞", "动漫"],
        ["读书", "写作", "文学"]
    ]
    
    personalities = [
        {"type": "外向", "activity": "高", "sentiment": "积极"},
        {"type": "内向", "activity": "中", "sentiment": "中性"},
        {"type": "外向", "activity": "高", "sentiment": "积极"},
        {"type": "内向", "activity": "低", "sentiment": "消极"},
        {"type": "外向", "activity": "中", "sentiment": "积极"}
    ]
    
    profiles = []
    for i in range(count):
        import random
        identity = random.choice(identities)
        interests = random.choice(interests_pool)
        personality = random.choice(personalities)
        
        profile = {
            "account_id": f"user_{i+1:03d}",
            "user_id": f"user_{i+1:03d}",
            "name": f"{identity}{i+1}",
            "identity": identity,
            "interests": interests,
            "personality": personality,
            "description": f"我是一名{identity}，喜欢{', '.join(interests)}"
        }
        profiles.append(profile)
    
    return profiles


def main():
    """主函数"""
    print("="*60)
    print("OASIS 社交模拟平台")
    print("="*60)
    print()
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        profile_file = sys.argv[1]
        print(f"从文件加载用户画像: {profile_file}")
        profiles = load_profiles(profile_file)
    else:
        print("使用自动生成的示例数据")
        agent_count = int(input("请输入 Agent 数量 (默认20): ") or "20")
        profiles = generate_sample_profiles(agent_count)
    
    if not profiles:
        print("错误: 没有可用的用户画像数据")
        return
    
    # 模拟参数
    steps = int(input("请输入模拟步数 (默认10): ") or "10")
    use_llm = input("是否使用 LLM 决策? (y/n, 默认n): ").lower() == 'y'
    
    db_path = "oasis_simulation.db"
    
    # 删除旧数据库（可选）
    if os.path.exists(db_path):
        delete = input(f"数据库 {db_path} 已存在，是否删除? (y/n, 默认n): ").lower()
        if delete == 'y':
            os.remove(db_path)
            print("已删除旧数据库")
    
    # 初始化模拟引擎
    print("\n初始化模拟引擎...")
    engine = SimulationEngine(
        db_path=db_path,
        platform_type=PlatformType.TWITTER,
        max_workers=10
    )
    
    # 加载 Agent
    engine.load_agents(profiles)
    
    # 运行模拟
    engine.run_simulation(steps=steps, use_llm=use_llm)
    
    # 导出结果
    output_file = "simulation_results.json"
    engine.export_data(output_file)
    
    print("\n模拟完成！")
    print(f"结果已保存到: {output_file}")
    print(f"数据库文件: {db_path}")


if __name__ == "__main__":
    main()

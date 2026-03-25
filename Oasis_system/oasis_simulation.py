# -*- coding: utf-8 -*-
"""
OASIS 社交模拟主程序
支持微博/抖音平台模拟
"""
import json
import sys
import os
import random
from simulation_engine import SimulationEngine
from social_platform import PlatformType


def load_profiles(file_path: str) -> list:
    """加载用户画像数据"""
    if not os.path.exists(file_path):
        print(f"错误: 找不到文件 {file_path}")
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


# 微博风格的身份和兴趣池
WEIBO_IDENTITIES = [
    "互联网从业者", "医生", "教师", "律师", "记者",
    "程序员", "产品经理", "自媒体博主", "公务员", "创业者",
    "大学生", "研究生", "设计师", "金融从业者", "科研人员",
]
WEIBO_INTERESTS_POOL = [
    ["科技", "AI", "互联网"], ["医疗", "健康", "科普"],
    ["教育", "考研", "学习"], ["法律", "维权", "社会"],
    ["财经", "股票", "投资"], ["娱乐", "八卦", "追星"],
    ["时政", "国际", "军事"], ["体育", "足球", "NBA"],
    ["读书", "写作", "历史"], ["美食", "旅游", "生活"],
]

# 抖音风格的身份和兴趣池
DOUYIN_IDENTITIES = [
    "美食博主", "健身教练", "穿搭达人", "知识分享官", "三农创作者",
    "搞笑博主", "旅行达人", "母婴博主", "音乐人", "手工达人",
    "宠物博主", "汽车博主", "游戏主播", "舞蹈达人", "摄影师",
]
DOUYIN_INTERESTS_POOL = [
    ["美食", "探店", "做饭"], ["健身", "减脂", "运动"],
    ["穿搭", "时尚", "美妆"], ["编程", "科技", "知识"],
    ["三农", "乡村", "美食"], ["搞笑", "段子", "日常"],
    ["旅行", "风景", "自驾"], ["育儿", "亲子", "教育"],
    ["音乐", "翻唱", "乐器"], ["手工", "DIY", "创意"],
]


def generate_sample_profiles(count: int = 20, platform: str = "weibo") -> list:
    """生成平台风格的示例用户画像"""
    if platform == "douyin":
        identities = DOUYIN_IDENTITIES
        interests_pool = DOUYIN_INTERESTS_POOL
    else:
        identities = WEIBO_IDENTITIES
        interests_pool = WEIBO_INTERESTS_POOL

    personalities = [
        {"type": "外向", "activity": "高", "sentiment": "积极"},
        {"type": "内向", "activity": "中", "sentiment": "中性"},
        {"type": "外向", "activity": "中", "sentiment": "积极"},
        {"type": "内向", "activity": "低", "sentiment": "中性"},
        {"type": "外向", "activity": "高", "sentiment": "积极"},
    ]

    prefix = "wb" if platform == "weibo" else "dy"
    profiles = []
    for i in range(count):
        identity = random.choice(identities)
        interests = random.choice(interests_pool)
        personality = random.choice(personalities)

        profiles.append({
            "account_id": f"{prefix}_{i+1:03d}",
            "user_id": f"{prefix}_{i+1:03d}",
            "name": f"{identity}{i+1}",
            "identity": identity,
            "interests": interests,
            "personality": personality,
            "description": f"我是一名{identity}，喜欢{', '.join(interests)}",
        })
    return profiles


def main():
    """主函数"""
    print("=" * 60)
    print("OASIS 社交模拟平台（微博/抖音）")
    print("=" * 60)
    print()

    # 选择平台
    print("选择模拟平台:")
    print("  1. 微博 (weibo)")
    print("  2. 抖音 (douyin)")
    platform_choice = input("请选择 (1/2, 默认1): ").strip()
    if platform_choice == "2":
        platform_type = PlatformType.DOUYIN
        platform_str = "douyin"
        platform_cn = "抖音"
    else:
        platform_type = PlatformType.WEIBO
        platform_str = "weibo"
        platform_cn = "微博"

    print(f"\n已选择: [{platform_cn}] 平台\n")

    # 加载画像
    if len(sys.argv) > 1:
        profile_file = sys.argv[1]
        print(f"从文件加载用户画像: {profile_file}")
        profiles = load_profiles(profile_file)
    else:
        print("使用自动生成的示例数据")
        agent_count = int(input("请输入 Agent 数量 (默认20): ") or "20")
        profiles = generate_sample_profiles(agent_count, platform_str)

    if not profiles:
        print("错误: 没有可用的用户画像数据")
        return

    # 模拟参数
    steps = int(input("请输入模拟步数 (默认10): ") or "10")
    use_llm = input("是否使用 LLM 决策? (y/n, 默认n): ").lower() == 'y'

    db_path = f"oasis_{platform_str}_simulation.db"

    if os.path.exists(db_path):
        delete = input(f"数据库 {db_path} 已存在，是否删除? (y/n, 默认y): ").strip().lower()
        if delete != 'n':
            os.remove(db_path)
            print("已删除旧数据库")

    # 初始化并运行
    print(f"\n初始化 [{platform_cn}] 模拟引擎...")
    engine = SimulationEngine(
        db_path=db_path,
        platform_type=platform_type,
        max_workers=10
    )

    engine.load_agents(profiles)
    engine.run_simulation(steps=steps, use_llm=use_llm)

    output_file = f"simulation_{platform_str}_results.json"
    engine.export_data(output_file)

    print(f"\n模拟完成！")
    print(f"结果已保存到: {output_file}")
    print(f"数据库文件: {db_path}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
OASIS 快速测试脚本
验证系统各模块是否正常工作
"""
import os
import sys


def test_imports():
    """测试模块导入"""
    print("测试模块导入...")
    try:
        from social_platform import SocialPlatform, PlatformType
        from agent import SocialAgent, ActionType
        from recommendation import RecommendationSystem
        from simulation_engine import SimulationEngine
        from llm_client import LLMClient
        print("✓ 所有模块导入成功")
        return True
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        return False


def test_platform():
    """测试社交平台"""
    print("\n测试社交平台...")
    try:
        from social_platform import SocialPlatform, PlatformType
        
        # 创建测试数据库
        db_path = "test_platform.db"
        if os.path.exists(db_path):
            os.remove(db_path)
        
        platform = SocialPlatform(db_path, PlatformType.TWITTER)
        
        # 创建用户
        platform.create_user("user1", "测试用户1", "这是测试用户")
        platform.create_user("user2", "测试用户2", "这也是测试用户")
        
        # 创建帖子
        post_id = platform.create_post("user1", "这是一条测试帖子")
        
        # 点赞
        platform.like_post("user2", post_id)
        
        # 关注
        platform.follow_user("user2", "user1")
        
        # 获取统计
        stats = platform.get_statistics()
        
        assert stats['total_users'] == 2
        assert stats['total_posts'] == 1
        assert stats['total_follows'] == 1
        assert stats['total_likes'] == 1
        
        # 清理
        os.remove(db_path)
        
        print("✓ 社交平台测试通过")
        return True
    except Exception as e:
        print(f"✗ 社交平台测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agent():
    """测试 Agent"""
    print("\n测试 Agent...")
    try:
        from agent import SocialAgent, ActionType
        from llm_client import LLMClient
        
        profile = {
            "account_id": "test_agent",
            "name": "测试Agent",
            "identity": "测试用户",
            "interests": ["测试", "开发"],
            "personality": {"type": "外向"},
            "description": "这是一个测试Agent"
        }
        
        agent = SocialAgent("test_agent", profile)
        
        assert agent.agent_id == "test_agent"
        assert agent.username == "测试Agent"
        assert len(agent.interests) == 2
        
        # 测试规则引擎决策
        context = {"feed": [], "trending": []}
        action = agent._rule_based_action(context)
        
        assert "action_type" in action
        assert isinstance(action["action_type"], ActionType)
        
        print("✓ Agent 测试通过")
        return True
    except Exception as e:
        print(f"✗ Agent 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_recommendation():
    """测试推荐系统"""
    print("\n测试推荐系统...")
    try:
        from recommendation import RecommendationSystem
        
        rec_sys = RecommendationSystem()
        
        # 更新用户兴趣
        rec_sys.update_user_interests("user1", ["科技", "AI"])
        
        # 测试帖子
        posts = [
            {"post_id": 1, "content": "今天学习了AI技术", "like_count": 10},
            {"post_id": 2, "content": "美食分享", "like_count": 5},
            {"post_id": 3, "content": "科技新闻报道", "like_count": 8}
        ]
        
        # 基于兴趣推荐
        recommended = rec_sys.recommend_by_interest("user1", posts, limit=2)
        assert len(recommended) <= 2
        
        # 基于热度推荐
        hot_posts = rec_sys.recommend_by_hot_score(posts, limit=2)
        assert len(hot_posts) <= 2
        assert hot_posts[0]["like_count"] >= hot_posts[1]["like_count"]
        
        print("✓ 推荐系统测试通过")
        return True
    except Exception as e:
        print(f"✗ 推荐系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_simulation_engine():
    """测试模拟引擎"""
    print("\n测试模拟引擎...")
    try:
        from simulation_engine import SimulationEngine
        from social_platform import PlatformType
        
        db_path = "test_simulation.db"
        if os.path.exists(db_path):
            os.remove(db_path)
        
        engine = SimulationEngine(db_path, PlatformType.TWITTER)
        
        # 加载测试 Agent
        profiles = [
            {
                "account_id": "agent1",
                "name": "Agent1",
                "identity": "测试用户",
                "interests": ["测试"],
                "personality": {},
                "description": "测试"
            },
            {
                "account_id": "agent2",
                "name": "Agent2",
                "identity": "测试用户",
                "interests": ["测试"],
                "personality": {},
                "description": "测试"
            }
        ]
        
        engine.load_agents(profiles)
        
        assert len(engine.agents) == 2
        
        # 运行一步模拟（使用规则引擎）
        engine.run_simulation(steps=1, use_llm=False)
        
        assert engine.stats["total_steps"] == 1
        
        # 清理
        os.remove(db_path)
        
        print("✓ 模拟引擎测试通过")
        return True
    except Exception as e:
        print(f"✗ 模拟引擎测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("="*60)
    print("OASIS 系统测试")
    print("="*60)
    
    results = []
    
    # 运行测试
    results.append(("模块导入", test_imports()))
    results.append(("社交平台", test_platform()))
    results.append(("Agent系统", test_agent()))
    results.append(("推荐系统", test_recommendation()))
    results.append(("模拟引擎", test_simulation_engine()))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统运行正常。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查错误信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())

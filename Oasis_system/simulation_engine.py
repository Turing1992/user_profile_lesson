# -*- coding: utf-8 -*-
"""
模拟引擎
管理和运行社交媒体模拟
"""
import asyncio
import json
import time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
from agent import SocialAgent, ActionType
from social_platform import SocialPlatform, PlatformType
from recommendation import RecommendationSystem
from llm_client import LLMClient


class SimulationEngine:
    """社交模拟引擎"""
    
    def __init__(self, db_path: str = "oasis_simulation.db", 
                 platform_type: PlatformType = PlatformType.TWITTER,
                 max_workers: int = 10):
        """
        初始化模拟引擎
        
        Args:
            db_path: 数据库路径
            platform_type: 平台类型
            max_workers: 最大并发数
        """
        self.platform = SocialPlatform(db_path, platform_type)
        self.recommendation = RecommendationSystem()
        self.llm_client = LLMClient()
        self.agents: Dict[str, SocialAgent] = {}
        self.max_workers = max_workers
        
        # 统计数据
        self.stats = {
            "total_steps": 0,
            "total_actions": 0,
            "action_counts": {},
            "start_time": None,
            "end_time": None
        }
    
    def load_agents(self, profiles: List[Dict]):
        """
        加载 Agent
        
        Args:
            profiles: 用户画像列表
        """
        print(f"加载 {len(profiles)} 个 Agent...")
        
        for profile in profiles:
            agent_id = profile.get("account_id") or profile.get("user_id")
            if not agent_id:
                continue
            
            # 创建 Agent
            agent = SocialAgent(agent_id, profile, self.llm_client)
            self.agents[agent_id] = agent
            
            # 在平台上创建用户
            self.platform.create_user(
                user_id=agent_id,
                username=agent.username,
                bio=agent.bio,
                profile_data=profile
            )
            
            # 更新推荐系统的兴趣数据
            self.recommendation.update_user_interests(agent_id, agent.interests)
        
        print(f"成功加载 {len(self.agents)} 个 Agent")
    
    def run_simulation(self, steps: int = 10, use_llm: bool = True):
        """
        运行模拟
        
        Args:
            steps: 模拟步数
            use_llm: 是否使用 LLM 决策（False 则使用规则引擎）
        """
        print(f"\n{'='*60}")
        print(f"开始模拟 - 共 {steps} 步，{len(self.agents)} 个 Agent")
        print(f"LLM 决策: {'启用' if use_llm else '禁用（规则引擎）'}")
        print(f"{'='*60}\n")
        
        self.stats["start_time"] = time.time()
        
        for step in range(1, steps + 1):
            print(f"\n--- 第 {step}/{steps} 步 ---")
            step_start = time.time()
            
            # 执行一步模拟
            actions_executed = self._execute_step(use_llm)
            
            step_time = time.time() - step_start
            self.stats["total_steps"] += 1
            self.stats["total_actions"] += actions_executed
            
            # 显示统计
            platform_stats = self.platform.get_statistics()
            print(f"本步执行: {actions_executed} 个行为")
            print(f"平台统计: {platform_stats['total_users']} 用户, "
                  f"{platform_stats['total_posts']} 帖子, "
                  f"{platform_stats['total_likes']} 点赞")
            print(f"耗时: {step_time:.2f}秒")
            
            # 短暂休息
            time.sleep(0.5)
        
        self.stats["end_time"] = time.time()
        self._print_final_stats()
    
    def _execute_step(self, use_llm: bool = True) -> int:
        """执行一步模拟"""
        actions_executed = 0
        
        # 随机选择一部分 Agent 执行行为（模拟真实场景）
        import random
        active_agents = random.sample(
            list(self.agents.values()), 
            min(len(self.agents), max(10, len(self.agents) // 10))
        )
        
        for agent in active_agents:
            try:
                # 获取环境上下文
                context = self._get_agent_context(agent.agent_id)
                
                # Agent 决策
                if use_llm:
                    action = agent.decide_action(context)
                else:
                    action = agent._rule_based_action(context)
                
                # 执行行为
                result = self._execute_action(agent.agent_id, action)
                
                # 记录
                agent.record_action(action, result)
                
                if result:
                    actions_executed += 1
                    action_type = action["action_type"].value
                    self.stats["action_counts"][action_type] = \
                        self.stats["action_counts"].get(action_type, 0) + 1
                
            except Exception as e:
                print(f"Agent {agent.agent_id} 执行失败: {e}")
                continue
        
        return actions_executed
    
    def _get_agent_context(self, agent_id: str) -> Dict:
        """获取 Agent 的环境上下文"""
        # 获取信息流
        feed = self.platform.get_user_feed(agent_id, limit=10)
        
        # 获取热门内容
        trending = self.platform.get_trending_posts(limit=5)
        
        return {
            "feed": feed,
            "trending": trending
        }
    
    def _execute_action(self, agent_id: str, action: Dict) -> bool:
        """执行具体行为"""
        action_type = action["action_type"]
        action_args = action.get("action_args", {})
        
        try:
            if action_type == ActionType.CREATE_POST:
                content = action_args.get("content", "")
                if content:
                    post_id = self.platform.create_post(agent_id, content)
                    return post_id is not None
            
            elif action_type == ActionType.CREATE_COMMENT:
                post_id = action_args.get("post_id")
                content = action_args.get("content", "")
                if post_id and content:
                    comment_id = self.platform.create_post(
                        agent_id, content, content_type="comment", parent_id=post_id
                    )
                    return comment_id is not None
            
            elif action_type == ActionType.LIKE_POST:
                post_id = action_args.get("post_id")
                if post_id:
                    return self.platform.like_post(agent_id, post_id)
            
            elif action_type == ActionType.DISLIKE_POST:
                post_id = action_args.get("post_id")
                if post_id:
                    return self.platform.dislike_post(agent_id, post_id)
            
            elif action_type == ActionType.REPOST:
                post_id = action_args.get("post_id")
                content = action_args.get("content", "转发")
                if post_id:
                    repost_id = self.platform.create_post(
                        agent_id, content, content_type="repost", repost_from=post_id
                    )
                    return repost_id is not None
            
            elif action_type == ActionType.FOLLOW:
                user_id = action_args.get("user_id")
                if user_id and user_id != agent_id:
                    return self.platform.follow_user(agent_id, user_id)
            
            elif action_type == ActionType.UNFOLLOW:
                user_id = action_args.get("user_id")
                if user_id:
                    return self.platform.unfollow_user(agent_id, user_id)
            
            elif action_type == ActionType.MUTE:
                user_id = action_args.get("user_id")
                if user_id:
                    return self.platform.mute_user(agent_id, user_id)
            
            elif action_type == ActionType.SEARCH_POSTS:
                keyword = action_args.get("keyword", "")
                if keyword:
                    results = self.platform.search_posts(keyword)
                    return len(results) > 0
            
            elif action_type == ActionType.SEARCH_USER:
                keyword = action_args.get("keyword", "")
                if keyword:
                    results = self.platform.search_users(keyword)
                    return len(results) > 0
            
            elif action_type in [ActionType.VIEW_FEED, ActionType.VIEW_TRENDING, ActionType.DO_NOTHING]:
                return True
            
            return False
            
        except Exception as e:
            print(f"执行行为失败 {action_type}: {e}")
            return False
    
    def _print_final_stats(self):
        """打印最终统计"""
        total_time = self.stats["end_time"] - self.stats["start_time"]
        
        print(f"\n{'='*60}")
        print("模拟完成 - 统计报告")
        print(f"{'='*60}")
        print(f"总步数: {self.stats['total_steps']}")
        print(f"总行为数: {self.stats['total_actions']}")
        print(f"总耗时: {total_time:.2f}秒")
        print(f"平均每步: {total_time/self.stats['total_steps']:.2f}秒")
        
        print(f"\n行为分布:")
        for action_type, count in sorted(self.stats['action_counts'].items(), 
                                        key=lambda x: x[1], reverse=True):
            percentage = count / self.stats['total_actions'] * 100
            print(f"  {action_type}: {count} ({percentage:.1f}%)")
        
        platform_stats = self.platform.get_statistics()
        print(f"\n平台最终状态:")
        print(f"  用户数: {platform_stats['total_users']}")
        print(f"  帖子数: {platform_stats['total_posts']}")
        print(f"  关注关系: {platform_stats['total_follows']}")
        print(f"  点赞数: {platform_stats['total_likes']}")
        print(f"  评论数: {platform_stats['total_comments']}")
        print(f"{'='*60}\n")
    
    def export_data(self, output_path: str = "simulation_results.json"):
        """导出模拟数据"""
        data = {
            "stats": self.stats,
            "platform_stats": self.platform.get_statistics(),
            "agents": [agent.get_profile_summary() for agent in self.agents.values()]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"数据已导出到: {output_path}")
    
    def get_agent(self, agent_id: str) -> Optional[SocialAgent]:
        """获取指定 Agent"""
        return self.agents.get(agent_id)
    
    def get_all_agents(self) -> List[SocialAgent]:
        """获取所有 Agent"""
        return list(self.agents.values())

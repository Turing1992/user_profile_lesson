# -*- coding: utf-8 -*-
"""
模拟引擎
管理和运行微博/抖音风格的社交媒体模拟
"""
import json
import time
import random
from typing import Dict, List, Optional
from agent import SocialAgent, ActionType
from social_platform import SocialPlatform, PlatformType
from recommendation import RecommendationSystem
from llm_client import LLMClient


class SimulationEngine:
    """社交模拟引擎"""

    def __init__(self, db_path: str = "oasis_simulation.db",
                 platform_type: PlatformType = PlatformType.WEIBO,
                 max_workers: int = 10):
        self.platform = SocialPlatform(db_path, platform_type)
        self.platform_type = platform_type
        self.recommendation = RecommendationSystem()
        self.llm_client = LLMClient()
        self.agents: Dict[str, SocialAgent] = {}
        self.max_workers = max_workers

        # 统计数据
        self.stats = {
            "platform": platform_type.value,
            "total_steps": 0,
            "total_actions": 0,
            "action_counts": {},
            "start_time": None,
            "end_time": None
        }

    def load_agents(self, profiles: List[Dict]):
        """加载 Agent，并初始化社交关系和种子内容"""
        platform_name = {"weibo": "微博", "douyin": "抖音"}.get(
            self.platform_type.value, self.platform_type.value)
        print(f"加载 {len(profiles)} 个 Agent 到 [{platform_name}] 平台...")

        for profile in profiles:
            agent_id = profile.get("account_id") or profile.get("user_id")
            if not agent_id:
                continue

            agent = SocialAgent(
                agent_id, profile, self.llm_client,
                platform=self.platform_type.value
            )
            self.agents[agent_id] = agent

            self.platform.create_user(
                user_id=agent_id,
                username=agent.username,
                bio=agent.bio,
                profile_data=profile
            )

            self.recommendation.update_user_interests(agent_id, agent.interests)

        print(f"成功加载 {len(self.agents)} 个 Agent")

        # --- 初始化社交关系：每个Agent随机关注其他几个人 ---
        agent_ids = list(self.agents.keys())
        if len(agent_ids) >= 2:
            for aid in agent_ids:
                others = [x for x in agent_ids if x != aid]
                # 每人关注 min(3, 全部其他人) 个
                follow_count = min(3, len(others))
                targets = random.sample(others, follow_count)
                for tid in targets:
                    self.platform.follow_user(aid, tid)
            print(f"  初始化关注关系完成（每人关注最多3人）")

        # --- 种子内容：每个Agent发一条初始帖子 ---
        from social_platform import PLATFORM_POST_TEMPLATES
        for aid, agent in self.agents.items():
            templates = PLATFORM_POST_TEMPLATES.get(agent.platform, PLATFORM_POST_TEMPLATES["weibo"])
            template = random.choice(templates)
            interest = random.choice(agent.interests) if agent.interests else "生活"
            content = template.format(interest=interest, identity=agent.identity)
            ctype = "short_video" if self.platform_type == PlatformType.DOUYIN else "post"
            topic = interest if random.random() < 0.4 else None
            self.platform.create_post(aid, content, content_type=ctype, topic=topic)
        print(f"  种子内容初始化完成（每人1条帖子）")

    def run_simulation(self, steps: int = 10, use_llm: bool = True):
        """运行模拟，记录每步快照"""
        platform_name = {"weibo": "微博", "douyin": "抖音"}.get(
            self.platform_type.value, self.platform_type.value)

        print(f"\n{'='*60}")
        print(f"开始模拟 [{platform_name}] - 共 {steps} 步，{len(self.agents)} 个 Agent")
        print(f"LLM 决策: {'启用' if use_llm else '禁用（规则引擎）'}")
        print(f"{'='*60}\n")

        self.stats["start_time"] = time.time()
        self.step_snapshots = []  # 每步快照

        for step in range(1, steps + 1):
            print(f"\n--- 第 {step}/{steps} 步 ---")
            step_start = time.time()

            step_actions = self._execute_step(use_llm)
            actions_executed = len([a for a in step_actions if a["success"]])

            step_time = time.time() - step_start
            self.stats["total_steps"] += 1
            self.stats["total_actions"] += actions_executed

            platform_stats = self.platform.get_statistics()

            # 记录本步快照
            snapshot = {
                "step": step,
                "actions_executed": actions_executed,
                "duration": round(step_time, 2),
                "platform_stats": dict(platform_stats),
                "actions": step_actions,
            }
            self.step_snapshots.append(snapshot)

            print(f"本步执行: {actions_executed} 个行为")

            if self.platform_type == PlatformType.DOUYIN:
                print(f"平台统计: {platform_stats['total_users']} 用户, "
                      f"{platform_stats['total_posts']} 视频, "
                      f"{platform_stats.get('total_plays', 0)} 播放, "
                      f"{platform_stats['total_likes']} 点赞")
            else:
                print(f"平台统计: {platform_stats['total_users']} 用户, "
                      f"{platform_stats['total_posts']} 微博, "
                      f"{platform_stats['total_likes']} 点赞, "
                      f"{platform_stats.get('total_reposts', 0)} 转发")

            print(f"耗时: {step_time:.2f}秒")
            time.sleep(0.3)

        self.stats["end_time"] = time.time()
        self._print_final_stats()

    def _execute_step(self, use_llm: bool = True) -> List[Dict]:
        """执行一步模拟，返回本步所有行为明细"""
        step_actions = []

        # 小规模时全部活跃，大规模时随机选择
        if len(self.agents) <= 20:
            active_agents = list(self.agents.values())
        else:
            active_count = min(len(self.agents), max(10, len(self.agents) // 10))
            active_agents = random.sample(list(self.agents.values()), active_count)

        for agent in active_agents:
            try:
                context = self._get_agent_context(agent.agent_id)

                if use_llm:
                    action = agent.decide_action(context)
                else:
                    action = agent._rule_based_action(context)

                result = self._execute_action(agent.agent_id, action)
                agent.record_action(action, result)

                action_record = {
                    "agent": agent.username,
                    "agent_id": agent.agent_id,
                    "action": action["action_type"].value,
                    "success": bool(result),
                    "reasoning": action.get("reasoning", ""),
                }
                # 记录关键参数
                args = action.get("action_args", {})
                if args.get("content"):
                    action_record["content"] = args["content"][:100]
                if args.get("post_id"):
                    action_record["target_post_id"] = args["post_id"]

                step_actions.append(action_record)

                if result:
                    action_type = action["action_type"].value
                    self.stats["action_counts"][action_type] = \
                        self.stats["action_counts"].get(action_type, 0) + 1

            except Exception as e:
                print(f"Agent {agent.agent_id} 执行失败: {e}")
                step_actions.append({
                    "agent": agent.username, "agent_id": agent.agent_id,
                    "action": "error", "success": False, "error": str(e)
                })
                continue

        return step_actions

    def _get_agent_context(self, agent_id: str) -> Dict:
        """获取 Agent 的环境上下文"""
        feed = self.platform.get_user_feed(agent_id, limit=10)
        trending = self.platform.get_trending_posts(limit=5)
        return {"feed": feed, "trending": trending}

    def _execute_action(self, agent_id: str, action: Dict) -> bool:
        """执行具体行为"""
        action_type = action["action_type"]
        action_args = action.get("action_args", {})

        try:
            # 需要 post_id 的行为：如果 post_id 无效，从 feed/trending 中随机选一个
            if action_type in (ActionType.CREATE_COMMENT, ActionType.LIKE_POST,
                               ActionType.DISLIKE_POST, ActionType.REPOST):
                post_id = action_args.get("post_id")
                if not isinstance(post_id, int) or post_id <= 0:
                    # 尝试从 feed 或 trending 获取一个有效 post_id
                    feed = self.platform.get_user_feed(agent_id, limit=10)
                    if not feed:
                        feed = self.platform.get_trending_posts(limit=5)
                    if feed:
                        action_args["post_id"] = random.choice(feed).get("post_id")
                    else:
                        return False  # 没有任何帖子可以互动

            if action_type == ActionType.CREATE_POST:
                content = action_args.get("content", "")
                if content:
                    topic = action_args.get("topic")
                    # 抖音内容类型为 short_video
                    ctype = "short_video" if self.platform_type == PlatformType.DOUYIN else "post"
                    post_id = self.platform.create_post(
                        agent_id, content, content_type=ctype, topic=topic)
                    return post_id is not None

            elif action_type == ActionType.CREATE_COMMENT:
                post_id = action_args.get("post_id")
                content = action_args.get("content", "")
                if post_id and content:
                    cid = self.platform.create_post(
                        agent_id, content, content_type="comment", parent_id=post_id)
                    return cid is not None

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
                    rid = self.platform.create_post(
                        agent_id, content, content_type="repost", repost_from=post_id)
                    return rid is not None

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
                    return len(self.platform.search_posts(keyword)) > 0

            elif action_type == ActionType.SEARCH_USER:
                keyword = action_args.get("keyword", "")
                if keyword:
                    return len(self.platform.search_users(keyword)) > 0

            elif action_type in (ActionType.VIEW_FEED, ActionType.VIEW_TRENDING,
                                 ActionType.DO_NOTHING):
                return True

            return False

        except Exception as e:
            print(f"执行行为失败 {action_type}: {e}")
            return False

    def _print_final_stats(self):
        """打印最终统计"""
        total_time = self.stats["end_time"] - self.stats["start_time"]
        platform_name = {"weibo": "微博", "douyin": "抖音"}.get(
            self.platform_type.value, self.platform_type.value)

        print(f"\n{'='*60}")
        print(f"[{platform_name}] 模拟完成 - 统计报告")
        print(f"{'='*60}")
        print(f"总步数: {self.stats['total_steps']}")
        print(f"总行为数: {self.stats['total_actions']}")
        print(f"总耗时: {total_time:.2f}秒")
        if self.stats['total_steps'] > 0:
            print(f"平均每步: {total_time/self.stats['total_steps']:.2f}秒")

        if self.stats['total_actions'] > 0:
            print(f"\n行为分布:")
            for action_type, count in sorted(self.stats['action_counts'].items(),
                                             key=lambda x: x[1], reverse=True):
                percentage = count / self.stats['total_actions'] * 100
                print(f"  {action_type}: {count} ({percentage:.1f}%)")

        platform_stats = self.platform.get_statistics()
        print(f"\n平台最终状态:")
        print(f"  用户数: {platform_stats['total_users']}")
        print(f"  内容数: {platform_stats['total_posts']}")
        print(f"  关注关系: {platform_stats['total_follows']}")
        print(f"  点赞数: {platform_stats['total_likes']}")
        print(f"  评论数: {platform_stats['total_comments']}")
        print(f"  转发数: {platform_stats.get('total_reposts', 0)}")

        if self.platform_type == PlatformType.DOUYIN:
            print(f"  总播放量: {platform_stats.get('total_plays', 0)}")
            print(f"  平均完播率: {platform_stats.get('avg_finish_rate', 0)}")

        print(f"{'='*60}\n")

    def export_data(self, output_path: str = "simulation_results.json"):
        """导出模拟数据（含每步快照时间序列）"""
        platform_stats = self.platform.get_statistics()
        data = {
            "stats": self.stats,
            "platform_stats": platform_stats,
            "step_snapshots": getattr(self, 'step_snapshots', []),
            "agents": []
        }
        for agent in self.agents.values():
            summary = agent.get_profile_summary()
            action_breakdown = {}
            for record in agent.action_history:
                if record.get("result"):
                    atype = record["action"]["action_type"].value
                    action_breakdown[atype] = action_breakdown.get(atype, 0) + 1
            summary["action_breakdown"] = action_breakdown
            summary["successful_actions"] = sum(action_breakdown.values())
            data["agents"].append(summary)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"数据已导出到: {output_path}")

    def get_agent(self, agent_id: str) -> Optional[SocialAgent]:
        """获取指定 Agent"""
        return self.agents.get(agent_id)

    def get_all_agents(self) -> List[SocialAgent]:
        """获取所有 Agent"""
        return list(self.agents.values())

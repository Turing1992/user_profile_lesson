# -*- coding: utf-8 -*-
"""
AI Agent 系统
每个 Agent 代表一个社交媒体用户
"""
import json
import random
from typing import Dict, List, Optional
from enum import Enum
from llm_client import LLMClient


class ActionType(Enum):
    """行为类型"""
    CREATE_POST = "create_post"
    CREATE_COMMENT = "create_comment"
    LIKE_POST = "like_post"
    DISLIKE_POST = "dislike_post"
    REPOST = "repost"
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    MUTE = "mute"
    SEARCH_POSTS = "search_posts"
    SEARCH_USER = "search_user"
    VIEW_FEED = "view_feed"
    VIEW_TRENDING = "view_trending"
    DO_NOTHING = "do_nothing"


class SocialAgent:
    """社交媒体 Agent"""
    
    def __init__(self, agent_id: str, profile: Dict, llm_client: LLMClient = None):
        """
        初始化 Agent
        
        Args:
            agent_id: Agent ID
            profile: 用户画像数据
            llm_client: LLM 客户端
        """
        self.agent_id = agent_id
        self.profile = profile
        self.llm_client = llm_client or LLMClient()
        
        # 从画像中提取关键信息
        self.username = profile.get("name", f"user_{agent_id}")
        self.identity = profile.get("identity", "普通用户")
        self.interests = profile.get("interests", [])
        self.personality = profile.get("personality", {})
        self.bio = profile.get("description", "")
        
        # 行为历史
        self.action_history = []
        self.interaction_history = []
    
    def decide_action(self, context: Dict) -> Dict:
        """
        决定下一步行为
        
        Args:
            context: 当前环境上下文（信息流、热门内容等）
        
        Returns:
            dict: 行为决策 {"action_type": ActionType, "action_args": {}}
        """
        # 构建决策 prompt
        prompt = self._build_decision_prompt(context)
        
        # 调用 LLM 决策
        result, _, _ = self.llm_client.call(prompt)
        
        if result:
            return self._parse_action(result)
        else:
            # LLM 失败时使用规则引擎
            return self._rule_based_action(context)
    
    def _build_decision_prompt(self, context: Dict) -> str:
        """构建决策 prompt"""
        feed_posts = context.get("feed", [])
        trending_posts = context.get("trending", [])
        
        feed_summary = "\n".join([
            f"- [{p.get('username')}]: {p.get('content')[:50]}... (赞:{p.get('like_count')}, 评:{p.get('comment_count')})"
            for p in feed_posts[:5]
        ])
        
        trending_summary = "\n".join([
            f"- [{p.get('username')}]: {p.get('content')[:50]}... (热度:{p.get('hot_score', 0)})"
            for p in trending_posts[:3]
        ])
        
        prompt = f"""你是一个社交媒体用户，需要决定下一步行为。

【你的身份】
用户名: {self.username}
身份: {self.identity}
兴趣: {', '.join(self.interests)}
个性: {json.dumps(self.personality, ensure_ascii=False)}

【当前信息流】
{feed_summary if feed_summary else "暂无内容"}

【热门内容】
{trending_summary if trending_summary else "暂无热门"}

【可选行为】
1. create_post - 发布新帖子
2. create_comment - 评论帖子
3. like_post - 点赞帖子
4. repost - 转发帖子
5. follow - 关注用户
6. search_posts - 搜索内容
7. view_trending - 查看热门
8. do_nothing - 什么都不做

请根据你的身份和兴趣，选择一个最合适的行为，并给出具体参数。

返回JSON格式:
{{
    "action_type": "行为类型",
    "action_args": {{
        "content": "如果是发帖/评论，这里是内容",
        "post_id": "如果是评论/点赞/转发，这里是帖子ID",
        "user_id": "如果是关注，这里是用户ID",
        "keyword": "如果是搜索，这里是关键词"
    }},
    "reasoning": "选择这个行为的原因"
}}
"""
        return prompt
    
    def _parse_action(self, llm_result: Dict) -> Dict:
        """解析 LLM 返回的行为"""
        try:
            action_type = llm_result.get("action_type", "do_nothing")
            action_args = llm_result.get("action_args", {})
            
            return {
                "action_type": ActionType(action_type),
                "action_args": action_args,
                "reasoning": llm_result.get("reasoning", "")
            }
        except:
            return {"action_type": ActionType.DO_NOTHING, "action_args": {}}
    
    def _rule_based_action(self, context: Dict) -> Dict:
        """基于规则的行为决策（LLM 失败时的后备方案）"""
        feed_posts = context.get("feed", [])
        trending_posts = context.get("trending", [])
        
        # 随机选择行为
        actions = [
            ActionType.VIEW_FEED,
            ActionType.VIEW_TRENDING,
            ActionType.DO_NOTHING
        ]
        
        # 如果有内容，可以互动
        if feed_posts:
            actions.extend([
                ActionType.LIKE_POST,
                ActionType.CREATE_COMMENT,
                ActionType.REPOST
            ])
        
        # 偶尔发帖
        if random.random() < 0.2:
            actions.append(ActionType.CREATE_POST)
        
        action_type = random.choice(actions)
        action_args = {}
        
        # 根据行为类型生成参数
        if action_type in [ActionType.LIKE_POST, ActionType.CREATE_COMMENT, ActionType.REPOST]:
            if feed_posts:
                post = random.choice(feed_posts)
                action_args["post_id"] = post.get("post_id")
                
                if action_type == ActionType.CREATE_COMMENT:
                    action_args["content"] = self._generate_simple_comment()
        
        elif action_type == ActionType.CREATE_POST:
            action_args["content"] = self._generate_simple_post()
        
        return {
            "action_type": action_type,
            "action_args": action_args,
            "reasoning": "规则引擎决策"
        }
    
    def _generate_simple_post(self) -> str:
        """生成简单的帖子内容"""
        templates = [
            f"今天学习了{random.choice(self.interests or ['新知识'])}，很有收获！",
            f"分享一下关于{random.choice(self.interests or ['生活'])}的想法...",
            f"作为{self.identity}，我觉得...",
            "今天天气不错，心情很好！"
        ]
        return random.choice(templates)
    
    def _generate_simple_comment(self) -> str:
        """生成简单的评论"""
        comments = [
            "说得好！",
            "很有道理",
            "学习了",
            "赞同",
            "有意思",
            "感谢分享"
        ]
        return random.choice(comments)
    
    def record_action(self, action: Dict, result: any):
        """记录行为历史"""
        self.action_history.append({
            "action": action,
            "result": result,
            "timestamp": time.time()
        })
    
    def get_profile_summary(self) -> Dict:
        """获取画像摘要"""
        return {
            "agent_id": self.agent_id,
            "username": self.username,
            "identity": self.identity,
            "interests": self.interests,
            "action_count": len(self.action_history)
        }


import time

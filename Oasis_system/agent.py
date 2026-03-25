# -*- coding: utf-8 -*-
"""
AI Agent 系统
每个 Agent 代表一个社交媒体用户，行为模式根据平台特征差异化
"""
import json
import time
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


# 平台特有的 LLM 决策 prompt
PLATFORM_DECISION_PROMPTS = {
    "weibo": """你是一个微博用户，需要决定下一步行为。

【你的身份】
用户名: {username}
身份: {identity}
兴趣: {interests}
个性: {personality}

【当前微博信息流】
{feed_summary}

【微博热搜】
{trending_summary}

【微博平台特征】
- 你可以发微博（140字以内或长文）、转发并评论、评论、点赞
- 微博有超话、热搜等特色功能
- 转发是微博传播的核心机制，看到好内容要转发
- 热搜话题参与度高

【可选行为】
1. create_post - 发微博
2. create_comment - 评论微博
3. like_post - 点赞
4. repost - 转发微博（可以加评论）
5. follow - 关注用户
6. search_posts - 搜索
7. view_trending - 刷热搜
8. do_nothing - 划走

请根据你的身份和兴趣，选择最合适的行为。

返回JSON格式:
{{
    "action_type": "行为类型",
    "action_args": {{
        "content": "如果是发微博/评论/转发，这里是内容（微博风格）",
        "post_id": "如果是评论/点赞/转发，这里是帖子ID",
        "user_id": "如果是关注，这里是用户ID",
        "keyword": "如果是搜索，这里是关键词",
        "topic": "如果是发微博，可以带话题标签"
    }},
    "reasoning": "选择这个行为的原因"
}}""",

    "douyin": """你是一个抖音用户，需要决定下一步行为。

【你的身份】
用户名: {username}
身份: {identity}
兴趣: {interests}
个性: {personality}

【推荐页内容】
{feed_summary}

【抖音热榜】
{trending_summary}

【抖音平台特征】
- 你主要是刷短视频，双击点赞是最常见的互动
- 发视频需要拍摄/剪辑，频率比刷视频低很多
- 评论区文化活跃，喜欢玩梗和互动
- 算法推荐为主，不需要主动搜索就能看到感兴趣的内容
- 看到喜欢的创作者会关注

【可选行为】
1. create_post - 发布短视频（写视频描述和标签）
2. create_comment - 评论视频
3. like_post - 双击点赞
4. repost - 分享视频
5. follow - 关注创作者
6. search_posts - 搜索
7. view_trending - 看热榜
8. do_nothing - 划走看下一个

请根据你的身份和兴趣，选择最合适的行为。

返回JSON格式:
{{
    "action_type": "行为类型",
    "action_args": {{
        "content": "如果是发视频，这里是视频描述（抖音风格，带#话题标签）",
        "post_id": "如果是评论/点赞/分享，这里是视频ID",
        "user_id": "如果是关注，这里是用户ID",
        "keyword": "如果是搜索，这里是关键词"
    }},
    "reasoning": "选择这个行为的原因"
}}""",
}


class SocialAgent:
    """社交媒体 Agent"""

    def __init__(self, agent_id: str, profile: Dict,
                 llm_client: LLMClient = None, platform: str = "weibo"):
        self.agent_id = agent_id
        self.profile = profile
        self.llm_client = llm_client or LLMClient()
        self.platform = platform

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
        """决定下一步行为（LLM 决策）"""
        prompt = self._build_decision_prompt(context)
        result, _, _ = self.llm_client.call(prompt)

        if result:
            return self._parse_action(result)
        else:
            return self._rule_based_action(context)

    def _build_decision_prompt(self, context: Dict) -> str:
        """构建平台特定的决策 prompt"""
        feed_posts = context.get("feed", [])
        trending_posts = context.get("trending", [])

        if self.platform == "douyin":
            feed_summary = "\n".join([
                f"- [{p.get('username')}]: {p.get('content')[:50]}... "
                f"(播放:{p.get('play_count', 0)}, 赞:{p.get('like_count')}, 评:{p.get('comment_count')})"
                for p in feed_posts[:5]
            ])
            trending_summary = "\n".join([
                f"- [{p.get('username')}]: {p.get('content')[:50]}... (热度:{p.get('hot_score', 0)})"
                for p in trending_posts[:3]
            ])
        else:
            feed_summary = "\n".join([
                f"- [{p.get('username')}]: {p.get('content')[:50]}... "
                f"(转:{p.get('repost_count', 0)}, 评:{p.get('comment_count')}, 赞:{p.get('like_count')})"
                for p in feed_posts[:5]
            ])
            trending_summary = "\n".join([
                f"- [{p.get('username')}]: {p.get('content')[:50]}... (热度:{p.get('hot_score', 0)})"
                for p in trending_posts[:3]
            ])

        template = PLATFORM_DECISION_PROMPTS.get(self.platform, PLATFORM_DECISION_PROMPTS["weibo"])

        return template.format(
            username=self.username,
            identity=self.identity,
            interests=', '.join(self.interests),
            personality=json.dumps(self.personality, ensure_ascii=False),
            feed_summary=feed_summary if feed_summary else "暂无内容",
            trending_summary=trending_summary if trending_summary else "暂无热门",
        )

    def _parse_action(self, llm_result: Dict) -> Dict:
        """解析 LLM 返回的行为，校验并修正参数"""
        try:
            action_type = llm_result.get("action_type", "do_nothing")
            action_args = llm_result.get("action_args", {})

            # 校验 post_id：LLM 经常返回用户名或无效字符串，必须是正整数
            if "post_id" in action_args:
                try:
                    pid = int(action_args["post_id"])
                    if pid > 0:
                        action_args["post_id"] = pid
                    else:
                        action_args.pop("post_id", None)
                except (ValueError, TypeError):
                    # LLM 返回了非数字的 post_id（如 "@用户名"），移除
                    action_args.pop("post_id", None)

            return {
                "action_type": ActionType(action_type),
                "action_args": action_args,
                "reasoning": llm_result.get("reasoning", "")
            }
        except:
            return {"action_type": ActionType.DO_NOTHING, "action_args": {}}

    def _rule_based_action(self, context: Dict) -> Dict:
        """基于规则的平台差异化行为决策"""
        from social_platform import PLATFORM_BEHAVIOR_WEIGHTS, PLATFORM_POST_TEMPLATES, PLATFORM_COMMENT_TEMPLATES

        feed_posts = context.get("feed", [])
        weights = PLATFORM_BEHAVIOR_WEIGHTS.get(self.platform, PLATFORM_BEHAVIOR_WEIGHTS["weibo"])

        # 根据平台权重选择行为
        available_actions = []
        action_weights = []

        for action_name, weight in weights.items():
            action_enum = ActionType(action_name)
            # 需要有内容才能互动
            if action_enum in (ActionType.LIKE_POST, ActionType.CREATE_COMMENT,
                               ActionType.REPOST) and not feed_posts:
                continue
            available_actions.append(action_enum)
            action_weights.append(weight)

        # 归一化权重
        total = sum(action_weights)
        action_weights = [w / total for w in action_weights]

        action_type = random.choices(available_actions, weights=action_weights, k=1)[0]
        action_args = {}

        # 根据行为类型生成参数
        if action_type in (ActionType.LIKE_POST, ActionType.CREATE_COMMENT, ActionType.REPOST):
            if feed_posts:
                post = random.choice(feed_posts)
                action_args["post_id"] = post.get("post_id")

                if action_type == ActionType.CREATE_COMMENT:
                    comments = PLATFORM_COMMENT_TEMPLATES.get(self.platform, PLATFORM_COMMENT_TEMPLATES["weibo"])
                    action_args["content"] = random.choice(comments)

                if action_type == ActionType.REPOST and self.platform == "weibo":
                    action_args["content"] = random.choice([
                        "转发", "转发学习", "马克", "//@" + post.get("username", ""),
                        f"说得好 //@{post.get('username', '')}",
                    ])

        elif action_type == ActionType.CREATE_POST:
            templates = PLATFORM_POST_TEMPLATES.get(self.platform, PLATFORM_POST_TEMPLATES["weibo"])
            template = random.choice(templates)
            interest = random.choice(self.interests) if self.interests else "生活"
            action_args["content"] = template.format(interest=interest, identity=self.identity)

            # 微博带话题
            if self.platform == "weibo" and random.random() < 0.4:
                action_args["topic"] = interest

        elif action_type == ActionType.FOLLOW:
            # 从信息流中随机关注一个人，如果信息流为空则跳过
            if feed_posts:
                post = random.choice(feed_posts)
                uid = post.get("user_id")
                if uid:
                    action_args["user_id"] = uid
                else:
                    # 没有有效user_id，改为发帖
                    action_type = ActionType.CREATE_POST
                    templates = PLATFORM_POST_TEMPLATES.get(self.platform, PLATFORM_POST_TEMPLATES["weibo"])
                    template = random.choice(templates)
                    interest = random.choice(self.interests) if self.interests else "生活"
                    action_args["content"] = template.format(interest=interest, identity=self.identity)
            else:
                # 信息流为空，改为发帖
                action_type = ActionType.CREATE_POST
                templates = PLATFORM_POST_TEMPLATES.get(self.platform, PLATFORM_POST_TEMPLATES["weibo"])
                template = random.choice(templates)
                interest = random.choice(self.interests) if self.interests else "生活"
                action_args["content"] = template.format(interest=interest, identity=self.identity)

        elif action_type == ActionType.SEARCH_POSTS:
            if self.interests:
                action_args["keyword"] = random.choice(self.interests)

        return {
            "action_type": action_type,
            "action_args": action_args,
            "reasoning": f"规则引擎决策 ({self.platform})"
        }

    def record_action(self, action: Dict, result):
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
            "platform": self.platform,
            "action_count": len(self.action_history)
        }

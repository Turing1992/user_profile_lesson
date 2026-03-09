# -*- coding: utf-8 -*-
"""
推荐系统
基于兴趣和热度的内容推荐
"""
import random
from typing import List, Dict, Set
from collections import Counter


class RecommendationSystem:
    """推荐系统"""
    
    def __init__(self):
        self.user_interests = {}  # user_id -> interests
        self.user_interactions = {}  # user_id -> [post_ids]
    
    def update_user_interests(self, user_id: str, interests: List[str]):
        """更新用户兴趣"""
        self.user_interests[user_id] = interests
    
    def record_interaction(self, user_id: str, post_id: int):
        """记录用户互动"""
        if user_id not in self.user_interactions:
            self.user_interactions[user_id] = []
        self.user_interactions[user_id].append(post_id)
    
    def recommend_by_interest(self, user_id: str, posts: List[Dict], limit: int = 20) -> List[Dict]:
        """
        基于兴趣的推荐
        
        Args:
            user_id: 用户ID
            posts: 候选帖子列表
            limit: 返回数量
        
        Returns:
            推荐的帖子列表
        """
        user_interests = self.user_interests.get(user_id, [])
        
        if not user_interests:
            # 没有兴趣数据，返回随机推荐
            return random.sample(posts, min(limit, len(posts)))
        
        # 计算每个帖子的相关性分数
        scored_posts = []
        for post in posts:
            score = self._calculate_interest_score(post, user_interests)
            scored_posts.append((score, post))
        
        # 按分数排序
        scored_posts.sort(key=lambda x: x[0], reverse=True)
        
        return [post for _, post in scored_posts[:limit]]
    
    def recommend_by_hot_score(self, posts: List[Dict], limit: int = 20) -> List[Dict]:
        """
        基于热度的推荐
        
        Args:
            posts: 候选帖子列表
            limit: 返回数量
        
        Returns:
            推荐的帖子列表
        """
        # 计算热度分数
        scored_posts = []
        for post in posts:
            hot_score = self._calculate_hot_score(post)
            scored_posts.append((hot_score, post))
        
        # 按热度排序
        scored_posts.sort(key=lambda x: x[0], reverse=True)
        
        return [post for _, post in scored_posts[:limit]]
    
    def recommend_hybrid(self, user_id: str, posts: List[Dict], limit: int = 20, 
                        interest_weight: float = 0.6) -> List[Dict]:
        """
        混合推荐（兴趣 + 热度）
        
        Args:
            user_id: 用户ID
            posts: 候选帖子列表
            limit: 返回数量
            interest_weight: 兴趣权重（0-1）
        
        Returns:
            推荐的帖子列表
        """
        user_interests = self.user_interests.get(user_id, [])
        hot_weight = 1 - interest_weight
        
        # 计算综合分数
        scored_posts = []
        for post in posts:
            interest_score = self._calculate_interest_score(post, user_interests)
            hot_score = self._calculate_hot_score(post)
            
            final_score = interest_score * interest_weight + hot_score * hot_weight
            scored_posts.append((final_score, post))
        
        # 按分数排序
        scored_posts.sort(key=lambda x: x[0], reverse=True)
        
        return [post for _, post in scored_posts[:limit]]
    
    def _calculate_interest_score(self, post: Dict, user_interests: List[str]) -> float:
        """计算兴趣匹配分数"""
        if not user_interests:
            return 0.0
        
        content = post.get("content", "").lower()
        
        # 计算关键词匹配数
        matches = sum(1 for interest in user_interests if interest.lower() in content)
        
        # 归一化分数
        score = matches / len(user_interests)
        
        return score
    
    def _calculate_hot_score(self, post: Dict) -> float:
        """计算热度分数"""
        like_count = post.get("like_count", 0)
        comment_count = post.get("comment_count", 0)
        repost_count = post.get("repost_count", 0)
        view_count = post.get("view_count", 0)
        
        # 加权计算热度
        hot_score = (
            like_count * 1.0 +
            comment_count * 2.0 +
            repost_count * 3.0 +
            view_count * 0.1
        )
        
        # 时间衰减（简化版）
        # 实际应该根据 created_at 计算
        
        return hot_score
    
    def recommend_users_to_follow(self, user_id: str, candidate_users: List[Dict], 
                                  limit: int = 10) -> List[Dict]:
        """
        推荐关注的用户
        
        Args:
            user_id: 用户ID
            candidate_users: 候选用户列表
            limit: 返回数量
        
        Returns:
            推荐的用户列表
        """
        user_interests = self.user_interests.get(user_id, [])
        
        # 计算用户相似度
        scored_users = []
        for candidate in candidate_users:
            if candidate.get("user_id") == user_id:
                continue
            
            score = self._calculate_user_similarity(user_interests, candidate)
            scored_users.append((score, candidate))
        
        # 按分数排序
        scored_users.sort(key=lambda x: x[0], reverse=True)
        
        return [user for _, user in scored_users[:limit]]
    
    def _calculate_user_similarity(self, user_interests: List[str], candidate: Dict) -> float:
        """计算用户相似度"""
        # 基于简介和画像数据计算相似度
        bio = candidate.get("bio", "").lower()
        
        if not user_interests:
            # 基于粉丝数
            return candidate.get("followers_count", 0) * 0.01
        
        # 兴趣匹配
        matches = sum(1 for interest in user_interests if interest.lower() in bio)
        interest_score = matches / len(user_interests)
        
        # 影响力分数
        influence_score = min(candidate.get("followers_count", 0) / 1000, 1.0)
        
        # 综合分数
        return interest_score * 0.7 + influence_score * 0.3

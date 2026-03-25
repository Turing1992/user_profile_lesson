# -*- coding: utf-8 -*-
"""推荐系统（轻量 stub）"""


class RecommendationSystem:
    """简易推荐系统，记录用户兴趣"""

    def __init__(self):
        self.user_interests = {}

    def update_user_interests(self, user_id: str, interests: list):
        self.user_interests[user_id] = interests

    def get_recommendations(self, user_id: str, count: int = 5):
        return []

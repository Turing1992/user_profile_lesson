# -*- coding: utf-8 -*-
"""
社交平台模拟环境
支持微博风格和抖音风格的社交媒体平台模拟
"""
import time
import json
import sqlite3
import random
from datetime import datetime
from typing import Dict, List, Optional, Set
from enum import Enum


class PlatformType(Enum):
    """平台类型"""
    TWITTER = "twitter"
    REDDIT = "reddit"
    WEIBO = "weibo"
    DOUYIN = "douyin"


class ContentType(Enum):
    """内容类型"""
    POST = "post"
    COMMENT = "comment"
    REPOST = "repost"
    # 微博特有
    LONG_POST = "long_post"       # 微博长文
    SUPER_TOPIC = "super_topic"   # 超话帖子
    # 抖音特有
    SHORT_VIDEO = "short_video"   # 短视频
    LIVE_CLIP = "live_clip"       # 直播切片
    PHOTO_POST = "photo_post"     # 图文


# 平台行为权重配置：不同平台上各行为的自然发生概率不同
PLATFORM_BEHAVIOR_WEIGHTS = {
    "weibo": {
        "create_post": 0.15,
        "create_comment": 0.15,
        "like_post": 0.20,
        "repost": 0.15,        # 微博转发文化很强
        "follow": 0.05,
        "search_posts": 0.08,
        "view_trending": 0.12,  # 刷热搜是高频行为
        "do_nothing": 0.10,
    },
    "douyin": {
        "create_post": 0.08,    # 抖音发视频门槛高，频率低
        "create_comment": 0.12,
        "like_post": 0.30,      # 抖音双击点赞是最高频行为
        "repost": 0.05,         # 抖音转发相对少
        "follow": 0.08,
        "search_posts": 0.07,
        "view_trending": 0.10,
        "do_nothing": 0.20,     # 刷视频不互动的比例高
    },
}

# 平台内容模板
PLATFORM_POST_TEMPLATES = {
    "weibo": [
        "今天聊聊{interest}这个话题，我觉得...",
        "分享一个关于{interest}的观点：作为{identity}，我认为...",
        "刚看到一条关于{interest}的新闻，说几句自己的看法",
        "#热门话题# 关于{interest}，大家怎么看？",
        "作为一个{identity}，今天想和大家聊聊{interest}",
        "[长文] 深度分析：{interest}的现状与未来趋势",
        "转发微博：这个观点我非常认同 //@原博主",
    ],
    "douyin": [
        "#{interest} 今天给大家分享一个小技巧",
        "作为{identity}，教你3个{interest}的实用方法",
        "#{interest} 这个知识点99%的人都不知道",
        "一分钟带你了解{interest}的核心要点",
        "#{identity}日常 今天的工作内容分享",
        "关于{interest}，评论区告诉我你们的想法",
        "挑战：{interest}相关的冷知识你知道几个？",
    ],
}

PLATFORM_COMMENT_TEMPLATES = {
    "weibo": [
        "说得好！", "转发学习", "马克一下", "有道理",
        "博主说得对", "长知识了", "支持！", "同意",
        "这个观点很新颖", "收藏了", "哈哈哈哈",
        "emmm有不同看法", "顶上去让更多人看到",
    ],
    "douyin": [
        "学到了", "太强了", "收藏了", "关注了",
        "第一", "哈哈哈笑死", "真的假的", "厉害",
        "求更新", "催更", "同款在哪买", "坐标哪里",
        "这也太绝了", "建议全网推广", "爷青回",
    ],
}


class SocialPlatform:
    """社交平台环境"""

    def __init__(self, db_path: str = "oasis_simulation.db",
                 platform_type: PlatformType = PlatformType.WEIBO):
        self.db_path = db_path
        self.platform_type = platform_type
        self.init_database()

    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                bio TEXT,
                profile_data TEXT,
                verified_type INTEGER DEFAULT -1,
                followers_count INTEGER DEFAULT 0,
                following_count INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                total_liked INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 帖子/内容表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                content_type TEXT DEFAULT 'post',
                parent_id INTEGER,
                repost_from INTEGER,
                topic TEXT,
                like_count INTEGER DEFAULT 0,
                dislike_count INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                repost_count INTEGER DEFAULT 0,
                view_count INTEGER DEFAULT 0,
                share_count INTEGER DEFAULT 0,
                play_count INTEGER DEFAULT 0,
                finish_rate REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # 关注关系表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS follows (
                follower_id TEXT NOT NULL,
                following_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (follower_id, following_id),
                FOREIGN KEY (follower_id) REFERENCES users(user_id),
                FOREIGN KEY (following_id) REFERENCES users(user_id)
            )
        """)

        # 互动表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                user_id TEXT NOT NULL,
                post_id INTEGER NOT NULL,
                interaction_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, post_id, interaction_type),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (post_id) REFERENCES posts(post_id)
            )
        """)

        # 屏蔽表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id TEXT NOT NULL,
                muted_user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, muted_user_id)
            )
        """)

        # 热搜/热门话题表（微博特有，但抖音也有热榜）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trending_topics (
                topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                hot_score REAL DEFAULT 0,
                post_count INTEGER DEFAULT 0,
                platform TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_topic ON posts(topic)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows(follower_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_follows_following ON follows(following_id)")

        conn.commit()
        conn.close()

    def create_user(self, user_id: str, username: str, bio: str = "",
                    profile_data: dict = None, verified_type: int = -1):
        """创建用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, bio, profile_data, verified_type)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, bio, json.dumps(profile_data or {}), verified_type))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def create_post(self, user_id: str, content: str, content_type: str = "post",
                    parent_id: int = None, repost_from: int = None,
                    topic: str = None) -> Optional[int]:
        """创建帖子/视频/评论/转发"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # 抖音内容自动模拟播放数据
            play_count = 0
            finish_rate = 0.0
            view_count = 0
            if self.platform_type == PlatformType.DOUYIN and content_type in ("post", "short_video"):
                play_count = random.randint(500, 50000)
                finish_rate = round(random.uniform(0.15, 0.85), 2)
                view_count = play_count
            elif self.platform_type == PlatformType.WEIBO:
                view_count = random.randint(100, 10000)

            cursor.execute("""
                INSERT INTO posts (user_id, content, content_type, parent_id,
                                   repost_from, topic, play_count, finish_rate, view_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, content, content_type, parent_id, repost_from,
                  topic, play_count, finish_rate, view_count))

            post_id = cursor.lastrowid

            cursor.execute("UPDATE users SET posts_count = posts_count + 1 WHERE user_id = ?",
                           (user_id,))

            if parent_id:
                cursor.execute("UPDATE posts SET comment_count = comment_count + 1 WHERE post_id = ?",
                               (parent_id,))
            if repost_from:
                cursor.execute("UPDATE posts SET repost_count = repost_count + 1 WHERE post_id = ?",
                               (repost_from,))

            conn.commit()
            return post_id
        except Exception as e:
            print(f"创建内容失败: {e}")
            return None
        finally:
            conn.close()

    def like_post(self, user_id: str, post_id: int) -> bool:
        """点赞"""
        return self._interact(user_id, post_id, "like")

    def dislike_post(self, user_id: str, post_id: int) -> bool:
        """点踩（微博没有，抖音长按不喜欢）"""
        return self._interact(user_id, post_id, "dislike")

    def _interact(self, user_id: str, post_id: int, interaction_type: str) -> bool:
        """通用互动方法"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO interactions (user_id, post_id, interaction_type)
                VALUES (?, ?, ?)
            """, (user_id, post_id, interaction_type))

            if cursor.rowcount > 0:
                if interaction_type == "like":
                    cursor.execute("UPDATE posts SET like_count = like_count + 1 WHERE post_id = ?",
                                   (post_id,))
                    # 更新作者的总获赞数
                    cursor.execute("""
                        UPDATE users SET total_liked = total_liked + 1
                        WHERE user_id = (SELECT user_id FROM posts WHERE post_id = ?)
                    """, (post_id,))
                elif interaction_type == "dislike":
                    cursor.execute("UPDATE posts SET dislike_count = dislike_count + 1 WHERE post_id = ?",
                                   (post_id,))
                conn.commit()
                return True
            return False
        finally:
            conn.close()

    def follow_user(self, follower_id: str, following_id: str) -> bool:
        """关注用户"""
        if follower_id == following_id:
            return False
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO follows (follower_id, following_id)
                VALUES (?, ?)
            """, (follower_id, following_id))
            if cursor.rowcount > 0:
                cursor.execute("UPDATE users SET following_count = following_count + 1 WHERE user_id = ?",
                               (follower_id,))
                cursor.execute("UPDATE users SET followers_count = followers_count + 1 WHERE user_id = ?",
                               (following_id,))
                conn.commit()
                return True
            return False
        finally:
            conn.close()

    def unfollow_user(self, follower_id: str, following_id: str) -> bool:
        """取消关注"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM follows WHERE follower_id = ? AND following_id = ?",
                           (follower_id, following_id))
            if cursor.rowcount > 0:
                cursor.execute("UPDATE users SET following_count = following_count - 1 WHERE user_id = ?",
                               (follower_id,))
                cursor.execute("UPDATE users SET followers_count = followers_count - 1 WHERE user_id = ?",
                               (following_id,))
                conn.commit()
                return True
            return False
        finally:
            conn.close()

    def mute_user(self, user_id: str, muted_user_id: str) -> bool:
        """屏蔽用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO mutes (user_id, muted_user_id) VALUES (?, ?)
            """, (user_id, muted_user_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_user_feed(self, user_id: str, limit: int = 20) -> List[Dict]:
        """
        获取用户信息流
        微博：关注的人的内容，按时间倒序
        抖音：算法推荐为主，关注内容为辅
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            if self.platform_type == PlatformType.DOUYIN:
                # 抖音：70%推荐池（全站高互动内容）+ 30%关注
                rec_limit = int(limit * 0.7)
                follow_limit = limit - rec_limit

                # 推荐池：基于播放完成率和互动量
                cursor.execute("""
                    SELECT p.*, u.username,
                           (p.like_count * 2 + p.comment_count * 3 + p.play_count * 0.01
                            + p.finish_rate * 100) as rec_score
                    FROM posts p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.user_id NOT IN (SELECT muted_user_id FROM mutes WHERE user_id = ?)
                    AND p.content_type IN ('post', 'short_video', 'photo_post')
                    ORDER BY rec_score DESC, RANDOM()
                    LIMIT ?
                """, (user_id, rec_limit))
                rec_posts = [dict(row) for row in cursor.fetchall()]

                # 关注的人的内容
                cursor.execute("""
                    SELECT p.*, u.username
                    FROM posts p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.user_id IN (SELECT following_id FROM follows WHERE follower_id = ?)
                    AND p.content_type IN ('post', 'short_video', 'photo_post')
                    ORDER BY p.created_at DESC
                    LIMIT ?
                """, (user_id, follow_limit))
                follow_posts = [dict(row) for row in cursor.fetchall()]

                # 合并并打乱（模拟算法混排）
                all_posts = rec_posts + follow_posts
                random.shuffle(all_posts)
                return all_posts

            else:
                # 微博/Twitter/Reddit：关注的人 + 自己的内容，按时间倒序
                cursor.execute("""
                    SELECT p.*, u.username
                    FROM posts p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.user_id IN (
                        SELECT following_id FROM follows WHERE follower_id = ?
                        UNION SELECT ?
                    )
                    AND p.user_id NOT IN (SELECT muted_user_id FROM mutes WHERE user_id = ?)
                    ORDER BY p.created_at DESC
                    LIMIT ?
                """, (user_id, user_id, user_id, limit))
                return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_trending_posts(self, limit: int = 20, time_window_hours: int = 24) -> List[Dict]:
        """
        获取热门内容
        微博：转评赞加权（转发权重最高，热搜逻辑）
        抖音：播放量+完播率+互动量（算法推荐逻辑）
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            if self.platform_type == PlatformType.DOUYIN:
                cursor.execute("""
                    SELECT p.*, u.username,
                           (p.play_count * 0.01 + p.finish_rate * 200
                            + p.like_count * 1 + p.comment_count * 3
                            + p.share_count * 5) as hot_score
                    FROM posts p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.created_at >= datetime('now', '-' || ? || ' hours')
                    AND p.content_type IN ('post', 'short_video')
                    ORDER BY hot_score DESC
                    LIMIT ?
                """, (time_window_hours, limit))
            else:
                # 微博热度：转发*4 + 评论*3 + 点赞*2（转发在微博权重最高）
                cursor.execute("""
                    SELECT p.*, u.username,
                           (p.repost_count * 4 + p.comment_count * 3
                            + p.like_count * 2 + p.view_count * 0.01) as hot_score
                    FROM posts p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.created_at >= datetime('now', '-' || ? || ' hours')
                    ORDER BY hot_score DESC, p.created_at DESC
                    LIMIT ?
                """, (time_window_hours, limit))

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_posts(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索内容"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT p.*, u.username
                FROM posts p JOIN users u ON p.user_id = u.user_id
                WHERE p.content LIKE ? OR p.topic LIKE ?
                ORDER BY p.created_at DESC LIMIT ?
            """, (f"%{keyword}%", f"%{keyword}%", limit))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_users(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM users
                WHERE username LIKE ? OR bio LIKE ?
                ORDER BY followers_count DESC LIMIT ?
            """, (f"%{keyword}%", f"%{keyword}%", limit))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_user_info(self, user_id: str) -> Optional[Dict]:
        """获取用户信息"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_post(self, post_id: int) -> Optional[Dict]:
        """获取内容详情"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT p.*, u.username FROM posts p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.post_id = ?
            """, (post_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_statistics(self) -> Dict:
        """获取平台统计数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            stats = {"platform": self.platform_type.value}

            cursor.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM posts")
            stats['total_posts'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM follows")
            stats['total_follows'] = cursor.fetchone()[0]

            cursor.execute("SELECT SUM(like_count) FROM posts")
            stats['total_likes'] = cursor.fetchone()[0] or 0

            cursor.execute("SELECT SUM(comment_count) FROM posts")
            stats['total_comments'] = cursor.fetchone()[0] or 0

            cursor.execute("SELECT SUM(repost_count) FROM posts")
            stats['total_reposts'] = cursor.fetchone()[0] or 0

            if self.platform_type == PlatformType.DOUYIN:
                cursor.execute("SELECT SUM(play_count) FROM posts")
                stats['total_plays'] = cursor.fetchone()[0] or 0
                cursor.execute("SELECT AVG(finish_rate) FROM posts WHERE play_count > 0")
                stats['avg_finish_rate'] = round(cursor.fetchone()[0] or 0, 2)

            return stats
        finally:
            conn.close()

    def update_trending_topics(self):
        """更新热门话题（从帖子中提取话题标签）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT topic, COUNT(*) as cnt,
                       SUM(like_count + comment_count + repost_count) as score
                FROM posts
                WHERE topic IS NOT NULL AND topic != ''
                AND created_at >= datetime('now', '-24 hours')
                GROUP BY topic
                ORDER BY score DESC
                LIMIT 50
            """)
            for row in cursor.fetchall():
                cursor.execute("""
                    INSERT OR REPLACE INTO trending_topics (topic, hot_score, post_count, platform)
                    VALUES (?, ?, ?, ?)
                """, (row[0], row[2], row[1], self.platform_type.value))
            conn.commit()
        finally:
            conn.close()

    def get_trending_topics(self, limit: int = 10) -> List[Dict]:
        """获取热门话题列表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM trending_topics
                ORDER BY hot_score DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

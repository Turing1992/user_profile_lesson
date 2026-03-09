# -*- coding: utf-8 -*-
"""
社交平台模拟环境
模拟类似 Twitter/Reddit 的社交媒体平台
"""
import time
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Set
from enum import Enum


class PlatformType(Enum):
    """平台类型"""
    TWITTER = "twitter"
    REDDIT = "reddit"


class ContentType(Enum):
    """内容类型"""
    POST = "post"
    COMMENT = "comment"
    REPOST = "repost"


class SocialPlatform:
    """社交平台环境"""
    
    def __init__(self, db_path: str = "oasis_simulation.db", platform_type: PlatformType = PlatformType.TWITTER):
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
                followers_count INTEGER DEFAULT 0,
                following_count INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 帖子表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                content_type TEXT DEFAULT 'post',
                parent_id INTEGER,
                repost_from INTEGER,
                like_count INTEGER DEFAULT 0,
                dislike_count INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                repost_count INTEGER DEFAULT 0,
                view_count INTEGER DEFAULT 0,
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
        
        # 互动表（点赞、点踩等）
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
                PRIMARY KEY (user_id, muted_user_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (muted_user_id) REFERENCES users(user_id)
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows(follower_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_follows_following ON follows(following_id)")
        
        conn.commit()
        conn.close()
    
    def create_user(self, user_id: str, username: str, bio: str = "", profile_data: dict = None):
        """创建用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, bio, profile_data)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, bio, json.dumps(profile_data or {})))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def create_post(self, user_id: str, content: str, content_type: str = "post", 
                   parent_id: int = None, repost_from: int = None) -> Optional[int]:
        """创建帖子/评论/转发"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO posts (user_id, content, content_type, parent_id, repost_from)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, content, content_type, parent_id, repost_from))
            
            post_id = cursor.lastrowid
            
            # 更新用户发帖数
            cursor.execute("UPDATE users SET posts_count = posts_count + 1 WHERE user_id = ?", (user_id,))
            
            # 如果是评论，更新父帖子的评论数
            if parent_id:
                cursor.execute("UPDATE posts SET comment_count = comment_count + 1 WHERE post_id = ?", (parent_id,))
            
            # 如果是转发，更新原帖的转发数
            if repost_from:
                cursor.execute("UPDATE posts SET repost_count = repost_count + 1 WHERE post_id = ?", (repost_from,))
            
            conn.commit()
            return post_id
        except Exception as e:
            print(f"创建帖子失败: {e}")
            return None
        finally:
            conn.close()
    
    def like_post(self, user_id: str, post_id: int) -> bool:
        """点赞帖子"""
        return self._interact(user_id, post_id, "like")
    
    def dislike_post(self, user_id: str, post_id: int) -> bool:
        """点踩帖子"""
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
                # 更新帖子计数
                if interaction_type == "like":
                    cursor.execute("UPDATE posts SET like_count = like_count + 1 WHERE post_id = ?", (post_id,))
                elif interaction_type == "dislike":
                    cursor.execute("UPDATE posts SET dislike_count = dislike_count + 1 WHERE post_id = ?", (post_id,))
                
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
                cursor.execute("UPDATE users SET following_count = following_count + 1 WHERE user_id = ?", (follower_id,))
                cursor.execute("UPDATE users SET followers_count = followers_count + 1 WHERE user_id = ?", (following_id,))
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
                cursor.execute("UPDATE users SET following_count = following_count - 1 WHERE user_id = ?", (follower_id,))
                cursor.execute("UPDATE users SET followers_count = followers_count - 1 WHERE user_id = ?", (following_id,))
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
                INSERT OR IGNORE INTO mutes (user_id, muted_user_id)
                VALUES (?, ?)
            """, (user_id, muted_user_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def get_user_feed(self, user_id: str, limit: int = 20) -> List[Dict]:
        """获取用户信息流"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # 获取关注的用户和自己的帖子
            cursor.execute("""
                SELECT p.*, u.username
                FROM posts p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.user_id IN (
                    SELECT following_id FROM follows WHERE follower_id = ?
                    UNION
                    SELECT ?
                )
                AND p.user_id NOT IN (
                    SELECT muted_user_id FROM mutes WHERE user_id = ?
                )
                ORDER BY p.created_at DESC
                LIMIT ?
            """, (user_id, user_id, user_id, limit))
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_trending_posts(self, limit: int = 20, time_window_hours: int = 24) -> List[Dict]:
        """获取热门帖子"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT p.*, u.username,
                       (p.like_count * 2 + p.comment_count * 3 + p.repost_count * 4) as hot_score
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
        """搜索帖子"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT p.*, u.username
                FROM posts p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.content LIKE ?
                ORDER BY p.created_at DESC
                LIMIT ?
            """, (f"%{keyword}%", limit))
            
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
                ORDER BY followers_count DESC
                LIMIT ?
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
        """获取帖子详情"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT p.*, u.username
                FROM posts p
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
            stats = {}
            
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
            
            return stats
        finally:
            conn.close()

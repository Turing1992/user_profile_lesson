# -*- coding: utf-8 -*-
"""
模拟数据分析工具
"""
import sqlite3
import json
from collections import Counter
from typing import Dict, List


class SimulationAnalyzer:
    """模拟数据分析器"""
    
    def __init__(self, db_path: str = "oasis_simulation.db"):
        self.db_path = db_path
    
    def analyze_all(self) -> Dict:
        """全面分析"""
        return {
            "basic_stats": self.get_basic_stats(),
            "user_ranking": self.get_user_ranking(),
            "content_analysis": self.analyze_content(),
            "network_analysis": self.analyze_network(),
            "activity_timeline": self.get_activity_timeline()
        }
    
    def get_basic_stats(self) -> Dict:
        """基础统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # 用户统计
        cursor.execute("SELECT COUNT(*), AVG(followers_count), AVG(following_count), AVG(posts_count) FROM users")
        row = cursor.fetchone()
        stats['users'] = {
            'total': row[0],
            'avg_followers': round(row[1] or 0, 2),
            'avg_following': round(row[2] or 0, 2),
            'avg_posts': round(row[3] or 0, 2)
        }
        
        # 帖子统计
        cursor.execute("""
            SELECT 
                COUNT(*),
                AVG(like_count),
                AVG(comment_count),
                AVG(repost_count),
                SUM(CASE WHEN content_type='post' THEN 1 ELSE 0 END),
                SUM(CASE WHEN content_type='comment' THEN 1 ELSE 0 END),
                SUM(CASE WHEN content_type='repost' THEN 1 ELSE 0 END)
            FROM posts
        """)
        row = cursor.fetchone()
        stats['posts'] = {
            'total': row[0],
            'avg_likes': round(row[1] or 0, 2),
            'avg_comments': round(row[2] or 0, 2),
            'avg_reposts': round(row[3] or 0, 2),
            'original_posts': row[4],
            'comments': row[5],
            'reposts': row[6]
        }
        
        # 互动统计
        cursor.execute("SELECT COUNT(*) FROM interactions")
        stats['total_interactions'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM follows")
        stats['total_follows'] = cursor.fetchone()[0]
        
        conn.close()
        return stats
    
    def get_user_ranking(self, limit: int = 10) -> Dict:
        """用户排行榜"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        rankings = {}
        
        # 粉丝数排行
        cursor.execute("""
            SELECT user_id, username, followers_count
            FROM users
            ORDER BY followers_count DESC
            LIMIT ?
        """, (limit,))
        rankings['by_followers'] = [dict(row) for row in cursor.fetchall()]
        
        # 发帖数排行
        cursor.execute("""
            SELECT user_id, username, posts_count
            FROM users
            ORDER BY posts_count DESC
            LIMIT ?
        """, (limit,))
        rankings['by_posts'] = [dict(row) for row in cursor.fetchall()]
        
        # 影响力排行（综合指标）
        cursor.execute("""
            SELECT 
                u.user_id,
                u.username,
                u.followers_count,
                u.posts_count,
                COALESCE(SUM(p.like_count), 0) as total_likes,
                (u.followers_count * 2 + u.posts_count + COALESCE(SUM(p.like_count), 0)) as influence_score
            FROM users u
            LEFT JOIN posts p ON u.user_id = p.user_id
            GROUP BY u.user_id
            ORDER BY influence_score DESC
            LIMIT ?
        """, (limit,))
        rankings['by_influence'] = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return rankings
    
    def analyze_content(self) -> Dict:
        """内容分析"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        analysis = {}
        
        # 热门帖子
        cursor.execute("""
            SELECT post_id, user_id, content, like_count, comment_count, repost_count
            FROM posts
            WHERE content_type = 'post'
            ORDER BY (like_count * 2 + comment_count * 3 + repost_count * 4) DESC
            LIMIT 10
        """)
        analysis['hot_posts'] = [
            {
                'post_id': row[0],
                'user_id': row[1],
                'content': row[2][:100],
                'likes': row[3],
                'comments': row[4],
                'reposts': row[5]
            }
            for row in cursor.fetchall()
        ]
        
        # 内容长度分布
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN LENGTH(content) < 50 THEN '短(< 50)'
                    WHEN LENGTH(content) < 100 THEN '中(50-100)'
                    ELSE '长(> 100)'
                END as length_category,
                COUNT(*) as count
            FROM posts
            WHERE content_type = 'post'
            GROUP BY length_category
        """)
        analysis['content_length_distribution'] = dict(cursor.fetchall())
        
        conn.close()
        return analysis
    
    def analyze_network(self) -> Dict:
        """网络分析"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        analysis = {}
        
        # 关注网络密度
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM follows")
        total_follows = cursor.fetchone()[0]
        
        max_possible_follows = total_users * (total_users - 1)
        analysis['network_density'] = round(total_follows / max_possible_follows, 4) if max_possible_follows > 0 else 0
        
        # 互惠关注
        cursor.execute("""
            SELECT COUNT(*) FROM follows f1
            WHERE EXISTS (
                SELECT 1 FROM follows f2
                WHERE f1.follower_id = f2.following_id
                AND f1.following_id = f2.follower_id
            )
        """)
        mutual_follows = cursor.fetchone()[0]
        analysis['mutual_follows'] = mutual_follows
        analysis['mutual_follow_rate'] = round(mutual_follows / total_follows, 4) if total_follows > 0 else 0
        
        conn.close()
        return analysis
    
    def get_activity_timeline(self) -> List[Dict]:
        """活动时间线"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                COUNT(*) as post_count
            FROM posts
            GROUP BY hour
            ORDER BY hour
        """)
        
        timeline = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return timeline
    
    def print_report(self):
        """打印分析报告"""
        print("\n" + "="*60)
        print("OASIS 模拟数据分析报告")
        print("="*60)
        
        analysis = self.analyze_all()
        
        # 基础统计
        print("\n【基础统计】")
        stats = analysis['basic_stats']
        print(f"用户总数: {stats['users']['total']}")
        print(f"  平均粉丝数: {stats['users']['avg_followers']}")
        print(f"  平均关注数: {stats['users']['avg_following']}")
        print(f"  平均发帖数: {stats['users']['avg_posts']}")
        print(f"\n帖子总数: {stats['posts']['total']}")
        print(f"  原创帖子: {stats['posts']['original_posts']}")
        print(f"  评论: {stats['posts']['comments']}")
        print(f"  转发: {stats['posts']['reposts']}")
        print(f"  平均点赞数: {stats['posts']['avg_likes']}")
        print(f"\n总互动数: {stats['total_interactions']}")
        print(f"总关注关系: {stats['total_follows']}")
        
        # 用户排行
        print("\n【影响力 TOP 5】")
        for i, user in enumerate(analysis['user_ranking']['by_influence'][:5], 1):
            print(f"{i}. {user['username']} - 影响力:{user['influence_score']} "
                  f"(粉丝:{user['followers_count']}, 帖子:{user['posts_count']}, "
                  f"获赞:{user['total_likes']})")
        
        # 热门内容
        print("\n【热门帖子 TOP 3】")
        for i, post in enumerate(analysis['content_analysis']['hot_posts'][:3], 1):
            print(f"{i}. [{post['user_id']}] {post['content']}")
            print(f"   赞:{post['likes']}, 评:{post['comments']}, 转:{post['reposts']}")
        
        # 网络分析
        print("\n【网络分析】")
        network = analysis['network_analysis']
        print(f"网络密度: {network['network_density']}")
        print(f"互惠关注数: {network['mutual_follows']}")
        print(f"互惠关注率: {network['mutual_follow_rate']}")
        
        print("\n" + "="*60 + "\n")
    
    def export_report(self, output_path: str = "analysis_report.json"):
        """导出分析报告"""
        analysis = self.analyze_all()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        
        print(f"分析报告已导出到: {output_path}")


def main():
    """主函数"""
    import sys
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else "oasis_simulation.db"
    
    analyzer = SimulationAnalyzer(db_path)
    analyzer.print_report()
    analyzer.export_report()


if __name__ == "__main__":
    main()

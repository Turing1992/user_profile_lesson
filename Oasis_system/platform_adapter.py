# -*- coding: utf-8 -*-
"""
平台数据适配器
处理微博、抖音等不同平台的数据格式差异，统一转换为系统标准格式
"""
from typing import Dict, List, Optional


# 平台特征描述，用于 LLM 分析时提供平台上下文
PLATFORM_CONTEXT = {
    "weibo": {
        "name": "微博",
        "description": "新浪微博，中国最大的社交媒体平台之一",
        "features": [
            "140字短文本为主，支持长文",
            "有转发、评论、点赞机制",
            "有超话、热搜等特色功能",
            "有蓝V(企业认证)和黄V(个人认证)体系",
            "粉丝数和互动量是影响力核心指标",
            "内容偏向时事热点、娱乐八卦、社会话题"
        ],
        "user_levels": ["普通用户", "黄V认证", "蓝V认证", "金V", "微博大V"],
        "content_types": ["微博正文", "长文章", "视频微博", "图文微博", "转发微博"],
        "key_metrics": ["粉丝数", "关注数", "微博数", "转评赞", "超话等级"]
    },
    "douyin": {
        "name": "抖音",
        "description": "字节跳动旗下短视频平台",
        "features": [
            "短视频为核心内容形式(15s-10min)",
            "算法推荐驱动，去中心化分发",
            "有直播、电商、本地生活等功能",
            "有蓝V(企业认证)和黄V(个人认证)",
            "播放量和完播率是核心指标",
            "内容偏向娱乐、生活、知识、带货"
        ],
        "user_levels": ["普通用户", "个人认证", "企业认证", "MCN签约", "头部达人"],
        "content_types": ["短视频", "直播", "图文", "商品橱窗"],
        "key_metrics": ["粉丝数", "获赞数", "作品数", "播放量", "直播数据"]
    }
}


class PlatformAdapter:
    """平台数据适配器"""

    @staticmethod
    def normalize(account_data: Dict, platform: str) -> Dict:
        """
        将平台原始数据标准化为系统统一格式

        Args:
            account_data: 原始账号数据
            platform: 平台标识 (weibo / douyin)

        Returns:
            标准化后的账号数据
        """
        if platform == "weibo":
            return PlatformAdapter._normalize_weibo(account_data)
        elif platform == "douyin":
            return PlatformAdapter._normalize_douyin(account_data)
        else:
            # 未知平台，直接返回
            return account_data

    @staticmethod
    def _normalize_weibo(data: Dict) -> Dict:
        """标准化微博数据"""
        normalized = {
            "account_id": data.get("account_id") or data.get("uid") or data.get("id", ""),
            "platform": "weibo",
            "name": data.get("name") or data.get("screen_name") or data.get("nickname", ""),
            "identity": data.get("identity") or data.get("verified_reason") or "",
            "description": data.get("description") or data.get("bio") or "",
            "verified_reason": data.get("verified_reason") or "",
        }

        # 微博特有字段
        platform_data = {
            "verified_type": data.get("verified_type"),  # -1未认证 0黄V 1蓝V等
            "followers_count": data.get("followers_count") or data.get("fans_count", 0),
            "following_count": data.get("following_count") or data.get("follow_count", 0),
            "statuses_count": data.get("statuses_count") or data.get("weibo_count", 0),
            "gender": data.get("gender") or data.get("sex", ""),
            "location": data.get("location") or data.get("city", ""),
            "created_at": data.get("created_at") or data.get("register_time", ""),
            "sunshine_credit": data.get("sunshine_credit", ""),
            "urank": data.get("urank", 0),
            "mbrank": data.get("mbrank", 0),  # 会员等级
            "labels": data.get("labels") or data.get("tags", []),
            "recent_posts": data.get("recent_posts", []),
        }
        normalized["platform_data"] = platform_data

        # 拼接更丰富的 description 给 LLM
        extra_desc_parts = []
        if platform_data["location"]:
            extra_desc_parts.append(f"所在地: {platform_data['location']}")
        if platform_data["followers_count"]:
            extra_desc_parts.append(f"粉丝数: {platform_data['followers_count']}")
        if platform_data["statuses_count"]:
            extra_desc_parts.append(f"微博数: {platform_data['statuses_count']}")
        vtype = platform_data["verified_type"]
        if vtype is not None and vtype >= 0:
            v_label = {0: "黄V个人认证", 1: "蓝V企业认证", 3: "蓝V政府认证"}.get(vtype, f"认证类型{vtype}")
            extra_desc_parts.append(f"认证: {v_label}")
        if platform_data["labels"]:
            extra_desc_parts.append(f"标签: {', '.join(platform_data['labels'][:5])}")

        if extra_desc_parts:
            normalized["platform_summary"] = "；".join(extra_desc_parts)

        return normalized

    @staticmethod
    def _normalize_douyin(data: Dict) -> Dict:
        """标准化抖音数据"""
        normalized = {
            "account_id": data.get("account_id") or data.get("sec_uid") or data.get("uid") or data.get("id", ""),
            "platform": "douyin",
            "name": data.get("name") or data.get("nickname") or "",
            "identity": data.get("identity") or data.get("custom_verify") or data.get("enterprise_verify_reason") or "",
            "description": data.get("description") or data.get("signature") or "",
            "verified_reason": data.get("verified_reason") or data.get("custom_verify") or "",
        }

        # 抖音特有字段
        platform_data = {
            "verified_type": data.get("verified_type"),
            "follower_count": data.get("follower_count") or data.get("fans_count", 0),
            "following_count": data.get("following_count") or data.get("follow_count", 0),
            "total_favorited": data.get("total_favorited") or data.get("like_count", 0),
            "aweme_count": data.get("aweme_count") or data.get("video_count", 0),
            "gender": data.get("gender", ""),  # 0未知 1男 2女
            "city": data.get("city") or data.get("location", ""),
            "province": data.get("province", ""),
            "ip_location": data.get("ip_location", ""),
            "unique_id": data.get("unique_id") or data.get("douyin_id", ""),
            "short_id": data.get("short_id", ""),
            "is_star": data.get("is_star", False),
            "commerce_info": data.get("commerce_info", {}),  # 电商信息
            "live_commerce": data.get("live_commerce", False),  # 是否直播带货
            "labels": data.get("labels") or data.get("tags", []),
            "recent_videos": data.get("recent_videos", []),
        }
        normalized["platform_data"] = platform_data

        # 拼接更丰富的 description
        extra_desc_parts = []
        location = platform_data.get("ip_location") or platform_data.get("city") or platform_data.get("province")
        if location:
            extra_desc_parts.append(f"IP属地: {location}")
        if platform_data["follower_count"]:
            extra_desc_parts.append(f"粉丝数: {platform_data['follower_count']}")
        if platform_data["total_favorited"]:
            extra_desc_parts.append(f"获赞数: {platform_data['total_favorited']}")
        if platform_data["aweme_count"]:
            extra_desc_parts.append(f"作品数: {platform_data['aweme_count']}")
        if platform_data["live_commerce"]:
            extra_desc_parts.append("有直播带货")
        if platform_data["labels"]:
            extra_desc_parts.append(f"标签: {', '.join(platform_data['labels'][:5])}")

        gender_map = {1: "男", 2: "女"}
        g = gender_map.get(platform_data["gender"])
        if g:
            extra_desc_parts.append(f"性别: {g}")

        if extra_desc_parts:
            normalized["platform_summary"] = "；".join(extra_desc_parts)

        return normalized

    @staticmethod
    def get_platform_context(platform: str) -> Dict:
        """获取平台上下文信息，用于 LLM prompt"""
        return PLATFORM_CONTEXT.get(platform, {})

    @staticmethod
    def build_enriched_description(normalized_data: Dict) -> str:
        """
        构建增强版描述文本，将平台特有数据融入描述中供 LLM 使用

        Args:
            normalized_data: 标准化后的数据

        Returns:
            增强后的描述文本
        """
        parts = []

        platform = normalized_data.get("platform", "")
        if platform:
            ctx = PLATFORM_CONTEXT.get(platform, {})
            parts.append(f"[平台: {ctx.get('name', platform)}]")

        desc = normalized_data.get("description", "")
        if desc:
            parts.append(desc)

        summary = normalized_data.get("platform_summary", "")
        if summary:
            parts.append(f"[平台数据] {summary}")

        # 加入近期内容摘要
        pd = normalized_data.get("platform_data", {})
        recent = pd.get("recent_posts") or pd.get("recent_videos") or []
        if recent:
            content_items = []
            for item in recent[:3]:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("desc") or item.get("content", "")
                elif isinstance(item, str):
                    text = item
                else:
                    continue
                if text:
                    content_items.append(text[:80])
            if content_items:
                parts.append(f"[近期内容] " + " | ".join(content_items))

        return "\n".join(parts)

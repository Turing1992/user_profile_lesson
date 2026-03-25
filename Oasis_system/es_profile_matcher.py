# -*- coding: utf-8 -*-
"""
ES 画像匹配器
从 OpenSearch 中按账号名/uid 搜索已有画像数据
"""
import hashlib
from typing import Dict, List, Optional
from opensearchpy import OpenSearch

# OpenSearch 配置（与主系统一致）
OPENSEARCH_CONFIG = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": '../ca.cer',
    "timeout": 30
}

INDEX_PREFIX = "user_profile"
TOTAL_SHARDS = 1000

# 平台索引映射
PLATFORM_INDEX_MAP = {
    "抖音": "media_douyin",
    "西瓜视频": "media_douyin",
    "新浪微博": "media_weibo",
    "新浪长微博": "media_weibo",
    "新浪微博视频": "media_weibo",
    "快手": "media_kuaishou",
    "小红书": "media_xhs",
    "bilibili": "media_bilibili",
    "知乎": "media_zhihu",
    "微信": "media_weixin",
    "今日头条": "media_toutiao",
}


class ESProfileMatcher:
    """ES 画像匹配器"""

    def __init__(self, config: Dict = None):
        self.config = config or OPENSEARCH_CONFIG
        self.client = None

    def _get_client(self) -> OpenSearch:
        if self.client is None:
            self.client = OpenSearch(**self.config)
        return self.client

    def _get_shard_index(self, uid: str) -> str:
        """根据 uid 计算分片索引名"""
        hash_value = int(hashlib.md5(uid.encode('utf-8')).hexdigest(), 16)
        shard_id = hash_value % TOTAL_SHARDS
        return f"{INDEX_PREFIX}_{shard_id:03d}"

    def search_by_name(self, name: str, platform: str = None, size: int = 5) -> List[Dict]:
        """
        按账号名搜索画像（模糊匹配）

        Args:
            name: 账号名
            platform: 限定平台（weibo/douyin），不传则搜全部
            size: 返回数量

        Returns:
            匹配到的画像列表
        """
        try:
            client = self._get_client()

            # 只在平台索引中搜索
            if platform == "douyin":
                index = "media_douyin"
            elif platform == "weibo":
                index = "media_weibo"
            else:
                index = "media_douyin,media_weibo"

            query = {
                "query": {
                    "bool": {
                        "should": [
                            {"match_phrase": {"name": {"query": name, "boost": 5.0}}},
                            {"term": {"uid": {"value": name, "boost": 10.0}}},
                            {"term": {"name.keyword": {"value": name, "boost": 10.0}}},
                        ],
                        "minimum_should_match": 1
                    }
                },
                "_source": [
                    "uid", "name", "site_name", "identity", "identity_standerd",
                    "description", "verified_reason", "gender", "age",
                    "ip_region", "followers_count", "community", "three_new_identity"
                ],
                "size": size
            }

            resp = client.search(index=index, body=query)
            hits = resp.get("hits", {}).get("hits", [])
            results = []
            for hit in hits:
                doc = hit["_source"]
                doc["_score"] = hit.get("_score", 0)
                doc["_index"] = hit.get("_index", "")
                results.append(doc)
            return results

        except Exception as e:
            print(f"[ES搜索失败] name={name}: {e}")
            return []

    def search_by_uid(self, uid: str, sitename: str = None) -> Optional[Dict]:
        """
        按 uid 精确查询画像

        Args:
            uid: 用户ID
            sitename: 站点名（用于定位分片索引）

        Returns:
            画像数据或 None
        """
        try:
            client = self._get_client()

            if sitename:
                # 用 uid + sitename 定位精确分片
                index_name = self._get_shard_index(uid + '_' + sitename)
                try:
                    resp = client.get(index=index_name, id=uid, ignore=[404])
                    if resp.get("found"):
                        return resp["_source"]
                except Exception:
                    pass

            # 回退：只在微博和抖音索引中搜索
            for idx in ["media_douyin", "media_weibo"]:
                try:
                    query = {"query": {"term": {"uid": uid}}, "size": 1}
                    resp = client.search(index=idx, body=query, ignore=[404])
                    hits = resp.get("hits", {}).get("hits", [])
                    if hits:
                        return hits[0]["_source"]
                except Exception:
                    continue

            return None

        except Exception as e:
            print(f"[ES查询失败] uid={uid}: {e}")
            return None

    def batch_search(self, account_names: List[str], platform: str = None) -> Dict[str, Optional[Dict]]:
        """
        批量搜索账号画像

        Args:
            account_names: 账号名列表
            platform: 限定平台

        Returns:
            {账号名: 画像数据或None}
        """
        results = {}
        for name in account_names:
            matches = self.search_by_name(name, platform=platform, size=1)
            if matches and matches[0].get("_score", 0) > 50.0:
                results[name] = matches[0]
            else:
                results[name] = None
        return results

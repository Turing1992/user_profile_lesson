"""
账号检索服务
"""
import logging
from typing import List, Dict, Any
import redis
from opensearchpy import OpenSearch

from intent_recognition_system.models.triplet import AccountResult, EventAnalysis
from intent_recognition_system.config.config import DATABASE_CONFIG, SEARCH_CONFIG

logger = logging.getLogger(__name__)


class AccountSearcher:
    """账号检索器"""
    
    def __init__(self):
        self.opensearch = self._init_opensearch()
        self.redis_client = self._init_redis()
        
    def _init_opensearch(self) -> OpenSearch:
        """初始化OpenSearch客户端"""
        config = DATABASE_CONFIG["opensearch"]
        return OpenSearch(
            hosts=config["hosts"],
            use_ssl=config["use_ssl"],
            verify_certs=config["verify_certs"]
        )
    
    def _init_redis(self) -> redis.Redis:
        """初始化Redis客户端"""
        config = DATABASE_CONFIG["redis"]
        return redis.Redis(
            host=config["host"],
            port=config["port"],
            db=config["db"],
            decode_responses=config["decode_responses"]
        )
    
    def search_accounts(self, analysis: EventAnalysis) -> List[AccountResult]:
        """根据事件分析结果搜索相关账号"""
        try:
            # 构建搜索查询
            search_query = self._build_search_query(analysis.all_keywords)
            
            # 执行搜索
            response = self.opensearch.search(
                index=f"{DATABASE_CONFIG['opensearch']['index_prefix']}*",
                body=search_query,
                size=SEARCH_CONFIG["max_results"]
            )
            
            # 解析搜索结果
            accounts = self._parse_search_results(response, analysis.all_keywords)
            
            # 按相关性排序
            accounts.sort(key=lambda x: x.relevance_score, reverse=True)
            
            # 限制返回数量
            return accounts[:SEARCH_CONFIG["account_limit"]]
            
        except Exception as e:
            logger.error(f"账号搜索失败: {e}")
            return []
    
    def _build_search_query(self, keywords: List[str]) -> Dict[str, Any]:
        """构建OpenSearch查询"""
        # 构建多字段匹配查询
        should_clauses = []
        
        for keyword in keywords:
            should_clauses.extend([
                {"match": {"content": {"query": keyword, "boost": 2.0}}},
                {"match": {"user_profile.identity": {"query": keyword, "boost": 1.5}}},
                {"match": {"user_profile.tags": {"query": keyword, "boost": 1.0}}},
                {"wildcard": {"content": f"*{keyword}*"}}
            ])
        
        query = {
            "query": {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1
                }
            },
            "aggs": {
                "accounts": {
                    "terms": {
                        "field": "account_id.keyword",
                        "size": SEARCH_CONFIG["max_results"]
                    },
                    "aggs": {
                        "relevance": {
                            "max": {"script": "_score"}
                        },
                        "comment_count": {
                            "value_count": {"field": "content.keyword"}
                        },
                        "sample": {
                            "top_hits": {
                                "size": 1,
                                "_source": ["username", "platform", "user_profile"]
                            }
                        }
                    }
                }
            }
        }
        
        return query
    
    def _parse_search_results(self, response: Dict[str, Any], keywords: List[str]) -> List[AccountResult]:
        """解析搜索结果"""
        accounts = []
        
        try:
            buckets = response["aggregations"]["accounts"]["buckets"]
            
            for bucket in buckets:
                account_id = bucket["key"]
                relevance_score = bucket["relevance"]["value"]
                comment_count = bucket["comment_count"]["value"]
                
                # 获取账号基本信息
                sample_hit = bucket["sample"]["hits"]["hits"][0]["_source"]
                username = sample_hit.get("username", "")
                platform = sample_hit.get("platform", "")
                
                # 计算匹配的关键词
                matched_keywords = self._find_matched_keywords(
                    sample_hit.get("content", ""), 
                    keywords
                )
                
                account = AccountResult(
                    account_id=account_id,
                    username=username,
                    platform=platform,
                    relevance_score=relevance_score,
                    matched_keywords=matched_keywords,
                    comment_count=comment_count
                )
                
                accounts.append(account)
                
        except Exception as e:
            logger.error(f"解析搜索结果失败: {e}")
        
        return accounts
    
    def _find_matched_keywords(self, content: str, keywords: List[str]) -> List[str]:
        """找出内容中匹配的关键词"""
        matched = []
        content_lower = content.lower()
        
        for keyword in keywords:
            if keyword.lower() in content_lower:
                matched.append(keyword)
        
        return matched
    
    def get_cached_result(self, cache_key: str) -> List[AccountResult]:
        """从缓存获取结果"""
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                import json
                data = json.loads(cached_data)
                return [AccountResult(**item) for item in data]
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
        
        return []
    
    def cache_result(self, cache_key: str, accounts: List[AccountResult], expire_time: int = 3600):
        """缓存搜索结果"""
        try:
            import json
            data = [account.dict() for account in accounts]
            self.redis_client.setex(cache_key, expire_time, json.dumps(data))
        except Exception as e:
            logger.error(f"缓存结果失败: {e}")
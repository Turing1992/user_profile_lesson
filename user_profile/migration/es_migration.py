import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import traceback
from opensearchpy import OpenSearch, helpers
import logging
from utils.config import opensearch_config
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OpenSearchScanner:
    def __init__(self, thread_count=4):
        try:
            self.client = OpenSearch(**opensearch_config)
            self.thread_count = thread_count
            logger.info("✅ 成功连接 OpenSearch")
        except Exception as e:
            logger.error(f"❌ 连接 OpenSearch 失败: {traceback.format_exc()}")
            raise

    def has_non_empty_history(self, data):
        """
        检查文档是否含有非空的 *history 字段
        非空：数组中至少有一个 item 的 'value' 不是空字符串或 None
        """
        for key, value in data.items():
            if "history" in key and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("value") not in ["", None]:
                        return True
        return False

    def extract_relevant_fields(self, source):
        """
        从原始文档中提取符合条件的 history 字段：
        - value 不为空字符串或 None
        - updated_at 不为 None
        """
        result = {"uid": source.get("uid")}

        # 要处理的三个字段
        history_fields = [
            "content_opinion_history",
            "description_history",
            "identity_history"
        ]

        for field in history_fields:
            if field not in source:
                continue

            items = source[field]
            if not isinstance(items, list):
                continue

            # 过滤：value 和 updated_at 都必须存在且非空
            filtered_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue

                value = item.get("value")
                updated_at = item.get("updated_at")

                # 判断是否有效
                if value not in ["", None] and updated_at is not None:
                    filtered_items.append({
                        "value": value,
                        "updated_at": updated_at
                    })

            # 只有非空列表才加入结果
            if filtered_items:
                result[field] = filtered_items

        return result

    def ensure_target_index(self, index_name):
        if not self.client.indices.exists(index=index_name):
            mapping = {
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "uid": {"type": "keyword"},

                        "content_opinion_history": {
                            "type": "nested",  # ← 关键！
                            "properties": {
                                "value": {"type": "text"},
                                "updated_at": {"type": "date"}
                            }
                        },

                        "description_history": {
                            "type": "nested",
                            "properties": {
                                "value": {"type": "text"},
                                "updated_at": {"type": "date"}
                            }
                        },

                        "identity_standerd_history": {
                            "type": "nested",
                            "properties": {
                                "value": {"type": "keyword"},
                                "updated_at": {"type": "date"}
                            }
                        },

                        "industry_history": {
                            "type": "nested",
                            "properties": {
                                "value": {"type": "keyword"},
                                "updated_at": {"type": "date"}
                            }
                        },

                        "opinions_history": {
                            "type": "nested",
                            "properties": {
                                "value": {"type": "text"},
                                "updated_at": {"type": "date"}
                            }
                        },

                        "following_history": {
                            "type": "nested",
                            "properties": {
                                "value": {"type": "keyword"},
                                "updated_at": {"type": "date"}
                            }
                        },

                        "identity_history": {
                            "type": "nested",
                            "properties": {
                                "value": {"type": "keyword"},
                                "updated_at": {"type": "date"}
                            }
                        }
                    }
                }
            }

            self.client.indices.create(index=index_name, body=mapping)
            print(f"✅ 索引 '{index_name}' 已创建，包含 nested 类型 mapping")
        else:
            print(f"ℹ️ 索引 '{index_name}' 已存在")

    def fetch_batch(self, scroll_id=None):
        """获取下一批数据（使用 scroll）"""
        if scroll_id is None:
            # 第一次查询
            query = {
                "query": {"match_all": {}},
                "size": 500,
                "_source": True
            }
            return self.client.search(
                index="user_profile*",
                body=query,
                scroll="5m",  # scroll 上下文保持 5 分钟
                request_timeout=30
            )
        else:
            # 继续滚动
            return self.client.scroll(
                scroll_id=scroll_id,
                scroll="5m",
                request_timeout=30
            )

    def process_and_write_batch(self, hits, target_index):
        """处理一批 hits 并写入目标索引"""
        actions = []
        count = 0

        for hit in hits:
            source = hit["_source"]

            if not self.has_non_empty_history(source):
                continue

            new_doc = self.extract_relevant_fields(source)
            new_doc["id"] = hit["_id"]

            action = {
                "_op_type": "index",
                "_index": target_index,
                "_id": hit["_id"],
                "_source": new_doc
            }
            actions.append(action)
            count += 1

        if actions:
            helpers.bulk(self.client, actions)
        return count

    def migrate_history_data(
        self,
        source_pattern="user_profile*",
        target_index="history_user_profile",
        batch_size=500,
        max_workers=None
    ):
        """
        多线程分批迁移：
        - 使用 scroll 获取数据批次
        - 多线程并行处理每个批次
        """
        self.ensure_target_index(target_index)
        if max_workers is None:
            max_workers = self.thread_count

        logger.info(f"🚀 开始多线程迁移数据，使用 {max_workers} 个线程...")
        query_body ={
              "size": 500,
              "query": {
                "bool": {
                  "should": [
                    {
                      "nested": {
                        "path": "content_opinion_history",
                        "query": {
                          "range": {
                            "content_opinion_history.updated_at": {
                              "gte": "2025-09-01T00:00:00",
                              "lte": "2025-11-24T00:00:00"
                            }
                          }
                        },
                        "inner_hits": {
                          "size": 5
                        }
                      }
                    },
                    {
                      "nested": {
                        "path": "description_history",
                        "query": {
                          "range": {
                            "description_history.updated_at": {
                              "gte": "2025-09-01T00:00:00",
                              "lte": "2025-11-24T00:00:00"
                            }
                          }
                        },
                        "inner_hits": {
                          "size": 5
                        }
                      }
                    },
                    {
                      "nested": {
                        "path": "identity_history",
                        "query": {
                          "range": {
                            "identity_history.updated_at": {
                              "gte": "2025-09-01T00:00:00",
                              "lte": "2025-11-24T00:00:00"
                            }
                          }
                        },
                        "inner_hits": {
                          "size": 5
                        }
                      }
                    }
                  ],
                  "minimum_should_match": 1
                }
              }
            }

        # 第一步：初始化 scroll
        response = self.client.search(
            index=source_pattern,
            body=query_body,
            scroll="5m",
            request_timeout=30
        )
        scroll_id = response.get('_scroll_id')
        total_fetched = len(response['hits']['hits'])

        # 提交第一批任务
        batches = [response['hits']['hits']]
        all_futures = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 将第一个批次提交给线程池
            future = executor.submit(self.process_and_write_batch, response['hits']['hits'], target_index)
            all_futures.append(future)

            processed_batches = 1
            total_written = 0

            try:
                while True:
                    # 获取下一批
                    response = self.fetch_batch(scroll_id=scroll_id)
                    hits = response['hits']['hits']
                    if not hits:
                        break

                    # 提交新批次到线程池
                    future = executor.submit(self.process_and_write_batch, hits, target_index)
                    all_futures.append(future)
                    processed_batches += 1

                    # 实时收集已完成的任务结果
                    for completed in as_completed(all_futures, timeout=10):
                        if completed not in [f for f in all_futures]:  # 避免重复统计
                            continue
                        try:
                            written = completed.result()
                            total_written += written
                            all_futures.remove(completed)
                            logger.info(f"📊 累计成功写入 {total_written} 条记录...")
                        except Exception as e:
                            logger.error(f"❌ 批量写入失败: {e}")

                    # 更新 scroll_id
                    scroll_id = response.get('_scroll_id')
                    total_fetched += len(hits)

                    # 控制并发数量（防止堆积太多未完成任务）
                    while len(all_futures) >= max_workers * 2:
                        time.sleep(0.1)

                # 等待剩余任务完成
                for future in as_completed(all_futures):
                    try:
                        written = future.result()
                        total_written += written
                    except Exception as e:
                        logger.error(f"❌ 最终批量写入失败: {e}")

            except Exception as e:
                logger.error(f"❌ 滚动查询出错: {traceback.format_exc()}")
                raise
            finally:
                # 清理 scroll 上下文
                try:
                    if scroll_id:
                        self.client.clear_scroll(scroll_id=scroll_id)
                except:
                    pass

        logger.info(f"✅ 数据迁移完成！共获取 {total_fetched} 条源文档，成功写入 {total_written} 条有效记录。")


# ======================
# 使用示例
# ======================
if __name__ == "__main__":
    scanner = OpenSearchScanner(thread_count=4)
    scanner.migrate_history_data(
        source_pattern="user_profile*",
        target_index="history_user_profile",
        max_workers=4
    )
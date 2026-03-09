# -*- coding: utf-8 -*-
from time import process_time_ns
from cassandra.cluster import Cluster
import traceback
import logging
from opensearchpy import OpenSearch, helpers
from concurrent.futures import ThreadPoolExecutor, as_completed

from torch.nn.parallel.comm import gather
from utils.config import opensearch_config  # 假设你的 ES 配置在这里
from utils.opinin_extract import qiye_expect  # 模型函数
from utils import download_API
from utils.daoding_body import daoding_body_gen
from utils.flash_user import get_douyin_play_count
import redis
import hashlib
from urllib.parse import urlparse
import pandas as pd
from datetime import datetime

# ========================
# Redis 配置
# ========================
REDIS_HOST = '192.168.16.136'
REDIS_PORT = 6379
REDIS_DB = 11

# ScyllaDB 配置（保留备用）
SCYLLADB_CONTACT_POINTS = ["192.168.191.9"]
SCYLLADB_PORT = 9042
SCYLLADB_KEYSPACE = "user_post_keyspace"

# OpenSearch 索引模式
INDEX_PATTERN = "user_profile_*"

# 并发与日志
MAX_WORKERS = 1
LOG_EVERY_N = 100

# 日志设置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ========================
# OpenSearch 扫描器：获取 user_level == "头部" 的完整用户信息
# ========================
class OpenSearchScanner:
    def __init__(self):
        try:
            self.client = OpenSearch(**opensearch_config)
            logger.info("✅ 成功连接 OpenSearch")
        except Exception as e:
            logger.error(f"❌ 连接 OpenSearch 失败: {traceback.format_exc()}")
            raise

    def get_head_user_docs(self):
        """获取所有 user_level 为 '头部' 的完整用户文档"""
        fields_to_fetch = [
            "uid", "sitename", "username", "name", "description", "org",
            "content_opinion", "community", "identity", "identity_standerd",
            "three_new_identity", "industry", "opinions", "user_level","followers"
        ]
        query = {
            "query": {
                "term": {"user_level": "头部"}
            },
            "_source": fields_to_fetch
        }
        try:
            logger.info("🔍 开始扫描 user_level='头部' 的用户文档...")
            docs = []
            for hit in helpers.scan(
                client=self.client,
                query=query,
                index=INDEX_PATTERN
            ):
                source = hit['_source']
                source['_id'] = hit['_id']  # 可选：保留 _id
                docs.append(source)

            logger.info(f"✅ 共找到 {len(docs)} 个符合条件的用户")
            return docs
        except Exception as e:
            logger.error(f"❌ 扫描 OpenSearch 失败: {traceback.format_exc()}")
            raise


# ========================
# ScyllaDB 客户端（备用，当前未使用）
# ========================
class ScyllaDBClient:
    def __init__(self):
        try:
            cluster = Cluster(SCYLLADB_CONTACT_POINTS, port=SCYLLADB_PORT)
            self.session = cluster.connect(SCYLLADB_KEYSPACE)
            logger.info("✅ 成功连接 ScyllaDB")
        except Exception as e:
            logger.error(f"❌ 连接 ScyllaDB 失败: {traceback.format_exc()}")
            self.session = None

    def query_texts_by_uid(self, uid: str) -> list:
        if not self.session:
            return []
        try:
            rows = self.session.execute(
                "SELECT text FROM user_posts WHERE uid = %s LIMIT 100",
                (uid,),
                timeout=10.0
            )
            return [row.text for row in rows if row.text and row.text.strip()]
        except Exception as e:
            logger.warning(f"[{uid}] 查询出错: {str(e)}")
            return []


# ========================
# Redis 客户端（保留原逻辑，按需使用）
# ========================
class RedisUrlClient:
    def __init__(self):
        try:
            self.client = redis.StrictRedis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            self.client.ping()
            print("✅ 成功连接到 Redis (db=11)")
        except Exception as e:
            raise ConnectionError(f"❌ 连接 Redis 失败: {e}")

    def get_url_metrics(self, url) -> dict:
        try:
            if self.client.type(url) != 'hash':
                return {}
            data = self.client.hgetall(url)
            metrics = {}
            for k, v in data.items():
                try:
                    metrics[k] = int(v)
                except (ValueError, TypeError):
                    metrics[k] = v
            return metrics
        except Exception as e:
            print(f"❌ Redis 查询失败: {e}")
            return {}


# 初始化 Redis（如果后续要用）
redis_client = RedisUrlClient()


# ========================
# 处理单个用户的数据（核心逻辑）
# ========================
def process_user_data(user_doc):
    """
    处理单个用户的道丁数据 + 模型分析，并合并所有字段
    """
    try:
        uid = user_doc.get("uid")
        sitename = user_doc.get("sitename")

        if not uid or not sitename:
            logger.warning(f"⚠️ 缺失必要字段，跳过: {user_doc}")
            return None

        # 时间范围（可配置）
        start_time = "2025-10-21 00:00:00"
        end_time = "2025-11-21 00:00:00"
        body = daoding_body_gen(uid, sitename, [start_time, end_time])

        # 调用道丁 API 获取内容
        contents, total_count = download_API.get_data(body)

        # 统计互动数据
        like_count = repost_count = reply_count = visit_count = 0
        full_content = ""

        for item in contents:
            like_count += item.get("like_count", 0)
            repost_count += item.get("repost_count", 0)
            reply_count += item.get("reply_count", 0)
            visit_count += item.get("visit_count", 0)
            content_text = item.get("content", "").strip()
            if content_text:
                full_content += content_text + "\n"

        full_content = full_content.strip()

        # 过企业舆情模型
        if full_content:
            model_result = qiye_expect(full_content)
        else:
            model_result = {}

        # === 构造最终结果字典 ===

        final_entry = {
            # 来自 OpenSearch 的原始字段
            "uid": user_doc.get("uid"),
            "sitename": user_doc.get("sitename"),
            "username": user_doc.get("username"),
            "name": user_doc.get("name"),
            "description": user_doc.get("description"),
            "org": user_doc.get("org"),
            "content_opinion": user_doc.get("content_opinion"),
            "community": user_doc.get("community"),
            "identity": user_doc.get("identity"),
            "identity_standerd": user_doc.get("identity_standerd"),
            "three_new_identity": user_doc.get("three_new_identity"),
            "industry": user_doc.get("industry"),
            "opinions": user_doc.get("opinions"),
            "user_level": user_doc.get("user_level"),
            "followers": user_doc.get("followers"),


            # 互动统计
            "like_count": like_count,
            "repost_count": repost_count,
            "reply_count": reply_count,
            "visit_count": visit_count,

            # 模型输出（动态展开）
            **model_result  # 自动合并所有模型返回的键值对
        }

        return final_entry

    except Exception as e:
        logger.error(f"❌ 处理用户数据失败: {traceback.format_exc()}")
        return None


# ========================
# 主函数
# ========================
def main():
    scanner = OpenSearchScanner()
    # scylla_client = ScyllaDBClient()  # 保留，当前未使用
    #
    # if not scylla_client.session:
    #     logger.error("🛑 ScyllaDB 连接失败，退出。")
    #     return

    # 获取用户数据
    user_docs = scanner.get_head_user_docs()
    if not user_docs:
        logger.info("📭 未找到任何 user_level='头部' 的用户，程序结束。")
        return

    final_result = []
    processed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_doc = {executor.submit(process_user_data, doc): doc for doc in user_docs}

        for future in as_completed(future_to_doc):
            result = future.result()
            if result:
                final_result.append(result)
            processed += 1

            if processed % LOG_EVERY_N == 0:
                logger.info(f"📊 已处理: {processed}/{len(user_docs)}")

    logger.info(f"🎉 完成！共处理 {processed} 个用户。")

    # 写入 Excel
    if final_result:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"user_profile_head_export_{timestamp}.xlsx"
        try:
            df = pd.DataFrame(final_result)
            df.to_excel(output_file, index=False, sheet_name='Head_Users')
            logger.info(f"💾 结果已保存至 Excel: {output_file}")
            logger.info(f"📋 数据维度: {df.shape[0]} 行 × {df.shape[1]} 列")
        except Exception as e:
            logger.error(f"❌ 写入 Excel 失败: {traceback.format_exc()}")
    else:
        logger.warning("📭 没有生成任何有效数据，无法写入文件")


def demo_data_preocess(user_doc):
    contents=[]
    try:
        user=user_doc.get('user')
        uid = user.get("uid")
        sitename = user_doc.get("sitename")
        username=user.get("username")
        url=user_doc.get("url")
        ctime=user_doc.get("ctime")
        # 点评转刷新
        num_dict=get_douyin_play_count('0d57a4b0-c3da-4abe-b972-a729de1444f5',url,ctime)
        content=user_doc.get("content")
        ocr=user_doc.get("ocr")
        full_content=content+ocr
        #大模型抽取
        contents.append(full_content)


        return

    except Exception as e:
        logger.error(f"❌ 处理用户数据失败: {traceback.format_exc()}")
        return None

# ========================
# 程序入口
# ========================
if __name__ == '__main__':
    main()
    #直接使用贴文数据计算样例数据

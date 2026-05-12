import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from time import process_time_ns

from cassandra.cluster import Cluster
import traceback
import logging
from opensearchpy import OpenSearch, helpers
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.config import *
from utils.opinin_extract import *
import redis
import hashlib
from urllib.parse import urlparse

# 临时使用道丁接口
from utils import download_API
from utils.daoding_body import daoding_body_gen

# ========================
# Redis 配置
# ========================
REDIS_HOST = '192.168.16.136'
REDIS_PORT = 6379
REDIS_DB = 11

# 可选：是否对 URL 做标准化（去参数、小写等）
NORMALIZE_URL = True


SCYLLADB_CONTACT_POINTS = ["192.168.191.9"]
SCYLLADB_PORT = 9042
SCYLLADB_KEYSPACE = "user_post_keyspace"

INDEX_PATTERN = "user_profile_*"
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
# OpenSearch 扫描器：只取 user_level == "头部" 的文档 ID
# ========================
class OpenSearchScanner:
    def __init__(self):
        self.client = OpenSearch(**opensearch_config)

    def get_head_user_docs(self):
        """获取所有 user_level 为 '头部' 的完整用户文档（指定字段）"""
        query = {
            "query": {
                "term": {"user_level": "头部"}
            },
            "_source": [
                "uid", "sitename", "username", "name", "description", "org",
                "content_opinion", "community", "identity", "identity_standerd",
                "three_new_identity", "industry", "opinions", "user_level"
            ]
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
                # 添加 _id 字段用于后续处理
                source['_id'] = hit['_id']
                docs.append(source)
            logger.info(f"✅ 共找到 {len(docs)} 个符合条件的用户")
            return docs
        except Exception as e:
            logger.error(f"❌ 扫描失败: {traceback.format_exc()}")
            raise

# ========================
# ScyllaDB 查询客户端
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
        """根据 uid 查询 text 字段"""
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


class RedisUrlClient:
    def __init__(self):
        try:
            self.client = redis.StrictRedis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,  # 自动将 bytes 转为 str
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # 测试连接
            self.client.ping()
            print("✅ 成功连接到 Redis (db=11)")
        except Exception as e:
            raise ConnectionError(f"❌ 连接 Redis 失败: {e}")

    def get_url_metrics(self,url) -> str:
        """
        根据传入的 URL，从 Redis DB11 中获取其行为数据
        返回字典，包含 comment, visit, attitudes 等
        """
        try:
            if self.client.type(url) != 'hash':
                print(f"⚠️ 未找到或类型不匹配: {url}")
                return {}

            data = self.client.hgetall(url)
            # 转成 int 类型更方便后续处理
            metrics = {}
            for k, v in data.items():
                try:
                    metrics[k] = int(v)
                except (ValueError, TypeError):
                    metrics[k] = v  # 保留原值
            print(f"🎯 命中: {url} → {metrics}")
            return metrics

        except Exception as e:
            print(f"❌ 查询失败: {e}")
            return {}

reidsclient = RedisUrlClient()
# ========================
# 主处理逻辑
# ========================
final_result=[]
def main():
    # 初始化
    scanner = OpenSearchScanner()
    scylla_client = ScyllaDBClient()

    if not scylla_client.session:
        logger.error("🛑 ScyllaDB 连接失败，退出。")
        return

    # 获取所有目标用户 ID
    user_ids = scanner.get_head_user_ids()
    if not user_ids:
        logger.info("📭 未找到任何 user_level='头部' 的用户，程序结束。")
        return

    # 并发查询并输出
    processed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_uid = {}

        for _id in user_ids:
            # 掉丁接口临时获取数据
            m=_id.split('_')
            uid=m[0]
            final_sitename=m[1]
            body=daoding_body_gen(uid,final_sitename,["2025-10-21"+" 00:00:00","2025-11-21"+" 00:00:00"])
            # 获得文本后过模型
            contents,total_count = download_API.get_data(body)
            try:
                cons=""
                like_count,repost_count,reply_count,visit_count=0,0,0,0
                for content in contents:
                    print(content)
                    like_count+=content.get("like_count",0)#点赞
                    repost_count+=content.get("repost_count",0)#转发
                    reply_count+=content.get("reply_count",0)#转发
                    visit_count+=content.get("visit_count",0)#访问量
                    cons+=content["content"]

                model_result=qiye_expect(cons)
                model_result['like_count']=like_count
                model_result['repost_count']=repost_count
                model_result['reply_count']=reply_count
                model_result['visit_count']=visit_count
            except:
                continue
            final_result.append(model_result)

            # print(model_result)

            # qiye_expect(contents)
        # 大宽表调用
        # uid = _id.replace('_', '-')  # 转换规则按需调整
        #     future = executor.submit(scylla_client.query_texts_by_uid, uid)
        #     future_to_uid[future] = uid
        #
        # for future in as_completed(future_to_uid):
        #     uid = future_to_uid[future]
        #     texts = future.result()
        #     processed += 1
        #
        #     # 🔥 直接打印输出，便于后续接入其他模块
        #     if texts:
        #         print(f"\n--- UID: {uid} ---")
        #         for i, text in enumerate(texts, 1):
        #             print(f"{i:2d}. {text}")

            # if processed % LOG_EVERY_N == 0:
            #     logger.info(f"📊 已处理: {processed}/{len(user_ids)}")

    logger.info(f"🎉 完成！共处理 {processed} 个用户。")


if __name__ == '__main__':
    main()
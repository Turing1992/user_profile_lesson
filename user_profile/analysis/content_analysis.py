import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cassandra.cluster import Cluster
import traceback
import json
from typing import Dict, Optional, List, Generator
from opensearchpy import OpenSearch, helpers
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from utils.config import *
from utils import opinin_extract

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class ScenarioManager:
    """用于与 OpenSearch 交互：扫描和更新文档"""

    def __init__(self):
        self.es_client = OpenSearch(**opensearch_config)

    def scan_opensearch(self, index: str = "user_profile_*") -> Generator[Dict, None, None]:
        """
        流式扫描 OpenSearch 文档，返回生成器。
        可处理任意规模数据，内存友好。
        """
        query = {"query": {"match_all": {}}}  # 可替换为实际过滤条件，如时间范围等

        try:
            logger.info(f"🔍 开始流式扫描索引: {index}")
            for hit in helpers.scan(
                client=self.es_client,
                query=query,
                index=index,
                _source=True
            ):
                yield hit
        except Exception as e:
            logger.error(f"❌ 扫描 OpenSearch 失败: {traceback.format_exc()}")
            raise

    def update_document_in_opensearch(self, index: str, doc_id: str, update_body: Dict) -> bool:
        """
        将结果写回 OpenSearch。
        返回是否成功。
        """
        try:
            response = self.es_client.update(
                index=index,
                id=doc_id,
                body={
                    "doc": update_body,
                    "doc_as_upsert": True  # 如果不存在则插入
                }
            )
            result = response.get('result', 'unknown')
            if result in ('created', 'updated'):
                return True
            else:
                logger.warning(f"⚠️ 文档 {doc_id} 更新状态异常: {result}")
                return False
        except Exception as e:
            logger.error(f"❌ 更新文档 {doc_id} 失败: {traceback.format_exc()}")
            return False


class ScyllaPostTexts:
    """连接 ScyllaDB 并查询用户帖子内容"""

    def __init__(self, contact_points, port=9042, keyspace="user_post_keyspace"):
        self.contact_points = contact_points
        self.port = port
        self.keyspace = keyspace
        self.session = self._connect()
        if self.session:
            try:
                self.session.set_keyspace(self.keyspace)
                logger.info("✅ 成功切换到 keyspace: %s", self.keyspace)
            except Exception as e:
                logger.error(f"❌ 切换 keyspace 失败: {traceback.format_exc()}")
                self.session = None

    def _connect(self) -> Optional:
        """建立连接"""
        try:
            cluster = Cluster(self.contact_points, port=self.port)
            session = cluster.connect()
            logger.info("✅ 成功连接到 ScyllaDB")
            return session
        except Exception as e:
            logger.error(f"❌ 连接 ScyllaDB 失败: {traceback.format_exc()}")
            return None

    def get_uid_post(self, uid: str) -> Optional[List]:
        """根据 UID 查询用户帖子文本"""
        if not self.session:
            return None
        try:
            query = "SELECT text FROM user_posts WHERE uid = %s"
            rows = list(self.session.execute(query, (uid,), timeout=10.0))
            return rows if rows else None
        except Exception as e:
            logger.error(f"[{uid}] 查询失败: {traceback.format_exc()}")
            return None


def process_single_doc(
    doc: Dict,
    scenario_manager: ScenarioManager,
    scylla_db: ScyllaPostTexts
):
    """
    处理单个文档的函数（供线程池调用）
    返回处理结果统计
    """
    doc_id = doc['_id']
    index_name = doc['_index']
    uid = doc_id.replace('_',"-")

    result = {
        "doc_id": doc_id,
        "success": False,
        "found_in_scylla": False,
        "updated_in_es": False
    }

    try:
        # 1. 查询 ScyllaDB
        scylla_data = scylla_db.get_uid_post(uid)
        if not scylla_data:
            result["success"] = True  # 没查到也算成功处理
            return result

        all_texts = list(set([row.text for row in scylla_data]))
        if len(all_texts)<10:
            result["success"] = True  # 没查到也算成功处理
            return result
        result["found_in_scylla"] = True
        # 2. 调用业务逻辑
        kind_result = opinin_extract.get_kind2(''.join(all_texts))
        if not kind_result:
            result["success"] = True
            return result

        # if kind_result['user_info']!={}:
        print(all_texts)
        print(kind_result)

        # 3. 写回 OpenSearch
        # updated = scenario_manager.update_document_in_opensearch(
        #     index=index_name,
        #     doc_id=doc_id,
        #     update_body=kind_result
        # )
        # result["updated_in_es"] = updated
        # result["success"] = True

    except Exception as e:
        logger.error(f"📌 处理文档 {doc_id} 时发生未预期错误: {traceback.format_exc()}")
        result["success"] = False

    return result


# ========================
# 主函数
# ========================

def main():


    SCYLLADB_CONTACT_POINTS = ["192.168.191.9"]
    SCYLLADB_PORT = 9042
    SCYLLADB_KEYSPACE = "user_post_keyspace"

    INDEX_PATTERN = "user_profile_*"
    MAX_WORKERS = 2          # 并发线程数（建议 5~20）
    LOG_EVERY_N = 1000        # 每处理 N 条输出一次进度

    # 初始化组件
    scenario_manager = ScenarioManager()
    scylla_db = ScyllaPostTexts(
        contact_points=SCYLLADB_CONTACT_POINTS,
        port=SCYLLADB_PORT,
        keyspace=SCYLLADB_KEYSPACE
    )

    if not scylla_db.session:
        logger.error("🛑 ScyllaDB 初始化失败，退出程序。")
        return

    # 统计变量
    processed_count = 0
    updated_count = 0
    failed_count = 0

    logger.info("🚀 开始执行批处理任务...")

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []

            # 提交任务流
            for doc in scenario_manager.scan_opensearch(index=INDEX_PATTERN):
                future = executor.submit(process_single_doc, doc, scenario_manager, scylla_db)
                futures.append(future)

                # 控制队列长度，防止内存堆积
                if len(futures) >= MAX_WORKERS * 3:
                    for f in as_completed(futures[:MAX_WORKERS]):
                        res = f.result()
                        processed_count += 1
                        if res["updated_in_es"]:
                            updated_count += 1
                        if not res["success"]:
                            failed_count += 1
                        futures.remove(f)

                        if processed_count % LOG_EVERY_N == 0:
                            logger.info(f"📊 已处理: {processed_count}, "
                                      f"成功更新: {updated_count}, "
                                      f"失败: {failed_count}")

            # 处理剩余任务
            for f in as_completed(futures):
                res = f.result()
                processed_count += 1
                if res["updated_in_es"]:
                    updated_count += 1
                if not res["success"]:
                    failed_count += 1
                if processed_count % LOG_EVERY_N == 0:
                    logger.info(f"📊 已处理: {processed_count}, "
                              f"成功更新: {updated_count}, "
                              f"失败: {failed_count}")

    except KeyboardInterrupt:
        logger.warning("🟡 用户中断程序。")
    except Exception as e:
        logger.critical(f"💥 程序异常终止: {traceback.format_exc()}")

    finally:
        logger.info(f"\n🎉 批处理完成！总计：")
        logger.info(f"   处理文档数: {processed_count}")
        logger.info(f"   成功更新 ES: {updated_count}")
        logger.info(f"   处理失败: {failed_count}")


if __name__ == '__main__':
    main()
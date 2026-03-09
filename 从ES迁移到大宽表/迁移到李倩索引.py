import traceback
from opensearchpy import OpenSearch, helpers
import logging
from datetime import datetime
from utils.config import opensearch_config
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



def clean_empty_bracket(value):
    if isinstance(value, str):
        cleaned = value.replace("[ ]", "").strip()
        return cleaned if cleaned != "" else None
    return value

#索引映射表
def build_sitename_to_target_index_map():
    """
    构建 sitename -> target_index 的映射表。
    返回一个 dict，key 是 sitename（字符串），value 是目标索引名。
    """
    mapping_rules = {
        "media_douyin": [
            "抖音",
            "西瓜视频"
        ],
        "media_weibo": [
            "新浪微博",
            "新浪长微博",
            "新浪微博视频",
            "新浪看点"

        ],
        "media_weixin": [
            "微信视频号",
            "微信"
        ],
        "media_kuaishou": [
            "快手",
            "快手极速版",
        ],
        "media_douban": [
            "豆瓣广场",
            "豆瓣"

        ],
        "media_baidu": [
            "百度贴吧",
            "百度百家",
            "度小视",
            "好看视频",
            "有驾",
            "百度知道"
        ],
        "media_xhs": [
            "小红书",
        ],
        "media_bilibili": [
            "bilibili"
        ],
        "media_zhihu": [
            "知乎问答",
            "知乎",
            "知乎专栏",
            "知乎问题",
            "知乎视频"

        ],
        "media_toutiao": [
            "今日头条"
        ],
        "media_other": [
            "腾讯网",
            "企鹅号",
            "腾讯看点",
            "腾讯视频",
            "快资讯",
            "一点资讯",
            "UC头条",
            "UC",
            "搜狐新闻",
            "趣头条",
            "网易号",
            "澎湃新闻"
        ],

    }

    # 反转为 {sitename: target_index}
    sitename_to_index = {}
    for target_index, sitenames in mapping_rules.items():
        for name in sitenames:
            if name in sitename_to_index:
                logger.warning(f"⚠️ sitename '{name}' 重复定义！已存在映射到 {sitename_to_index[name]}")
            sitename_to_index[name] = target_index

    return sitename_to_index


# 全局缓存映射表（模块级）
SITENAME_TO_TARGET_INDEX = build_sitename_to_target_index_map()


class MediaMigrator:  # 类名也改得更通用
    def __init__(self, max_workers=4):
        try:
            self.client = OpenSearch(**opensearch_config)
            self.max_workers = max_workers
            logger.info("✅ 成功连接 OpenSearch")
        except Exception as e:
            logger.error(f"❌ 连接 OpenSearch 失败: {traceback.format_exc()}")
            raise

    def ensure_target_index(self, index_name):
        if not self.client.indices.exists(index=index_name):
            mapping = {
                "mappings": {
                    "properties": {
                        "uid": {"type": "keyword"},
                        "sitename": {"type": "keyword"},
                        "identity": {"type": "text"},
                        "community": {"type": "text"},
                        "identity_standerd": {"type": "keyword"},
                        "industry": {"type": "keyword"}
                    }
                }
            }
            self.client.indices.create(index=index_name, body=mapping)
            logger.info(f"✅ 索引 '{index_name}' 已创建")
        else:
            logger.info(f"ℹ️ 索引 '{index_name}' 已存在")

    def process_batch(self, hits, target_index):
        """处理一批属于同一个 target_index 的文档"""
        if not hits:
            return 0

        doc_ids = []
        full_sources = []

        for hit in hits:
            src = hit['_source']
            uid = src.get('uid')
            identity = src.get('identity')
            sitename = src.get('sitename')

            if not uid or not identity or not isinstance(sitename, str):
                continue

            cleaned_identity = clean_empty_bracket(identity)
            if cleaned_identity is None:
                continue

            # 使用原始 sitename 构造 doc_id（保持一致性）
            doc_id = f"{sitename}|{uid}"
            doc_ids.append(doc_id)
            full_sources.append(src)

        if not doc_ids:
            return 0

        # 批量检查是否存在
            # 批量检查是否存在，并获取 source（用于判断是否有 identity）
        try:
            mget_resp = self.client.mget(
                index=target_index,
                body={"ids": doc_ids},
                _source=["identity"]  # 只取 identity 字段，节省带宽
            )
            existing_docs = {}
            for doc in mget_resp.get('docs', []):
                if doc.get('found'):
                    src = doc.get('_source', {})
                    # 判断旧数据是否已有 identity（非空字符串）
                    old_identity = src.get('identity')
                    if old_identity and isinstance(old_identity, str) and old_identity.strip():
                        existing_docs[doc['_id']] = True  # 标记为“已有 identity”
                    else:
                        existing_docs[doc['_id']] = False
        except Exception as e:
            logger.error(f"❌ mget 失败 (index={target_index}): {e}")
            return 0

        actions = []
        for doc_id, full_src in zip(doc_ids, full_sources):
            if doc_id in existing_docs:
                # 如果旧文档已有 identity，直接跳过
                if existing_docs[doc_id]:
                    continue  # 👈 关键修改：跳过更新

                # 否则，尝试更新（仅当新数据有有效字段时）
                update_doc = {}
                for field in ['identity', 'community', 'identity_standerd', 'industry']:
                    val = full_src.get(field)
                    cleaned_val = clean_empty_bracket(val)
                    if cleaned_val is not None:
                        update_doc[field] = cleaned_val
                if update_doc:
                    actions.append({
                        "_op_type": "update",
                        "_index": target_index,
                        "_id": doc_id,
                        "doc": update_doc
                    })
            else:
                # 插入模式（保持不变）
                insert_doc = {}
                for field in [
                    'identity', 'community', 'identity_standerd', 'industry',
                    'description', 'uid', 'sitename', 'username', 'three_new_identity'
                ]:
                    val = full_src.get(field)
                    cleaned_val = clean_empty_bracket(val)
                    if cleaned_val is not None:
                        if field == 'sitename':
                            insert_doc['site_name'] = cleaned_val
                        elif field == 'username':
                            insert_doc['name'] = cleaned_val
                        else:
                            insert_doc[field] = cleaned_val

                insert_doc['id'] = doc_id
                insert_doc['create_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                actions.append({
                    "_op_type": "index",
                    "_index": target_index,
                    "_id": doc_id,
                    "_source": insert_doc
                })

        if not actions:
            return 0

        try:
            success_count, errors = helpers.bulk(
                self.client,
                actions,
                raise_on_error=False,
                raise_on_exception=False
            )
            if errors:
                logger.warning(f"⚠️ 索引 {target_index} 本批次有 {len(errors)} 条失败，示例: {errors[0]}")
            return success_count
        except Exception as e:
            logger.error(f"❌ bulk 异常 (index={target_index}): {traceback.format_exc()}")
            return 0

    def migrate_all_profiles(
        self,
        source_pattern="user_profile_*",
        batch_size=1000,
        scroll_time="10m",
        test_mode=False,
    ):
        query_size = min(batch_size, 10) if test_mode else batch_size

        query_body = {
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "sitename"}},
                        {"exists": {"field": "identity"}},
                        {"exists": {"field": "uid"}}
                    ],
                    "must_not": [
                        {"term": {"identity": ""}}
                    ]
                }
            },
            "size": query_size
        }

        logger.info(f"🔍 开始全量迁移（测试模式: {'开启' if test_mode else '关闭'}）...")
        response = self.client.search(
            index=source_pattern,
            body=query_body,
            scroll=scroll_time if not test_mode else "2m",
            request_timeout=60
        )
        scroll_id = response.get('_scroll_id')
        total_written = 0
        batch_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            try:
                while True:
                    hits = response['hits']['hits']
                    if not hits:
                        break

                    batch_count += 1
                    logger.info(f"📤 处理第 {batch_count} 批（共 {len(hits)} 条）")

                    # === 核心：按 target_index 分组 ===
                    grouped = {}
                    unknown_count = 0
                    for hit in hits:
                        src = hit['_source']
                        sitename = src.get('sitename')
                        if not isinstance(sitename, str):
                            continue
                        target_idx = SITENAME_TO_TARGET_INDEX.get(sitename)
                        if not target_idx:
                            unknown_count += 1
                            continue
                        if target_idx not in grouped:
                            grouped[target_idx] = []
                        grouped[target_idx].append(hit)

                    if unknown_count:
                        logger.warning(f"❓ 第 {batch_count} 批跳过 {unknown_count} 条未知 sitename 的记录")

                    # 确保目标索引存在（懒创建）
                    # for idx in grouped.keys():
                    #     self.ensure_target_index(idx)

                    # 提交每个分组作为一个任务
                    for target_idx, sub_hits in grouped.items():
                        future = executor.submit(self.process_batch, sub_hits, target_idx)
                        futures.append(future)

                    if test_mode:
                        break

                    response = self.client.scroll(scroll_id=scroll_id, scroll=scroll_time)
                    scroll_id = response.get('_scroll_id')

                # 收集结果
                for future in as_completed(futures):
                    try:
                        written = future.result(timeout=120)
                        total_written += written
                    except Exception as e:
                        logger.error(f"❌ 线程异常: {e}")

            except Exception as e:
                logger.error(f"💥 主循环异常: {traceback.format_exc()}")
                raise
            finally:
                if scroll_id:
                    try:
                        self.client.clear_scroll(scroll_id=scroll_id)
                        logger.info("🧹 Scroll 上下文已清理")
                    except Exception as e:
                        logger.warning(f"⚠️ 清理 scroll 失败: {e}")

        logger.info(f"🎉 全量迁移完成！总共成功写入/更新 {total_written} 条记录")


# ======================
# 启动入口
# ======================
if __name__ == "__main__":
    # migrator = MediaMigrator(max_workers=2)
    #
    # print("🚀 启动测试模式（最多处理 10 条记录）...")
    # migrator.migrate_all_profiles(test_mode=True)

    # 全量运行时：
    migrator = MediaMigrator(max_workers=6)
    migrator.migrate_all_profiles(batch_size=2000, test_mode=False)
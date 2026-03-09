# -*- coding: utf-8 -*-
import mysql.connector
import hashlib
from opensearchpy import OpenSearch, helpers
import logging
from datetime import datetime
from collections import defaultdict
import threading
import codecs
import json

# ==================== 配置区 ====================


buffered_actions = defaultdict(list)
BUFFER_SIZE = 1000  # 每个索引缓存 1000 条再写入
client_lock = threading.Lock()

# MySQL 配置
sql_config = {
    "host": "192.168.19.65",
    "user": "buser",
    "password": "p3jnmja3",
    "database": "user_profile",
    "port": 3306,
    "charset": "utf8mb4"
}

# OpenSearch 配置
opensearch_config = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": 'ca.cer',
    "timeout": 30
}

# 索引配置
INDEX_PREFIX = "user_profile"        # 索引前缀
TOTAL_SHARDS = 1000               # 分片数量：1000 个索引
BATCH_SIZE = 1000                    # 每批读取行数

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
my_log_hd = logging.getLogger("MigrationLogger")

# ==================== 工具函数 ====================

def get_es_index_name(uid: str, total_shards=TOTAL_SHARDS, prefix=INDEX_PREFIX) -> str:
    """
    根据 uid 计算应写入的 OpenSearch 索引名
    使用 MD5 哈希确保分布均匀
    返回如: user_profile_000 ~ user_profile_999
    """
    uid_str = str(uid).strip()
    hash_value = int(hashlib.md5(uid_str.encode('utf-8')).hexdigest(), 16)
    shard_id = hash_value % total_shards
    return f"{prefix}_{shard_id:03d}"

# ==================== 初始化 OpenSearch 客户端 ====================

client = OpenSearch(**opensearch_config)

def create_all_indices():
    """批量创建 1000 个索引（如果不存在）"""
    index_settings = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 1,
            "refresh_interval": "30s"
        },
        "mappings": {
            "dynamic": "strict",  # 只允许预定义字段

            "properties": {
                "uid": {
                    "type": "keyword",
                    "doc_values": True
                },
                "index_suffix": {"type": "keyword"},

                # === 可追踪字段及其历史（最多10条）===
                "username": {
                    "type": "keyword",
                    "doc_values": True
                },
                "username_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "name": {
                    "type": "keyword",
                    "doc_values": True
                },
                "name_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },

                "org": {
                    "type": "keyword",
                    "doc_values": True
                },
                "org_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "real_name": {
                    "type": "keyword",
                    "doc_values": True
                },

                "gender": {
                    "type": "keyword",
                    "doc_values": True
                },
                "verified_org": {
                    "type": "keyword",
                    "doc_values": True
                },
                "verified_org_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "mcn": {
                    "type": "keyword",
                    "doc_values": True
                },
                "mcn_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "location": {
                    "type": "keyword",
                    "doc_values": True
                },
                "location_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "followers": {
                    "type": "keyword",
                    "doc_values": True
                },
                "followers_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "following": {
                    "type": "keyword",
                    "doc_values": True
                },
                "following_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "behavior_media": {
                    "type": "keyword",
                    "doc_values": True
                },
                "behavior_media_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },

                "sitename": {
                    "type": "keyword",
                    "doc_values": True
                },
                "contact": {
                    "type": "keyword",
                    "doc_values": True
                },
                "contact_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },

                "age": {
                    "type": "keyword",
                    "doc_values": True
                },
                "age_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },

                "industry": {
                    "type": "keyword",
                    "doc_values": True
                },
                "industry_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "verified_reason": {
                    "type": "keyword",
                    "doc_values": True
                },
                "verified_reason_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "identity": {
                    "type": "keyword",
                    "doc_values": True
                },
                "identity_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },
                "identity_standerd": {
                    "type": "keyword",
                    "doc_values": True
                },
                "identity_standerd_history": {
                    "type": "nested",
                    "properties": {
                        "value": {"type": "keyword"},
                        "updated_at": {"type": "date"}
                    }
                },

                # ✅ 修正：description 支持全文搜索 + 聚合
                "description": {
                    "type": "text",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256  # 超过256字符的将不被索引用于keyword
                        }
                    }
                    # ❌ 注意：text 不能有 doc_values，所以这里不能写 "doc_values": True
                },
                "description_history": {
                    "type": "nested",
                    "properties": {
                        "value": {
                            "type": "text",
                            "fields": {
                                "keyword": {
                                    "type": "keyword",
                                    "ignore_above": 256
                                }
                            }
                        },
                        "updated_at": {"type": "date"}
                    }
                },

                "opinions": {
                    "type": "text",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256
                        }
                    }
                },
                "opinions_history": {
                    "type": "nested",
                    "properties": {
                        "value": {
                            "type": "text",
                            "fields": {
                                "keyword": {
                                    "type": "keyword",
                                    "ignore_above": 256
                                }
                            }
                        },
                        "updated_at": {"type": "date"}
                    }
                },


                # === 时间戳 ===
                "create_time": {
                    "type": "date",
                    "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis||yyyy-MM-dd'T'HH:mm:ss"
                },
                "last_updated_time": {
                    "type": "date"
                }
            }
        }
    }

    created_count = 0
    for i in range(TOTAL_SHARDS):
        index_name = f"{INDEX_PREFIX}_{i:03d}"
        try:
            if not client.indices.exists(index=index_name):
                client.indices.create(index=index_name, body=index_settings)
                my_log_hd.info(f"✅ Created index: {index_name}")
                created_count += 1
            # else:
            #     my_log_hd.debug(f"ℹ️ Index already exists: {index_name}")
        except Exception as e:
            my_log_hd.error(f"❌ Failed to create index {index_name}: {e}")

    my_log_hd.info(f"🎉 Finished creating indices. Total created: {created_count}")

# ==================== 从 MySQL 分批读取数据 ====================

def fetch_data_in_batches(batch_size=BATCH_SIZE):
    """
    分批读取 MySQL 数据，防止内存溢出
    使用 _id 作为排序和分页键
    """
    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(**sql_config)
        cursor = connection.cursor(dictionary=True)

        last_id = 0
        while True:
            query = f"""
                SELECT *
                FROM profile_table1
                WHERE _id > %(last_id)s
                  AND identity IS NOT NULL
                  AND identity != ''
                ORDER BY _id
                LIMIT %(limit)s
            """
            cursor.execute(query, {"last_id": last_id, "limit": batch_size})
            batch = cursor.fetchall()

            if not batch:
                break

            last_id = batch[-1]["_id"]  # 更新最后 ID
            yield batch

            my_log_hd.info(f"📊 Fetched batch of {len(batch)} records, last _id={last_id}")

    except Exception as e:
        my_log_hd.error(f"❌ Error fetching data from MySQL: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def flush_index_buffer(client, index_name):
    """将指定索引的缓冲区数据写入 OpenSearch"""
    actions = buffered_actions[index_name]
    if not actions:
        return 0

    try:
        success, failed = helpers.bulk(
            client,
            actions,
            stats_only=False,
            raise_on_error=False,
            request_timeout=60,
            chunk_size=500,
            max_retries=3,
            initial_backoff=1,
            max_backoff=10,
        )
        my_log_hd.info(f"✅ Flush index [{index_name}]: {success} succeeded, {len(failed)} failed")
        for item in failed:
            my_log_hd.warning(f"❌ Failed to index: {item}")

        # 清空缓冲区
        buffered_actions[index_name] = []
        return success
    except Exception as e:
        my_log_hd.error(f"🚨 Flush failed for index [{index_name}]: {e}")
        return 0


#程序结束时调用，刷新缓冲，写入剩余数据
def flush_all_buffers(client):
    """
    程序结束时调用：强制刷新所有未写入的缓冲区
    """
    global buffered_actions
    total = 0
    for index_name in list(buffered_actions.keys()):
        if buffered_actions[index_name]:
            total += flush_index_buffer(client, index_name)
    my_log_hd.info(f"🔥 All buffers flushed. Total flushed indices: {len(buffered_actions)}")
    return total



def normalize_tags_to_string(mixed_data):
    """
    将多种形式的标签数据统一转换为逗号分隔的字符串。

    支持格式：
    - ('教师,其他',)              → "教师,其他"
    - ('["\\u6559\\u5e08"]',)     → "教师"
    - ('["\\u6559\\u5e08", "..."]',) → "教师,其他,农民"

    参数:
        mixed_data: tuple 或 str
    返回:
        str, 如 "教师,其他"
    """
    # 1. 提取字符串：处理 tuple 或 list
    if isinstance(mixed_data, (tuple, list)):
        s = mixed_data[0]  # 取第一个元素
    else:
        s = mixed_data

    if not s or s is None:
        return ""

    s = str(s).strip()
    if not s:
        return ""

    tags = []

    # 2. 判断是否为 JSON 数组（以 [ 开头）
    if s.startswith('['):
        try:
            # json.loads 自动解码 \u 转义
            tags = json.loads(s)
        except json.JSONDecodeError:
            # 解析失败，当作普通字符串处理
            tags = [tag.strip() for tag in s.split(',') if tag.strip()]
    else:
        # 普通字符串，按逗号分割
        tags = [tag.strip() for tag in s.split(',') if tag.strip()]

    # 3. 过滤空值并去重（可选），然后用逗号连接
    valid_tags = [t for t in tags if t]

    # 去重，保持顺序
    seen = set()
    unique_tags = []
    for t in valid_tags:
        if t not in seen:
            seen.add(t)
            unique_tags.append(t)

    return ",".join(unique_tags) if unique_tags else ""


# ==================== 批量写入 OpenSearch ====================

# def bulk_insert_to_opensearch(client, batch):
#     """
#     将一批数据写入对应的 OpenSearch 索引
#     每条记录根据 _id 计算目标索引
#     """
#     actions = []
#     for row in batch:
#         try:
#             uid = str(row['id'])
#             sitename=str(row['sitename'])
#             index_name = get_es_index_name(uid)
#
#             action = {
#                 "_index": index_name,
#                 "_id": uid + '_' + sitename,  # 确保 uid 和 sitename 不为空
#             }
#             # 构建 _source，只包含非空字段
#             source = {}
#
#             field_mapping = {
#                     "uid": row["id"],
#                     "index_suffix": row.get("sitename",''),
#                     "sitename": row.get("sitename"),
#                     "user_name": row.get("user_name"),
#                     "identity": row.get("identity"),
#                     "ientity_standerd": row.get("identity_standerd"),
#                     "name": row.get("name"),
#                     "verified_reason": row.get("verified_reason"),
#                     "description": row.get("description"),
#                     "org": row.get("org"),
#                     "contact": row.get("contact"),
#                     "create_time": row.get("create_time"),
#             }
#             for key, value in field_mapping.items():
#                 if value in (None, '', ' ', [], {}):
#                     continue
#                 source[key] = value
#
#             # 只有非空字段才添加到 _source
#             if source:  # 防止 _source 为空
#                 action["_source"] = source
#             actions.append(action)
#         except Exception as e:
#             my_log_hd.warning(f"⚠️ Skip invalid row: {e}")
#
#     if not actions:
#         return 0
#
#     try:
#         success, failed = helpers.bulk(
#             client,
#             actions,
#             stats_only=False,
#             raise_on_error=False,
#             request_timeout=60
#         )
#         my_log_hd.info(f"✅ Bulk insert: {success} succeeded, {len(failed)} failed")
#         for item in failed:
#             my_log_hd.warning(f"❌ Failed to index: {item}")
#         return success
#     except Exception as e:
#         my_log_hd.error(f"🚨 Bulk insert exception: {e}")
#         return 0


#分桶写入索引
def bulk_insert_to_opensearch_optimized(client, batch):
    """
    优化版：按索引分桶，每个索引攒够 BUFFER_SIZE 再写入
    """
    global buffered_actions

    total_written = 0
    index_batches = defaultdict(list)

    # Step 1: 按目标索引分组
    for row in batch:
        try:
            uid = str(row['id'])
            sitename = str(row['sitename'])
            index_name = get_es_index_name(uid)

            # 构建 action（同你原有逻辑）
            action = {
                "_index": index_name,
                "_id": uid + '_' + sitename,
            }

            source = {}
            identity_str = row.get("identity_standerd"),

            identity_str=normalize_tags_to_string(identity_str)
            field_mapping = {
                "uid": row["id"],
                "index_suffix": row.get("sitename", ''),
                "sitename": row.get("sitename"),
                "user_name": row.get("user_name"),
                "identity": row.get("identity"),
                "ientity_standerd": identity_str,
                "name": row.get("name"),
                "verified_reason": row.get("verified_reason"),
                "description": row.get("description"),
                "org": row.get("org"),
                "contact": row.get("contact"),
                "create_time": row.get("create_time"),
            }
            for key, value in field_mapping.items():
                if value not in ("None",None, '', ' ', [], {}):
                    source[key] = value

            if source:
                action["_source"] = source
            else:
                my_log_hd.debug(f"Skipped empty source for id={uid}, sitename={sitename}")
                continue

            index_batches[index_name].append(action)

        except Exception as e:
            my_log_hd.warning(f"⚠️ Skip invalid row: {e}")

    # Step 2: 合并到全局缓冲区，并判断是否触发 flush
    for index_name, actions in index_batches.items():
        with client_lock:  # 线程安全（如果多线程处理 batch）
            buffered_actions[index_name].extend(actions)
            print(index_name,len(buffered_actions[index_name]))
            # 如果当前索引的缓冲区 >= BUFFER_SIZE，触发 flush
            if len(buffered_actions[index_name]) >= BUFFER_SIZE:
                my_log_hd.info("{}写入数据量{}".format(index_name, len(buffered_actions[index_name])))
                total_written += flush_index_buffer(client, index_name)

    return total_written


# ==================== 主迁移函数 ====================

def migrate_data():
    """主迁移流程"""
    my_log_hd.info("🚀 Starting data migration from MySQL to OpenSearch...")

    total_imported = 0
    try:
        # for batch in fetch_data_in_batches(BATCH_SIZE):
        #     if not batch:
        #         continue
        #     count = bulk_insert_to_opensearch(client, batch)
        #     total_imported += count

        # 处理每一批数据
        for batch in fetch_data_in_batches(BATCH_SIZE):
            written = bulk_insert_to_opensearch_optimized(client, batch)
            print(f"Written (buffered): {written}")

        # my_log_hd.info(f"🎉 Migration completed! Total documents imported: {total_imported}")

    except KeyboardInterrupt:
        my_log_hd.warning("🛑 Migration interrupted by user.")
    except Exception as e:
        my_log_hd.critical(f"💥 Migration failed: {e}")
        raise

# ==================== 查询辅助函数（示例）====================

def query_user_by_uid(uid: str,sitename: str):
    """根据 uid 查询用户信息（快速定位索引）"""
    index_name = get_es_index_name(uid+'_'+sitename)
    try:
        if not client.exists(index=index_name, id=uid):
            my_log_hd.info(f"🔍 User {uid} not found in index {index_name}")
            return None

        doc = client.get(index=index_name, id=uid)
        my_log_hd.info(f"🎯 Found user {uid} in {index_name}")
        return doc['_source']
    except Exception as e:
        my_log_hd.error(f"❌ Query failed for uid={uid}: {e}")
        return None

# ==================== 主程序入口 ====================

if __name__ == "__main__":
    # 第一步：创建所有索引（首次运行时执行，之后可注释）
    # create_all_indices()  # 🔁 首次运行开启，后续可关闭

    # 第二步：开始迁移数据
    migrate_data()
    flush_all_buffers(client)

    # 示例：查询某个用户
    # result = query_user_by_uid("12345")
    # print(result)

# check_text_accounts.py

import hashlib
from opensearchpy import OpenSearch
from collections import defaultdict
import threading
import time

# ==================== 配置区（请根据实际情况修改）====================
INDEX_PREFIX_PROFILE = "user_profile"        # user_profile 索引前缀
INDEX_PREFIX_POST = "user_post_days"         # user_post_days 索引前缀
TOTAL_SHARDS = 1000                          # 分片总数：000 ~ 999

BATCH_SIZE = 500                             # 每批处理的账号数
OPENSEARCH_HOSTS = ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200']
OPENSEARCH_AUTH = ('admin', 'Zhxg09z11@')
OPENSEARCH_CA_CERTS = r'/Users/liuruixi/Desktop/minimind/user_profile_lesson/ca.cer'               # CA 证书路径，如不需要可设为 None

# ===================================================================

# 初始化 OpenSearch 客户端
client = OpenSearch(
    hosts=OPENSEARCH_HOSTS,
    http_auth=OPENSEARCH_AUTH,
    use_ssl=True,
    verify_certs=True,
    ca_certs=OPENSEARCH_CA_CERTS,
    timeout=30,
    max_retries=3,
    retry_on_timeout=True,
    send_get_body_as='POST'
)

# ========== 全局变量 ==========
print_lock = threading.Lock()
total_accounts = 0          # 总账号数（来自 user_profile）
total_with_text = 0         # 有文本记录的账号数（在 user_post 中存在）
failed_profile_indices = [] # 扫描失败的 profile 索引


# ========== 核心函数：根据 uid 计算所属索引 ==========
def get_es_index_name(uid: str, total_shards=TOTAL_SHARDS, prefix=INDEX_PREFIX_POST) -> str:
    """
    根据 uid 计算应写入的 OpenSearch 索引名
    使用 MD5 哈希确保分布均匀
    返回如: user_post_days_000 ~ user_post_days_999
    """
    uid_str = str(uid).strip()
    hash_value = int(hashlib.md5(uid_str.encode('utf-8')).hexdigest(), 16)
    shard_id = hash_value % total_shards
    return f"{prefix}_{shard_id:03d}"


# ========== 处理单个 user_profile_xxx 索引 ==========
def process_single_profile_index(profile_index_name):
    global total_accounts, total_with_text
    local_processed = 0
    local_with_text = 0
    batch_uids_to_check = []  # 缓存一批 uid，用于批量查询 user_post

    try:
        # 1. 使用 scroll 扫描当前 user_profile_xxx 索引
        query = {"query": {"match_all": {}}, "_source": ["uid"]}
        response = client.search(
            index=profile_index_name,
            body=query,
            scroll='5m',
            size=BATCH_SIZE,
            request_timeout=60
        )
        scroll_id = response['_scroll_id']
        hits = response['hits']['hits']

        while hits or batch_uids_to_check:
            # 收集本批次的 uid
            for hit in hits:
                uid = hit.get('_source', {}).get('uid')
                if uid:
                    batch_uids_to_check.append(str(uid).strip())

            # 当 batch 满或扫描结束时，执行查询
            if len(batch_uids_to_check) >= BATCH_SIZE or (not hits and batch_uids_to_check):
                # 按目标 user_post_days_xxx 分组
                post_index_to_uids = defaultdict(list)
                for uid in batch_uids_to_check:
                    target_post_index = get_es_index_name(uid)
                    post_index_to_uids[target_post_index].append(uid)

                # 对每个 user_post 分片执行 terms 查询
                for post_index, uids in post_index_to_uids.items():
                    query_post = {
                            "size": 0,
                            "aggs": {
                                "unique_uids": {
                                    "cardinality": {
                                        "field": "uid"
                                    }
                                }
                            },
                            "query": {
                                "terms": {
                                    "uid": uids  # 你的 500 个 uid
                                }
                            }
                        }
                    try:
                        resp = client.search(
                            index=post_index,
                            body=query_post,
                            request_timeout=30,
                            params={"rest_total_hits_as_int": "true"}
                        )
                        total = resp["aggregations"]["unique_uids"]
                        count = total["value"] if isinstance(total, dict) else total
                        local_with_text += count
                    except Exception as e:
                        with print_lock:
                            print(f"[ERROR] Failed to query {post_index}: {e}")

                local_processed += len(batch_uids_to_check)
                batch_uids_to_check.clear()

            # 获取下一批数据
            if hits:
                response = client.scroll(scroll_id=scroll_id, scroll='5m')
                hits = response['hits']['hits']

        # 清理 scroll 上下文
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception as e:
            with print_lock:
                print(f"[WARN] Failed to clear scroll {scroll_id}: {e}")

        # 打印当前索引处理结果
        with print_lock:
            print(f"✅ {profile_index_name}: {local_processed} accounts, {local_with_text} have text")

        # 更新全局统计
        with print_lock:
            total_accounts += local_processed
            total_with_text += local_with_text

    except Exception as e:
        with print_lock:
            print(f"[ERROR] Failed to process {profile_index_name}: {e}")
        failed_profile_indices.append(profile_index_name)


# ========== 主函数 ==========
def main():
    start_time = time.time()
    print(f"🚀 开始扫描 {TOTAL_SHARDS} 个 {INDEX_PREFIX_PROFILE}_* 索引...")
    print(f"🔍 将检查每个账号是否在 {INDEX_PREFIX_POST}_* 中有文本记录\n")

    # 逐个处理 user_profile_000 ~ user_profile_999
    for shard_id in range(TOTAL_SHARDS):
        profile_index_name = f"{INDEX_PREFIX_PROFILE}_{shard_id:03d}"
        print(f"🔍 处理 {profile_index_name} ({shard_id + 1}/{TOTAL_SHARDS})")
        process_single_profile_index(profile_index_name)

    # 输出最终结果
    elapsed = time.time() - start_time
    total_without_text = total_accounts - total_with_text

    print("\n" + "="*60)
    print("🎉 扫描完成！")
    print("="*60)
    print(f"📊 总账号数: {total_accounts:,}")
    print(f"✅ 有文本积累的账号数: {total_with_text:,}")
    print(f"❌ 无文本记录的账号数: {total_without_text:,}")
    print(f"📈 有文本账号占比: {total_with_text / total_accounts * 100:.2f}%")
    print(f"⏱️  总耗时: {elapsed:.2f} 秒 ({elapsed/60:.2f} 分钟)")
    if failed_profile_indices:
        print(f"⚠️  扫描失败的索引: {failed_profile_indices}")
    print("="*60)


# ========== 程序入口 ==========
if __name__ == "__main__":
    main()
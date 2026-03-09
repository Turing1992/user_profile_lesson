import hashlib
from opensearchpy import OpenSearch
from collections import defaultdict
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 配置区 ====================
INDEX_PREFIX_PROFILE = "user_profile"
TOTAL_SHARDS = 1000

BATCH_SIZE = 1000
QUERY_BATCH_SIZE = 100
MAX_WORKERS = 1  # 可根据服务器性能调整

# OpenSearch 配置
OPENSEARCH_HOSTS = ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200']
OPENSEARCH_AUTH = ('admin', 'Zhxg09z11@')
OPENSEARCH_CA_CERTS = r'/Users/liuruixi/Desktop/minimind/user_profile_lesson/ca.cer'
# OPENSEARCH_CA_CERTS = r'/home/lrx/临时任务/画像/user_profile_lesson/ca.cer'

# ==================================================

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
total_accounts = 0
total_user_level_updated = 0  # 更新计数器也改为 user_level
failed_profile_indices = []

# 支持的平台
TARGET_SITENAMES = {"小红书", "抖音", "快手", "bilibili"}

# 各平台粉丝数阈值（单位：人）
THRESHOLDS = {
    "小红书": {
        "头部": 1000000,
        "肩部": 500000,
        "腰部": 200000,
        "尾部": 5000
    },
    "bilibili": {
        "头部": 1000000,
        "肩部": 500000,
        "腰部": 200000,
        "尾部": 5000
    },
    "抖音": {
        "头部": 10000000,
        "肩部": 5000000,
        "腰部": 1000000,
        "尾部": 10000
    },
    "快手": {
        "头部": 5000000,
        "肩部": 2000000,
        "腰部": 500000,
        "尾部": 10000
    },
}


# ========== 核心函数：根据 uid 计算所属索引 ==========
def get_es_index_name(uid: str, total_shards=TOTAL_SHARDS, prefix=INDEX_PREFIX_PROFILE) -> str:
    uid_str = str(uid).strip()
    hash_value = int(hashlib.md5(uid_str.encode('utf-8')).hexdigest(), 16)
    shard_id = hash_value % total_shards
    return f"{prefix}_{shard_id:03d}"


# ========== 安全转换粉丝数为整数 ==========
def parse_followers(followers) -> int:
    """
    安全地将任意类型的 followers 转换为整数
    支持 str, int, float, None, 空字符串等
    """
    if followers is None:
        return 0

    if isinstance(followers, int):
        return max(0, followers)

    if isinstance(followers, float):
        return max(0, int(followers))

    if isinstance(followers, str):
        followers = followers.strip().replace(',', '').replace(' ', '')
        if not followers or followers.lower() in ['null', 'none', '']:
            return 0
        try:
            return max(0, int(float(followers)))
        except ValueError:
            return 0

    try:
        return max(0, int(followers))
    except (TypeError, ValueError):
        return 0


# ========== 判断用户等级==========
def classify_user_level(sitename: str, followers: int) -> str:
    """
    根据平台和粉丝数返回 user_level
    """
    if sitename not in THRESHOLDS:
        return "普通"

    thresholds = THRESHOLDS[sitename]
    if followers >= thresholds["头部"]:
        return "头部"
    elif followers >= thresholds["肩部"]:
        return "肩部"
    elif followers >= thresholds["腰部"]:
        return "腰部"
    elif followers >= thresholds["尾部"]:
        return "尾部"
    else:
        return "普通"


# ========== 处理单个 user_profile 索引（仅处理目标平台）==========
def process_single_profile_index(profile_index_name):
    local_processed = 0
    items_buffer = []  # 存储 {"uid": ..., "sitename": ..., "followers": ...}

    try:
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "terms": {
                                "sitename": list(TARGET_SITENAMES)
                            }
                        },
                        {
                            "exists": {
                                "field": "followers"
                            }
                        }
                    ]
                }
            },
            "_source": ["uid", "sitename", "followers"]
        }

        response = client.search(
            index=profile_index_name,
            body=query,
            scroll='5m',
            size=BATCH_SIZE
        )
        scroll_id = response['_scroll_id']
        hits = response['hits']['hits']

        while hits or items_buffer:
            for hit in hits:
                source = hit.get('_source', {})
                uid = source.get('uid')
                sitename = source.get('sitename', '').strip()
                raw_followers = source.get('followers')

                if not uid or sitename not in TARGET_SITENAMES:
                    continue

                followers = parse_followers(raw_followers)

                items_buffer.append({
                    "uid": str(uid).strip(),
                    "sitename": sitename,
                    "followers": followers
                })

            # 批量处理
            if len(items_buffer) >= QUERY_BATCH_SIZE or (not hits and items_buffer):
                batch = items_buffer[:QUERY_BATCH_SIZE]
                processed = 0
                for item in batch:
                    uid = item["uid"]
                    sitename = item["sitename"]
                    followers = item["followers"]

                    try:
                        user_level = classify_user_level(sitename, followers)

                        profile_index = get_es_index_name(uid)

                        # ✅ 更新字段名为 user_level
                        client.update(
                            index=profile_index,
                            id=uid + '_' + sitename,
                            body={
                                "doc": {"user_level": user_level},  # 修改此处
                                "doc_as_upsert": True
                            }
                        )
                        processed += 1

                        with print_lock:
                            print(f"[等级] {uid}({sitename}) → {user_level} (粉丝:{followers:,})")

                    except Exception as e:
                        with print_lock:
                            print(f"[ERROR] 更新 {uid} 失败: {e}")

                global total_user_level_updated
                total_user_level_updated += processed
                local_processed += len(batch)
                items_buffer = items_buffer[QUERY_BATCH_SIZE:]

            if hits:
                response = client.scroll(scroll_id=scroll_id, scroll='5m')
                hits = response['hits']['hits']

        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

        with print_lock:
            print(f"✅ {profile_index_name}: {local_processed} 个账号处理完成")

        return local_processed

    except Exception as e:
        with print_lock:
            print(f"[ERROR] 处理 {profile_index_name} 失败: {e}")
        failed_profile_indices.append(profile_index_name)
        return 0


# ========== 主函数 ==========
def main():
    global total_accounts, total_user_level_updated
    start_time = time.time()
    print(f"🚀 启动 {MAX_WORKERS} 线程，处理 {TOTAL_SHARDS} 个 {INDEX_PREFIX_PROFILE}_* 索引...")
    print(f"📌 仅处理 sitename 为 {list(TARGET_SITENAMES)} 的用户，根据粉丝数判断 user_level\n")

    profile_indices = [f"{INDEX_PREFIX_PROFILE}_{i:03d}" for i in range(TOTAL_SHARDS)]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_single_profile_index, idx): idx
            for idx in profile_indices
        }

        for future in as_completed(futures):
            try:
                processed = future.result()
                with print_lock:
                    total_accounts += processed
            except Exception as e:
                idx = futures[future]
                with print_lock:
                    print(f"[ERROR] 任务失败 {idx}: {e}")

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("🎉 全部处理完成！")
    print("=" * 60)
    print(f"📊 总共扫描账号数:       {total_accounts:,}")
    print(f"✅ 成功更新 user_level:  {total_user_level_updated:,}")
    print(f"⏱️  总耗时:             {elapsed:.2f} 秒 ({elapsed/60:.2f} 分钟)")
    if failed_profile_indices:
        print(f"⚠️  失败索引数:         {len(failed_profile_indices)}")
        print(f"    失败列表:           {failed_profile_indices}")
    print("=" * 60)


if __name__ == "__main__":
    main()
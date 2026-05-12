# user_profile_enhancer_dedup.py

import hashlib
from opensearchpy import OpenSearch
from collections import defaultdict
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.opinin_extract import *  # 假设 get_kind 在这里
from utils.daoding_body import daoding_body_gen
from utils.download_API import get_data
from actrie import Matcher


# ==================== 配置区 ====================
INDEX_PREFIX_PROFILE = "user_profile"
INDEX_PREFIX_POST = "user_post_days"
TOTAL_SHARDS = 1000

BATCH_SIZE = 1000
QUERY_BATCH_SIZE = 100
MAX_WORKERS = 10  # 你可以根据机器性能调大

# OpenSearch 配置
OPENSEARCH_HOSTS = ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200']
OPENSEARCH_AUTH = ('admin', 'Zhxg09z11@')
OPENSEARCH_CA_CERTS = r'/home/lrx/临时任务/画像/user_profile_lesson/ca.cer'
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
total_with_post = 0
failed_profile_indices = []


md = Matcher()
words=["外卖骑手", "外卖小哥", "外卖员", "送餐员", "快递员", "快递小哥", "快递师傅", "网约车司机", "滴滴司机", "货车司机", "卡车司机", "长途司机", "跑长途的司机", "配送员", "骑手", "司机大哥", "货运师傅", "网约配送员", "快递送货员", "网约车师傅",
       "网络主播", "自媒体创作者", "网络服务提供者", "电商主播", "娱乐主播", "公众号博主", "短视频UP主", "在线教师", "在线设计师", "远程客服", "直播达人", "带货主播", "内容创作者", "视频博主", "Vlogger", "知识博主", "直播主持人", "网红", "自媒体人", "数字游民", "自由职业者", "线上讲师", "远程工作者", "云客服", "独立设计师", "新媒体运营", "直播销售员", "短视频创作者", "图文博主", "音频主播",
       "网约家政服务人员", "社交电商从业者", "共享经济服务者", "保洁阿姨", "保姆", "月嫂", "育儿嫂", "家政阿姨", "上门保洁", "家庭维修工", "平台保洁员", "网约保姆", "网约维修工", "生活服务人员", "社区服务者", "家政服务员", "居家护理员", "钟点工", "智能家政员", "共享服务师傅",
       "自由职业者", "斜杠青年", "创意工作者", "独立设计师", "摄影师", "独立摄影师", "自由设计师", "多重职业者", "跨界人才", "灵活就业者", "个人创业者", "数字游民", "远程工作者", "兼职达人", "夜间网约车司机", "上班族兼副业者", "自由撰稿人", "独立艺术家", "自由程序员", "自由顾问", "自由插画师", "独立音乐人", "自由编剧", "独立开发者", "自由翻译", "自由讲师", "内容创作者", "品牌策划人", "独立策展人", "自由剪辑师", "自由配音员", "自由舞者", "自由教练", "自由心理咨询师", "自由律师", "独立研究员", "自由建筑师", "自由营销人", "自由电商运营", "自由投资顾问"]
md.load_from_collection(words)

# ========== 核心函数：根据 uid 计算所属索引 ==========
def get_es_index_name(uid: str, total_shards=TOTAL_SHARDS, prefix=INDEX_PREFIX_POST) -> str:
    uid_str = str(uid).strip()
    hash_value = int(hashlib.md5(uid_str.encode('utf-8')).hexdigest(), 16)
    shard_id = hash_value % total_shards
    return f"{prefix}_{shard_id:03d}"


# ========== 查询并处理一批 uid（✅ 使用 profile 中的 sitename）==========
def query_and_process_batch(uid_sitename_list: list) -> int:
    """
    输入: [{"uid": "123", "sitename": "weibo"}]
    输出: 成功处理的数量
    """
    if not uid_sitename_list:
        return 0

    # 按 post 索引分组
    post_index_to_items = defaultdict(list)
    for item in uid_sitename_list:
        uid = item["uid"]
        target_index = get_es_index_name(uid)
        post_index_to_items[target_index].append(item)

    processed_count = 0
    seen_uids = set()

    for post_index, items in post_index_to_items.items():
        uids = [item["uid"] for item in items]
        query = {
            "size": 1000,
            "_source": ["uid", "post_days"],
            "query": {
                "terms": {
                    "uid": list(set(uids))
                }
            }
        }
        try:
            resp = client.search(index=post_index, body=query, request_timeout=20)
            hits = resp["hits"]["hits"]

            # 构建 uid → post_days 映射
            uid_to_post_days = defaultdict(list)
            for hit in hits:
                source = hit["_source"]
                uid = str(source.get("uid")).strip()
                post_days = source.get("post_days", [])
                if isinstance(post_days, str):
                    post_days = [post_days]
                if not isinstance(post_days, list):
                    post_days = []
                uid_to_post_days[uid].extend(post_days)

            # 处理每个 item
            for item in items:
                uid = item["uid"]
                final_sitename = item["sitename"]# ✅ 使用 user_profile 中的 sitename
                description = item.get("description", "").strip()
                username=item.get("username","").strip()

                if uid in seen_uids:
                    continue
                seen_uids.add(uid)

                if uid not in uid_to_post_days:
                    continue  # 无发帖记录

                all_days = uid_to_post_days[uid]
                selected_days = list(dict.fromkeys(all_days))[:5]  # 去重取前10

                with print_lock:
                    print(f"[发现] {uid} 有发帖记录，共 {len(all_days)} 天，取 {len(selected_days)} 天")

                # 获取文本
                body=daoding_body_gen(uid,final_sitename,[selected_days[0]+" 00:00:00",selected_days[-1]+" 00:00:00"])
                #contents=get_data(body)
                #if contents ==[]:
                #    continue
                # for day in selected_days:
                #     try:
                #         text = get_data(uid=uid, sitename=final_sitename, )
                #         if text.strip():
                #             texts.append(text)
                #     except Exception as e:
                #         with print_lock:
                #             print(f"[WARN] 获取 {uid} 文本失败: {e}")

                # 大模型分类
                try:
                    # 获取贴文后匹配关键词
                    contents=description+"_"+username
                    #if md.findall(contents) == []:
                    #    continue
                    #print('匹配到关键词')
                    kind = get_kind(contents)  # 假设 get_kind 在 opinionin_extract 中
                    with print_lock:
                        print(f"[大模型] {uid} → 分类: {kind}")
                except Exception as e:
                    kind = "未知"
                    with print_lock:
                        print(f"[ERROR] 大模型处理 {uid} 失败: {e}")

                # 回写到 user_profile
                try:
                    profile_index = f"{INDEX_PREFIX_PROFILE}_{int(hashlib.md5(uid.encode()).hexdigest(), 16) % TOTAL_SHARDS:03d}"
                    client.update(
                        index=profile_index,
                        id=uid+'_'+final_sitename,
                        body={
                            "doc": {"content_opinion": kind['opinin'],"three_new_identity":kind['identity'],"community":kind['identity2'],"org":kind['org'],"industry":kind['industry']},
                            "doc_as_upsert": True
                        }
                    )
                    with print_lock:
                        print(f"[回写] {kind} → {profile_index}#{uid}")
                    processed_count += 1
                except Exception as e:
                    with print_lock:
                        print(f"[ERROR] 回写失败 {uid}: {e}")

        except Exception as e:
            with print_lock:
                print(f"[ERROR] 查询 {post_index} 失败: {e}")

    return processed_count


# ========== 处理单个 user_profile 索引（✅ 同时取 uid 和 sitename）==========
def process_single_profile_index(profile_index_name):
    local_processed = 0
    items_buffer = []  # ✅ 存储 {"uid": ..., "sitename": ...}

    try:
        # ✅ 查询时带上 sitename
        #query = {"query": {"match_all": {}}, "_source": ["uid", "sitename","description"]}
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "exists": {
                                "field": "description"
                            }
                        }
                    ]
                }
            },
            "_source": ["uid", "sitename", "description","three_new_identity","username"]
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
                username=source.get('username','unknown')
                sitename = source.get('sitename', 'unknown')  # 默认值
                description = source.get('description', 'unknown')
                if uid:
                    items_buffer.append({
                        "uid": str(uid).strip(),
                        "sitename": str(sitename).strip(),
                        "username":str(username).strip(),
                        "description": str(description).strip()
                    })

            if len(items_buffer) >= QUERY_BATCH_SIZE or (not hits and items_buffer):
                batch = items_buffer[:QUERY_BATCH_SIZE]
                count = query_and_process_batch(batch)
                local_processed += len(batch)
                global total_with_post
                total_with_post += count
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
    global total_accounts, total_with_post
    start_time = time.time()
    print(f"🚀 启动 {MAX_WORKERS} 线程，处理 {TOTAL_SHARDS} 个 {INDEX_PREFIX_PROFILE}_* 索引...")
    print(f"📌 使用 user_profile 中的 sitename → 匹配发帖 → 分类 → 回写\n")

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
    print(f"📊 总共扫描账号数:     {total_accounts:,}")
    print(f"✅ 有发帖记录的账号数: {total_with_post:,}")
    print(f"⏱️  总耗时:           {elapsed:.2f} 秒 ({elapsed/60:.2f} 分钟)")
    if failed_profile_indices:
        print(f"⚠️  失败索引数:       {len(failed_profile_indices)}")
    print("=" * 60)


if __name__ == "__main__":
    main()

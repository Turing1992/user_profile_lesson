import hashlib
import threading
import time
from collections import deque
from datetime import datetime
from typing import Dict, Any, List
from opensearchpy import OpenSearch, helpers,exceptions as opensearch_exceptions



TOTAL_SHARDS = 1000
INDEX_PREFIX = "user_profile"
BATCH_SIZE = 1000          # 每批 flush 的最大条数
FLUSH_INTERVAL = 5         # 最大等待时间（秒


# OpenSearch 配置
opensearch_config = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": 'ca.cer',
    "timeout": 30
}

#链接es
client = OpenSearch(**opensearch_config)

# 每个 shard 一个队列 + 一个锁
shard_queues: List[deque] = [deque() for _ in range(TOTAL_SHARDS)]
shard_locks: List[threading.Lock] = [threading.Lock() for _ in range(TOTAL_SHARDS)]

# 全局锁，用于控制 flush 线程和关闭信号
buffer_lock = threading.Lock()
stop_event = threading.Event()

#统计
stats = {
    "enqueued": 0,
    "flushed": 0,
    "failed": 0
}

stats_lock = threading.Lock()

def get_es_index_name(uid: str, total_shards=1000, prefix="user_profile") -> str:
    """
    根据 uid 计算应写入的 OpenSearch 索引名
    使用 MD5 哈希确保分布均匀
    返回如: user_profile_000 ~ user_profile_999
    """
    uid_str = str(uid).strip()
    hash_value = int(hashlib.md5(uid_str.encode('utf-8')).hexdigest(), 16)
    shard_id = hash_value % total_shards
    return f"{INDEX_PREFIX}_{shard_id:03d}", shard_id


def update_user_profile(uid: str, INDEX_SUFFIX:str,new_data: Dict[str, Any]):
    """
    供外部调用：将更新任务加入缓冲区
    线程安全，可被 20 个线程并发调用
    """
    index_name, shard_id = get_es_index_name(uid)
    doc_id = f"{uid}_{INDEX_SUFFIX}"
    update_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    task = {
        "index_name": index_name,
        "doc_id": doc_id,
        "new_data": new_data,
        "update_time": update_time,
        "uid": uid,
        "index_suffix": INDEX_SUFFIX
    }

    # 加入对应 shard 的队列
    with shard_locks[shard_id]:
        shard_queues[shard_id].append(task)

    # 统计
    with stats_lock:
        stats["enqueued"] += 1

    # 可选：如果该 shard 队列达到 BATCH_SIZE，唤醒 flush（非阻塞）
    if len(shard_queues[shard_id]) >= BATCH_SIZE:
        # flush 线程会定时检查，这里不强制唤醒也行
        pass


PAINLESS_SCRIPT = """
    boolean has_changes = false;
    for (entry in params.new_data.entrySet()) {
        String field = entry.getKey();
        Object new_value = entry.getValue();

        if (ctx._source.containsKey(field)) {
            Object current_value = ctx._source[field];
            if (current_value == null ? new_value != null : !current_value.equals(new_value)) {
                Map history_entry = new HashMap();
                history_entry.put('value', current_value);
                history_entry.put('updated_at', ctx._source.last_updated_time);

                String history_field = field + '_history';
                if (!ctx._source.containsKey(history_field)) {
                    ctx._source[history_field] = new ArrayList();
                }
                ctx._source[history_field].add(history_entry);

                if (ctx._source[history_field].size() > 10) {
                    ctx._source[history_field] = new ArrayList(
                        ctx._source[history_field].subList(
                            ctx._source[history_field].size() - 10,
                            ctx._source[history_field].size()
                        )
                    );
                }
                has_changes = true;
            }
        } else {
            has_changes = true;
        }
        ctx._source[field] = new_value;
    }
    ctx._source.last_updated_time = params.update_time;
"""


def background_flush_thread():
    """
    后台线程：定期扫描所有 shard 队列，批量写入 ES
    """
    print("Background flush thread started.")
    while not stop_event.is_set():
        start_time = time.time()

        for shard_id in range(TOTAL_SHARDS):
            # 跳过空队列
            if len(shard_queues[shard_id]) == 0:
                continue

            # 尝试获取锁
            if not shard_locks[shard_id].acquire(timeout=0.1):
                continue  # 跳过正在被操作的 shard

            try:
                queue = shard_queues[shard_id]
                if len(queue) == 0:
                    continue

                bulk_ops = []
                batch_count = 0

                # 构建最多 BATCH_SIZE 条 bulk 操作
                while queue and batch_count < BATCH_SIZE:
                    task = queue.popleft()
                    bulk_ops.append({
                        "_op_type": "update",
                        "_index": task["index_name"],
                        "_id": task["doc_id"],
                        "retry_on_conflict": 3,
                        "script": {
                            "source": PAINLESS_SCRIPT,
                            "lang": "painless",
                            "params": {
                                "new_data": task["new_data"],
                                "update_time": task["update_time"]
                            }
                        },
                        "upsert": {
                            "uid": task["uid"],
                            "index_suffix": task["index_suffix"],
                            "create_time": task["update_time"],
                            "last_updated_time": task["update_time"],
                            **task["new_data"]
                        }
                    })
                    batch_count += 1

                # 执行批量写入
                if bulk_ops:
                    try:
                        success, failed = helpers.bulk(
                            client,
                            bulk_ops,
                            raise_on_error=False,
                            ignore_status=[400, 409]  # 忽略部分错误
                        )
                        with stats_lock:
                            stats["flushed"] += success
                            stats["failed"] += len(failed)
                        if failed:
                            print(f"Shard {shard_id}: {len(failed)} failed updates.")
                    except Exception as e:
                        print(f"Bulk write failed for shard {shard_id}: {e}")
                        # 可选择将任务重新放回队列（谨慎）
                        # for task in reversed(bulk_ops): queue.appendleft(task)

            finally:
                shard_locks[shard_id].release()

        # 控制循环频率，避免空转
        elapsed = time.time() - start_time
        sleep_time = max(0, FLUSH_INTERVAL - elapsed)
        time.sleep(sleep_time)


# ================== 启动和关闭 ==================
def start_update_system():
    """
    启动更新系统：启动后台 flush 线程
    """
    flush_thread = threading.Thread(target=background_flush_thread, daemon=True)
    flush_thread.start()
    print("Update system started with background flush thread.")
    return flush_thread


def shutdown_update_system():
    """
    关闭系统：强制刷新所有队列
    """
    print("Shutting down update system...")
    stop_event.set()

    # 强制 flush 所有剩余数据
    for shard_id in range(TOTAL_SHARDS):
        if len(shard_queues[shard_id]) > 0:
            flush_shard_immediately(shard_id)

    print(f"Shutdown complete. Stats: {dict(stats)}")


def flush_shard_immediately(shard_id: int):
    """立即 flush 指定 shard（用于 shutdown）"""
    if not shard_locks[shard_id].acquire(timeout=2):
        print(f"Warning: Cannot acquire lock for shard {shard_id} during shutdown.")
        return

    try:
        if len(shard_queues[shard_id]) == 0:
            return
        # 重用 background_flush 中的逻辑
        bulk_ops = []
        while shard_queues[shard_id]:
            task = shard_queues[shard_id].popleft()
            bulk_ops.append({
                "_op_type": "update",
                "_index": task["index_name"],
                "_id": task["doc_id"],
                "retry_on_conflict": 3,
                "script": { "source": PAINLESS_SCRIPT, "lang": "painless", "params": {
                    "new_data": task["new_data"], "update_time": task["update_time"]
                }},
                "upsert": { "uid": task["uid"], "index_suffix": task["index_suffix"],
                          "create_time": task["update_time"], "last_updated_time": task["update_time"],
                          **task["new_data"] }
            })
        if bulk_ops:
            success, failed = helpers.bulk(client, bulk_ops, raise_on_error=False)
            with stats_lock:
                stats["flushed"] += success
                stats["failed"] += len(failed)
    except Exception as e:
        print(f"Final flush failed for shard {shard_id}: {e}")
    finally:
        shard_locks[shard_id].release()


if __name__ == '__main__':
    # === 在节点启动时调用一次 ===
    flush_thread = start_update_system()


    # === 20 个线程中任意位置调用 ===
    def worker_thread():
        for i in range(1000):
            uid = f"user_{i}"
            new_data = {"score": i * 10, "tags": [f"tag_{i % 3}"]}
            update_user_profile(uid, new_data)  # 非阻塞，快速返回


    # === 程序退出时调用 ===
    shutdown_update_system()

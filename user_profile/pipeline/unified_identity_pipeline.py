# -*- coding: utf-8 -*-
"""
统一身份判断管线（单消费组版本）。

一个 consumer 订阅 spider_data topic，每条消息依次匹配所有任务的关键词，
命中哪个任务就分发到对应的 worker 队列处理。

使用方式：
    python unified_identity_pipeline.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import queue
import threading
import signal
import time
import traceback
import redis
from collections import defaultdict
import ujson as json

from utils.prompts import *
from utils.http_llm_factory import *
from utils.about_log import get_logger
from utils.opinin_extract import get_kind, get_kind2, get_kind_wangyueche, get_kind_huoche
from config.settings import config
from utils.bloom import BloomFilter
from utils.data_processor import data_process
from utils.mq_client import ProducerMQ
from utils.identity_mapper import load_identity_mapping, standardize_identity
from utils.community_filter import CommunityFilter
from utils.es_updata_new import update_single_profile
from actrie import Matcher

from rocketmq import (
    DefaultMQPushConsumer,
    MessageListenerConcurrently,
)


# 身份判断函数映射
IDENTITY_FUNC_MAP = {
    "get_kind": get_kind,
    "get_kind2": get_kind2,
    "get_kind_wangyueche": get_kind_wangyueche,
    "get_kind_huoche": get_kind_huoche,
}


def load_task_configs():
    # type: () -> dict
    """加载任务配置文件。"""
    config_path = os.path.join(os.path.dirname(__file__), "task_configs.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.loads(f.read())


# 全局加载身份映射表（所有任务共用）
identity_map = load_identity_mapping()


class Drawing(object):
    """身份识别处理器，根据任务配置执行不同的身份判断逻辑。"""

    def __init__(self, task_config, logger):
        # type: (dict, object) -> None
        self.task_config = task_config
        self.logger = logger
        self.redis_cache_identity_bloom = config["redis"]["redis_url_identity_bloom"]
        self.identity_bloom_key = config["redis"][task_config["bloom_key"]]
        self.age_cache = defaultdict(list)
        self.bloom_filter = BloomFilter(self.redis_cache_identity_bloom, self.identity_bloom_key)
        self.identity_func = IDENTITY_FUNC_MAP[task_config["identity_func"]]
        self.content_mode = task_config["content_mode"]
        # community 过滤器：排除广告/商家/影视等非目标人群账号
        self.community_filter = CommunityFilter(task_config.get("community_filter"))
        if self.community_filter.enabled:
            self.logger.info(
                "community过滤已启用, junk关键词数={}, 商家认证过滤={}".format(
                    len(self.community_filter.junk_keywords),
                    self.community_filter.filter_merchant_verified,
                )
            )

    def run(self, datas):
        # type: (list) -> None
        inputs = []
        try:
            for name_index, yaunshi_data in enumerate(datas):
                dd = {}
                yaunshi_data["input_id"] = str(name_index)
                yaunshi_data["user_name"] = yaunshi_data["name"]
                del yaunshi_data["name"]
                if yaunshi_data["user_name"]:
                    dd["账号名"] = yaunshi_data["user_name"]
                if yaunshi_data["verified_reason"]:
                    dd["账号认证原因"] = yaunshi_data["verified_reason"]
                if yaunshi_data["description"]:
                    dd["账号自我介绍"] = yaunshi_data["content"] + yaunshi_data["description"]
                if dd == {}:
                    continue
                dd['input_id'] = str(name_index)
                inputs.append(json.dumps(dd, ensure_ascii=False))

            self.logger.info(json.dumps(inputs, ensure_ascii=False, indent=2))
            results, info_response_id, response_content = get_user_infos(
                USER_INFOS, json.dumps(inputs, ensure_ascii=False, indent=2), self.logger
            )
            if info_response_id == 0:
                self.logger.error("请求出错-{}".format(json.dumps(inputs, ensure_ascii=False, indent=2)))
                return

            if len(results) != len(inputs):
                self.logger.error("结果数量不一致-{}-{}--{}".format(
                    info_response_id, json.dumps(inputs, ensure_ascii=False, indent=2), response_content
                ))

            self.logger.info("{}-{}".format(len(results), len(inputs)))
            results_lookup = {}
            self.logger.info("请求id-{}".format(info_response_id))
            self.logger.info(json.dumps(results, ensure_ascii=False, indent=2))
            for result in results:
                results_lookup[str(result['input_id'])] = result

            for data in datas:
                self.logger.info("input_id-{}".format(data))
                idx = data["input_id"]
                if idx in results_lookup:
                    final_result = results_lookup[idx]
                    data["info_response_id"] = info_response_id
                    data["identity"] = final_result.get('identity', [])
                    data['identity_standerd'] = standardize_identity(data['identity'], identity_map)
                    data['name'] = final_result.get('name', [])
                    data['age'] = final_result.get('age', [])

                    # 根据 content_mode 构建身份判断的输入内容
                    if self.content_mode == "concat_all":
                        if data['content'] != "":
                            content = data['content'] + data['description'] + str(data['name']) + data['verified_reason']
                        else:
                            content = data['description'] + str(data['name']) + data['verified_reason']
                        three_news = self.identity_func(content)
                    else:
                        # content_only 模式
                        if data['content'] != "":
                            three_news = self.identity_func(data['content'])
                        else:
                            three_news = {"identity": "", "identity2": "", "log": ""}

                    data['three_new_identity'] = three_news['identity']
                    # 应用 community 过滤器
                    raw_community = three_news['identity2']
                    filtered_community = self.community_filter.apply(
                        raw_community,
                        data.get('user_name', ''),
                        data.get('description', ''),
                        data.get('verified_reason', ''),
                    )
                    if raw_community and not filtered_community:
                        self.logger.info(
                            "community过滤命中: uid={} name={} 原community={} -> 清空".format(
                                data.get('id'),
                                data.get('user_name', ''),
                                raw_community,
                            )
                        )
                    data['community'] = filtered_community

                    try:
                        processed_data = data_process(data)
                        self.logger.info("处理数据最终为{}".format(processed_data))
                        update_single_profile(processed_data)
                    except Exception as e:
                        self.logger.error("Failed to enqueue ES update for {}: {}".format(
                            data['id'], traceback.format_exc()
                        ))
                        self.logger.error("出错数据为{}".format(data))

                    # 添加到 bloom filter
                    bloom_value = {
                        "sitename": data["sitename"],
                        "id": data["id"],
                        "url": data["url"],
                        "name": data["user_name"],
                    }
                    bloom_value = json.dumps(bloom_value, ensure_ascii=False, sort_keys=True)
                    self.bloom_filter.add_value(bloom_value)
                    self.logger.info("添加bloom-{}".format(bloom_value))
                else:
                    self.logger.error("未被处理的数据为-{}-{}".format(
                        info_response_id, json.dumps(data, ensure_ascii=False, indent=2)
                    ))
        except Exception as e:
            self.logger.exception("Error processing line: {}".format(traceback.format_exc()))
            return None


class DrawingWrapper(object):
    def __init__(self, task_config, logger):
        # type: (dict, object) -> None
        self.drawing = Drawing(task_config, logger)
        self.logger = logger

    def async_run(self, datas):
        # type: (list) -> None
        try:
            return self.drawing.run(datas)
        except Exception as e:
            self.logger.exception("Worker error: {}".format(traceback.format_exc()))


class UnifiedListener(MessageListenerConcurrently):
    """统一 MQ 消息监听器。

    单消费组订阅 spider_data，每条消息依次匹配所有任务的关键词，
    命中则分发到对应任务的 queue。一条消息可以同时命中多个任务。
    """

    def __init__(self, task_dispatchers, logger):
        # type: (list, object) -> None
        """
        Args:
            task_dispatchers: 列表，每项为 dict:
                {
                    "name": 任务名,
                    "matcher": Matcher 实例,
                    "bloom_filter": BloomFilter 实例,
                    "task_queue": queue.Queue,
                    "filter_verified": bool,
                }
        """
        self.task_dispatchers = task_dispatchers
        self.logger = logger
        self.redis_quchong = redis.from_url(config["redis"]["redis_quchong"])
        self.REDIS_EXPIRE_SECONDS = 20 * 60

    def consume_message(self, msgs):
        for msg in msgs:
            try:
                raw = json.loads(msg.body.decode('utf-8', 'ignore'))
                if raw["index_suffix"].startswith("rank"):
                    continue
                if raw["index_suffix"] in ["oversea", "youtube", "facebook", "twitter", "titok"]:
                    continue
                data = raw["data"]
                user = data.get("user")
                if not user or not user.get("uid"):
                    continue

                url = data.get("url", "    ")
                if url[-4:] in ["#ocr", "#asr", "#att"]:
                    continue

                site_name = str(data.get("gather", {}).get("site_name", ""))
                uid = str(user["uid"])
                content = data.get("content", "")

                queue_data = {
                    "id": uid,
                    "url": url,
                    "content": content,
                    "sitename": site_name,
                    "name": user.get("name", ""),
                    "verified_reason": user.get("verified_reason", ""),
                    "description": user.get("description", ""),
                    "gender": user.get("gender", ""),
                    "ip_region": user.get("ip_region", []),
                    "followers_count": str(user.get("followers_count", 0)),
                    "friends_count": str(user.get("friends_count", 0)),
                }
                if queue_data["ip_region"] != []:
                    queue_data["ip_region"] = queue_data["ip_region"][0]

                # 依次匹配每个任务
                for dispatcher in self.task_dispatchers:
                    # verified 过滤（快递员任务需要）
                    if dispatcher["filter_verified"] and user.get("verified", "") != 0:
                        continue

                    # Matcher 关键词过滤
                    if dispatcher["matcher"].findall(''.join(content)) == []:
                        continue

                    # Bloom 去重（每个任务独立 bloom）
                    user_data = {
                        "sitename": site_name,
                        "id": uid,
                        "url": url,
                        "name": user.get("name", ""),
                    }
                    bloom_value = json.dumps(user_data, ensure_ascii=False, sort_keys=True)
                    if dispatcher["bloom_filter"].is_double(bloom_value):
                        continue

                    # 检查是否有有效的身份信息字段
                    dd = {}
                    if user.get("name"):
                        dd["账号名"] = user.get("name")
                    if user.get("verified_reason"):
                        dd["账号认证原因"] = user.get("verified_reason")
                    if user.get("description"):
                        dd["账号自我介绍"] = user.get("description")
                    if dd == {}:
                        continue

                    # 分发到对应任务队列
                    try:
                        dispatcher["task_queue"].put(queue_data.copy(), block=False)
                    except queue.Full:
                        self.logger.warning("队列满，丢弃消息: task={} uid={}".format(
                            dispatcher["name"], uid))

            except Exception as e:
                self.logger.error("Message processing error: {}".format(traceback.format_exc()))


def main():
    logger = get_logger("unified_pipeline", "WARNING")

    all_configs = load_task_configs()
    task_names = list(all_configs.keys())

    print("\n统一身份判断管线（单消费组模式）")
    print("任务: {}".format(", ".join(task_names)))
    print("=" * 50)

    # 为每个任务创建 matcher、bloom、queue、worker
    task_dispatchers = []
    for task_name, task_config in all_configs.items():
        task_logger = get_logger(task_config["log_name"], "WARNING")

        # Matcher
        md = Matcher()
        md.load_from_collection(task_config["matcher_keywords"])

        # Bloom
        bloom_key = config["redis"][task_config["bloom_key"]]
        bloom_filter = BloomFilter(config["redis"]["redis_url_identity_bloom"], bloom_key)

        # Queue
        task_queue = queue.Queue(maxsize=1000)

        dispatcher = {
            "name": task_name,
            "matcher": md,
            "bloom_filter": bloom_filter,
            "task_queue": task_queue,
            "filter_verified": task_config.get("filter_verified", False),
        }
        task_dispatchers.append(dispatcher)

        # Worker 线程
        worker_count = task_config.get("worker_threads", 10)

        def make_worker(q, cfg, lg):
            def worker():
                dw = DrawingWrapper(cfg, lg)
                datas = []
                keys = set()
                while True:
                    try:
                        data = q.get(timeout=1)
                        double_key = data['url']
                        if double_key in keys:
                            continue
                        else:
                            keys.add(double_key)
                        datas.append(data)
                        q.task_done()
                        if len(datas) >= 20:
                            dw.async_run(datas)
                            datas = []
                            keys = set()
                    except queue.Empty:
                        continue
            return worker

        for _ in range(worker_count):
            t = threading.Thread(
                target=make_worker(task_queue, task_config, task_logger),
                daemon=True,
            )
            t.start()

        print("  [{}] {} 个 worker, 关键词: {}".format(
            task_name, worker_count,
            ",".join(task_config["matcher_keywords"][:3]) + "..."
        ))

    # 启动单个 MQ consumer（统一消费组）
    consumer_group = "unified_identity_consumer_group"
    consumer = DefaultMQPushConsumer(consumer_group)
    consumer.namesrv_addr = config["mq_url"]
    consumer.consume_thread_num = 1
    consumer.consume_message_batch_max_size = 1
    consumer.registerMessageListener(UnifiedListener(task_dispatchers, logger))
    consumer.subscribe(config["topic"]["spider_data"], "*")
    consumer.start()

    print("\nMQ consumer 启动完成")
    print("  消费组: {}".format(consumer_group))
    print("  topic: {}".format(config["topic"]["spider_data"]))
    print("  namesrv: {}".format(config["mq_url"]))
    print("\n运行中... 按 Ctrl+C 停止")

    # 优雅关闭
    def signal_handler(signum, frame):
        print("\n收到停止信号，正在关闭...")
        os._exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        print("关闭中...")


if __name__ == "__main__":
    main()

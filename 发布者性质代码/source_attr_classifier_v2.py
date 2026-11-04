# -*- coding: utf-8 -*-
"""发布者性质分类 v2 —— 实时流程（消费 MQ → 判定 → 下发 MQ + 结果 redis）。

读写契约与 v1(source_attr_classifier_single_thread.py) 完全一致，下游无需改动：

  消费： topic=prod_live_common_data  group=user_graph_check_user_consumer
         预过滤：(未认证 或 wtype!=1) 且有uid → 跳过；url 以 #ocr/#asr/#att 结尾 → 跳过
  下发： topic=user_graph_drawed_source_attrs_topic
         key  = sitename^uid（uid 为空时用 sitename^wm_site_domain）
         body = {sitename,id,name,verified,verified_reason,description,wm_site_domain,kind}
                + v2 附加 {source,reason}（下游可忽略）
         仅 kind != 自媒体 才下发
  结果 redis： 192.168.187.3/2   key=sitename^uid
         value = {"1":[性质], "2":判定理由全文}   ← 与 v1 同格式
         抖音站点额外写火山 redis db13；仅 kind != 自媒体 才写

v2 相对 v1 的判定链变化：
  1. 去掉 bloom 去重，改用 ClickHouse 认证账号库「查库复用 + 跨平台一致」。
  2. 媒体矩阵之后新增【高频过滤】(redis db14/db15)，命中直接自媒体。
  3. 新增【短剧/剧场号 → 自媒体】，位置在查 CH 之前（否则 v1 存量的"企业官方"
     旧结论会被 ch_reuse 原样复用，绕过这条规则）。
  4. 认证状态一律以【实时消息】user.verified 为准，画像库只补资料。
  5. 机构类结果用 similar_accounts 归并跨平台同源主体。
  6. LLM 改用 qwen（llm_qwen.chat）+ parse_llm_result 结构化解析。
     ⚠️ 不再用 utils.http_llm_factory.xingzhi_kind：它内部标签词表只有 6 个
     （不含 中央/省级/地方），会把分级标签过滤成空；且是 while True 死循环重试，
     API 持续失败会永久阻塞消费线程。

判定链：
  rank/境外 → 人工名单 → 媒体矩阵 → UGC? → 高频库 → 未认证 → 短剧号 → 查CH复用
           → 画像补资料 → 企业官方规则 → LLM → 一致性协调 → 写CH → 下发
"""
import json
import os
import signal
import sys
import threading
import time
import traceback
from collections import Counter

import redis

from utils.about_log import *          # noqa: F401,F403  (config_log)
from utils.prompts import UGC_KINDS_LAST
from rocketmq import (DefaultMQProducer, DefaultMQPushConsumer, Message,
                      MessageListenerConcurrently)

from ch_store import CHStore, consistency_reconcile
from hf_filter_lite import HFLookup
import llm_qwen
from llm_qwen import chat as llm_chat
from llm_batch import LLMBatcher
from daily_stats import DailyStats
# 判定逻辑与词表统一取 classify_core，避免与测试/演示链路漂移
from classify_core import (normalize_domain, normalize_kind_strict,
                           parse_llm_result, is_drama_account,
                           is_enterprise_official, is_unverified, pick)
import entity_service as ES

# HOSTNAME 在容器里由 docker 注入；裸机（尤其 zsh）可能没有，必须兜底，
# 否则 config_log(None, …) 会在 None + ".log" 处直接抛 TypeError 启动失败。
#
# 第二个参数是【控制台(stdout)】的级别，也就是 docker logs 能看到什么；
# 文件日志固定 DEBUG 全量落在 logs/<HOSTNAME>.log。
# 默认给 INFO：ERROR 会把判定过程和 dry-run 输出全过滤掉，上线观察时啥也看不见。
mylog_hd = config_log(os.environ.get("HOSTNAME") or "source_attr_v2",
                      os.environ.get("SA_LOG_LEVEL", "INFO"))

# ────────────────────────────── 配置（均可用环境变量覆盖）──────────────────────────────
NAMESRV = os.environ.get(
    "SA_MQ_NAMESRV",
    "yqms-rocketmq-broker1-master.istarshine.net.cn:9876;"
    "yqms-rocketmq-broker2-master.istarshine.net.cn:9876")
SRC_TOPIC = os.environ.get("SA_SRC_TOPIC", "prod_live_common_data")
SRC_TAG = os.environ.get("SA_SRC_TAG", "*")
# 用 v1 已注册的消费组（新建的 ..._v2 组在 broker 上注册不上，控制台看不到消费者）。
# ⚠️ 与 v1 同组 = 两者【分摊】消息，不是各自拿全量。所以 v2 跑起来之前要先停 v1，
#    否则同一账号可能这次被 v1 判（旧口径：个体户算企业官方、广电不分级）、
#    下次被 v2 判（新口径），结果在同一个结果 redis 和 topic 里混着写。
CONSUMER_GROUP = os.environ.get("SA_CONSUMER_GROUP",
                                "user_graph_check_user_consumer")
DST_TOPIC = os.environ.get("SA_DST_TOPIC", "user_graph_drawed_source_attrs_topic")
PRODUCER_GROUP = os.environ.get("SA_PRODUCER_GROUP",
                                "user_graph_drawed_source_attrs_producer")
CONSUME_THREADS = int(os.environ.get("SA_CONSUME_THREADS", "1"))
CONSUME_BATCH = int(os.environ.get("SA_CONSUME_BATCH", "5"))
# ⚠️ 单位是 MB 不是条数（映射到 max_cache_msg_size_pre_queue，语义同 Java 的
# pullThresholdSizeForQueue，官方默认 100 MiB/队列）。曾误当条数设成 2000，
# 等于允许每队列缓存 2000MB，单容器内存被顶到约 1.2 GiB。
MAX_CACHE_PER_QUEUE = int(os.environ.get("SA_MAX_CACHE_PER_QUEUE", "10"))

# 是否在判定时【实时】写结果 redis。1=写（v1 以来的行为），0=不写。
# 关闭后结果 redis 完全由每日同步作业（sync_result_redis.py）维护，
# 好处是 redis 以 CH 为唯一基准、不会出现"实时写过但后来被一致性收敛改了"
# 的陈旧值；代价是新判定要等下一次同步才可见（最多 24 小时）。
# ⚠️ 关掉它就必须把 sync_result_redis.py 挂上 cron，否则 redis 会停止更新。
WRITE_RESULT_REDIS = os.environ.get(
    "SA_WRITE_RESULT_REDIS", "1") not in ("0", "false", "False")

RESULT_REDIS_URL = os.environ.get("SA_RESULT_REDIS_URL", "redis://192.168.187.3/2")
HUOSHAN_REDIS_URL = os.environ.get(
    "SA_HUOSHAN_REDIS_URL",
    "redis://filter:Filter5352@huoshan-filter-redis.istarshine.net.cn/13")

# dry-run：走完整判定但不下发 MQ、不写 redis、不写 CH（上线前验证用）
DRY_RUN = os.environ.get("SA_DRY_RUN", "").lower() in ("1", "true", "yes")
# 每处理多少条打印一次统计（速率 + 来源分布 + 性质分布）；置 0 关闭
STAT_EVERY = int(os.environ.get("SA_STAT_EVERY", "200"))
# 逐条打印判定结果（含理由）。量大时别开，仅排查用
LOG_DETAIL = os.environ.get("SA_LOG_DETAIL", "").lower() in ("1", "true", "yes")
# 心跳间隔（秒）：没消息时也要有输出，用来区分"进程卡住"和"上游没数据"
HEARTBEAT_SEC = int(os.environ.get("SA_HEARTBEAT_SEC", "60"))
# 建同源主体的后台线程数（0 = 同步做）。异步是为了不占用消费线程，
# 主体表只服务于一致性收敛，晚几百毫秒建好不影响本条判定结果。
ENTITY_ASYNC_WORKERS = int(os.environ.get("SA_ENTITY_ASYNC_WORKERS", "4"))
# 建主体在途任务上限。ThreadPoolExecutor 的队列是【无界】的，submit() 永远不会
# 因为满而抛异常，所以不加这个上限就没有任何反压：建主体一个任务要查画像
# （entity_service._query 是 3 次重试 × 20s 超时，最坏 60s/次，且一个任务可能
# 查多个索引），画像库一慢，4 个 worker 的吞吐就从约 8 任务/秒塌到接近 0，
# 而提交端速率不变 → 队列每小时净增约 1 万项，每项闭包还captured 了完整画像
# 文档(KB 级)。16 个容器同机，持续降级一天就是 GB 级堆积直到 OOM kill，
# 而 OOM 走 SIGKILL 不执行 cleanup，排队的主体任务全部无声消失。
# 到上限后改为【同步执行】：占住消费线程，把压力如实传导回上游，而不是静默堆积。
ENTITY_MAX_PENDING = int(os.environ.get("SA_ENTITY_MAX_PENDING", "500"))
# 关闭时最多等建主体收尾多少秒。ThreadPoolExecutor.shutdown(wait=True) 会把
# 已排队任务全部跑完，堆积时可能要几十分钟，必然超过 docker stop 的 10s 宽限期
# 而被强杀 —— 等于"等主体收尾"这个好意在最需要它的时候反而制造了一次强杀。
# ⚠️ 20 → 10：K8s 的 terminationGracePeriodSeconds 默认只有 30 秒，
# 关闭流程还要留时间给 consumer.shutdown、LLM 批量器收尾和统计落盘，
# 建主体这一步等太久会导致整个优雅关闭被 SIGKILL 打断。
ENTITY_SHUTDOWN_WAIT = float(os.environ.get("SA_ENTITY_SHUTDOWN_WAIT", "10"))
# 每日统计：落盘目录与周期（秒）。产出 判定量/各来源分布/LLM token 用量
STATS_DIR = os.environ.get("SA_STATS_DIR", "stats")
STATS_FLUSH_SEC = int(os.environ.get("SA_STATS_FLUSH_SEC", "300"))

# mediaIndustry 映射（投诉…等）——映射规则待定，先留空、不生效
INDUSTRY_MAP = {}

# LLM 批量聚合器：prompt 本身支持批量输入输出，单条调用会把 2000+ tokens 的
# 分类定义反复重发，实测直接撞配额上限(429 Allocated quota exceeded)。
# 批量 10 条可把 token 降到约 1/8、请求数降到 1/10。
# ⚠️ normalizer 必须用 strict 版：normalize_kind 会把「空/词表外标签」兜底成
# "自媒体" 并带 ok=True 返回，模型漏答一条就静默产出一个假结论写进 CH、
# 被 TTL 固化再被 ch_reuse 扩散，而 LLM 失败计数里看不到。
# strict 版认不出返回 ""，上层据此丢弃该条，等下次消息重判。
_batcher = LLMBatcher(llm_chat, UGC_KINDS_LAST, normalizer=normalize_kind_strict,
                      logger=mylog_hd)

# 下发 MQ 的消息体字段白名单：前 8 个是 v1 契约，下游按这些字段读；
# source/reason 是 v2 附加信息。内部字段（domain/update_time）不下发。
DISPATCH_FIELDS = ("sitename", "id", "name", "verified", "verified_reason",
                   "description", "wm_site_domain", "kind", "source", "reason")

# 人工名单：(domain, uid) → (kind, 备注)。命中后在媒体矩阵之前直接定性，
# 用来纠正媒体矩阵等上游标签的错误（如上海市场监管被矩阵标成商媒）。
# 文件格式见 config/manual_override.tsv；进程启动时读取一次。
MANUAL_OVERRIDE_FILE = os.environ.get(
    "SA_MANUAL_OVERRIDE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "config", "manual_override.tsv"))
_MANUAL_KINDS = ("中央", "省级", "地方", "政务媒体", "商业媒体",
                 "企业官方", "社会组织", "其他", "自媒体")


def load_manual_overrides(path):
    """读人工名单。文件不存在返回空表；坏行跳过并打日志，不影响启动。"""
    table = {}
    if not os.path.isfile(path):
        mylog_hd.warning("人工名单文件不存在，按空名单处理: %s" % path)
        return table
    with open(path, encoding="utf-8") as f:
        for no, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) < 3 or not parts[0] or not parts[1] \
                    or parts[2] not in _MANUAL_KINDS:
                mylog_hd.warning("人工名单第 %d 行格式不对，已跳过: %r" % (no, line[:80]))
                continue
            table[(parts[0], parts[1])] = (parts[2], parts[3] if len(parts) > 3 else "")
    mylog_hd.info("人工名单已加载 %d 条: %s" % (len(table), path))
    return table


MANUAL_OVERRIDES = load_manual_overrides(MANUAL_OVERRIDE_FILE)

# 允许下发的性质标签（自媒体不下发；"其他"要下发，与 v1 一致）
DISPATCH_KINDS = ("中央", "省级", "地方", "政务媒体", "商业媒体",
                  "企业官方", "社会组织", "其他")

# run() 用这个键带出「这条为什么被丢弃」。裸 return None 会让丢弃原因彻底丢失，
# 结果 daily_stats 的 model_error 列恒为 0，LLM 失败与 rank/境外的正常过滤
# 混成同一个"丢弃量"，事后无法回答"今天有多少账号因为模型失败被丢了"。
DROP_MARK = "__drop__"

# ── 降级路径的错误日志限流 ──
# 这些错误是【每条消息】都可能触发的，依赖一挂就是日志风暴：
# 40 条/秒/容器 × 16 容器 × 约 300B ≈ 16GB/天，且 ERROR 同时进文件 sink 和
# stdout，stdout 那份走 docker json-file 默认不轮转不过期，一次半天的故障
# 就能把宿主磁盘写掉上百 GB（顺带 loguru 的 enqueue 异步队列也会吃内存）。
# 同类错误每 SA_ERR_LOG_INTERVAL 秒最多打一条，并带上被压掉的次数 ——
# "出了什么事"和"有多严重"都保住了，量却降到每类每 30 秒 1 行。
ERR_LOG_INTERVAL = float(os.environ.get("SA_ERR_LOG_INTERVAL", "30"))
_err_last = {}
_err_hits = Counter()
_err_lock = threading.Lock()


def log_err_throttled(tag, msg):
    """按 tag 分类限流打 ERROR。返回是否真的打了（便于测试）。"""
    now = time.time()
    with _err_lock:
        _err_hits[tag] += 1
        if now - _err_last.get(tag, 0.0) < ERR_LOG_INTERVAL:
            return False
        n = _err_hits[tag]
        _err_hits[tag] = 0
        _err_last[tag] = now
    tail = ("  ← %.0fs 内同类共 %d 次" % (ERR_LOG_INTERVAL, n)) if n > 1 else ""
    mylog_hd.error("[%s] %s%s" % (tag, msg, tail))
    return True


class ProducerMQ:
    def __init__(self, host, groupid):
        self.producer = DefaultMQProducer(groupid)
        self.producer.namesrv_addr = host
        self.producer.send_latency_fault_enable = False
        self.producer.max_message_size = 30000000
        self.producer.start()

    def send2mq(self, info_json, key, topic):
        msg = Message(topic=topic, body=info_json)
        msg.wait_store_msg_ok = True
        msg.keys = key
        err = ""
        for _ in range(3):
            try:
                self.producer.sendOneway(msg=msg)
                return ""
            except Exception as e:  # noqa: BLE001
                err = str(e)
        return err

    def close(self):
        try:
            self.producer.shutdown()
        except Exception:  # noqa: BLE001
            pass


class UserData:
    def __init__(self):
        # 下游结果 redis（供下游消费，格式与 v1 一致）
        self.redis_pool_ugc = redis.ConnectionPool.from_url(
            RESULT_REDIS_URL, max_connections=10, retry_on_timeout=True)
        self.redis_conn_ugc = redis.Redis(connection_pool=self.redis_pool_ugc)
        self.huoshan_redis_pool_ugc = redis.ConnectionPool.from_url(
            HUOSHAN_REDIS_URL, max_connections=10, retry_on_timeout=True)
        self.huoshan_redis_conn_ugc = redis.Redis(
            connection_pool=self.huoshan_redis_pool_ugc)
        # 高频库 + CH 认证账号库
        self.hf = HFLookup()
        self.ch = CHStore()
        # 建同源主体的后台线程池：这活儿要写 2 张表、成员多时是多行，
        # 放在消费线程里做会白占几百毫秒，而它只服务于一致性收敛，可以晚一点。
        self._entity_pool = None
        # 在途计数：ThreadPoolExecutor 队列无界，只能自己数，超过上限转同步
        self._entity_inflight = 0
        self._entity_peak = 0            # 峰值，打进心跳便于观察是否在堆积
        self._entity_sync = 0            # 因到上限而转同步的次数
        self._entity_lock = threading.Lock()
        if ENTITY_ASYNC_WORKERS > 0:
            try:
                from concurrent.futures import ThreadPoolExecutor
                self._entity_pool = ThreadPoolExecutor(
                    max_workers=ENTITY_ASYNC_WORKERS)
            except Exception:  # noqa: BLE001
                self._entity_pool = None

    def entity_stats(self):
        with self._entity_lock:
            return {"inflight": self._entity_inflight, "peak": self._entity_peak,
                    "sync": self._entity_sync, "limit": ENTITY_MAX_PENDING}

    # ── 外部依赖统一降级封装：任何外部故障都不能让消息整条丢失 ──
    # ⚠️ 这些降级路径里的 ERROR 一律走 log_err_throttled 而不是 mylog_hd.error：
    # 它们是【每条消息】都可能触发的，依赖一挂就变成日志风暴。按 40 条/秒/容器
    # × 16 容器 × 约 300B 算是 16GB/天，而 ERROR 同时进文件 sink 和 stdout，
    # stdout 那份走 docker json-file 驱动、默认既不轮转也不过期，
    # 一次半天的依赖故障就能把宿主磁盘写掉上百 GB。
    def _hf_hit(self, uid, domain):
        # ⚠️ 必须传 refresh=False。is_high_freq 默认 refresh=True 会在命中时
        # 给 db15 的 key 续期 7 天，而 db15 是【别的系统】(daily_run/hf_filter)
        # 维护的"最近 7 天仍高频"滑动窗口：
        #   1) 活跃账号天天有消息 → 每条都续期 → key 永不过期 → 账号一旦被打上
        #      高频标记就永久是"自媒体"，即使早已不高频也再不会被重新判定；
        #   2) 这是只读路径，却改写了另一个系统的状态，破坏它的窗口统计。
        # 与已修的 ch_reuse 续期 bug 完全同型。classify_core 的演示链路写对了
        # (refresh=False)，唯独生产链路漏传。
        try:
            return bool(self.hf.is_high_freq(uid, domain, refresh=False))
        except Exception:  # noqa: BLE001
            log_err_throttled("hf", "高频库查询失败(降级为未命中): %s"
                           % traceback.format_exc()[-200:])
            return False

    def _ch_query(self, domain, uid):
        try:
            return self.ch.query_by_uid(domain, uid)
        except Exception:  # noqa: BLE001
            log_err_throttled("ch_query", "CH 查询失败(降级为无缓存，继续走规则/模型): %s"
                           % traceback.format_exc()[-200:])
            return None

    def _ch_upsert(self, ud):
        if DRY_RUN:
            return
        try:
            self.ch.upsert(ud)
        except Exception:  # noqa: BLE001
            log_err_throttled("ch_upsert", "CH 写入失败(结果仍会下发): %s"
                           % traceback.format_exc()[-200:])

    def _profile(self, domain, uid, site_name=""):
        # site_name 必须传：注册域 qq.com 无法区分微信/QQ浏览器，
        # 只有站点名才能定位到 media_weixin 索引
        try:
            return ES.fetch_one(domain, uid, site_name) or {}
        except Exception:  # noqa: BLE001
            log_err_throttled("profile", "画像查询失败(降级为无画像资料): %s"
                           % traceback.format_exc()[-200:])
            return {}

    def _build_entity(self, domain, uid, name, kind, profile=None, site_name="",
                      source="stream"):
        """建同源主体。默认丢给后台线程池异步做。

        建主体要写 2 张表（主体结论 + 成员映射，成员多时是多行），
        同步做会把消费线程再占住几百毫秒。而主体表只服务于一致性收敛，
        晚几百毫秒建好不影响本条判定结果，所以异步化。
        """
        if DRY_RUN:
            return

        def _do():
            try:
                ES.build_entity(self.ch, domain, uid, name, kind, profile=profile,
                                site_name=site_name, source=source)
            except Exception:  # noqa: BLE001
                log_err_throttled("entity", "建同源主体失败: %s" % traceback.format_exc()[-200:])

        if self._entity_pool is None:
            _do()
            return
        # 在途到上限 → 同步做。这是唯一的反压手段：池的队列无界，
        # submit() 不会因为满而抛异常，光靠下面的 except 兜不住堆积。
        with self._entity_lock:
            if self._entity_inflight >= ENTITY_MAX_PENDING:
                self._entity_sync += 1
                over = True
            else:
                over = False
                self._entity_inflight += 1
                if self._entity_inflight > self._entity_peak:
                    self._entity_peak = self._entity_inflight
        if over:
            _do()
            return

        def _tracked():
            try:
                _do()
            finally:
                with self._entity_lock:
                    self._entity_inflight -= 1

        try:
            self._entity_pool.submit(_tracked)
        except Exception:  # noqa: BLE001
            with self._entity_lock:      # 提交失败要把计数还回去
                self._entity_inflight -= 1
            _do()          # 池已关闭就退回同步，别丢主体

    def _llm_kind(self, ud):
        """调 qwen 判定（走批量聚合）。返回 (kind, source, reason)。

        失败时返回 source="model_error"，调用方【必须】丢弃该条而不是落库：
        兜底成"自媒体"写进 CH 会被 TTL 固化并被 ch_reuse 复用扩散。
        """
        dd = {"账号名": ud["name"], "账号认证原因": ud["verified_reason"],
              "账号自我介绍": ud["description"]}
        kind, reason, ok = _batcher.judge(dd)
        if not ok or not kind:
            return "", "model_error", ""
        return kind, "model", reason or "模型未给出理由"

    # ── 媒体矩阵命中：机构类注入 CH（一致性锚点）+ 建同源主体 ──
    def _finalize_matrix(self, ud):
        if DRY_RUN or not ud.get("id"):
            return
        self._ch_upsert(ud)
        self._build_entity(ud["domain"], ud["id"], ud["name"], ud["kind"],
                           site_name=ud["sitename"], source="media_matrix")

    # ── 人工名单命中：写 CH，机构类同时建/更新主体（source=manual 权威分最高）──
    def _finalize_manual(self, ud):
        if DRY_RUN or not ud.get("id"):
            return
        self._ch_upsert(ud)
        if ud["kind"] != "自媒体":
            self._build_entity(ud["domain"], ud["id"], ud["name"], ud["kind"],
                               site_name=ud["sitename"], source="manual")

    def _write_result_redis(self, ud):
        """结果写下游 redis（仅非自媒体，保持 v1 行为与 value 格式）。

        value = {"1": [性质], "2": 判定理由全文}
        v1 的 "2" 存的是判定理由（规则依据或 LLM 理由），不是来源代号，这里保持一致。

        SA_WRITE_RESULT_REDIS=0 时整体跳过：结果 redis 改由每日同步作业
        以 CH 为基准维护（见该变量的说明）。
        """
        if DRY_RUN or not WRITE_RESULT_REDIS:
            return
        op_key = "^".join([ud["sitename"], ud["id"]])
        op_value = json.dumps({"1": [ud["kind"]], "2": ud.get("reason", "")},
                              ensure_ascii=False)
        try:
            self.redis_conn_ugc.set(op_key, op_value)
            if "抖音" in ud["sitename"]:
                self.huoshan_redis_conn_ugc.set(op_key, op_value)
        except Exception:  # noqa: BLE001
            log_err_throttled("result_redis", "下游 redis 写入失败: %s" % traceback.format_exc()[-300:])

    def run(self, data):
        site_name = str(data.get("siteName", ""))
        user = data.get("user") or {}
        uid = str(user.get("uid", ""))
        username = str(user.get("name", ""))
        verified = user.get("verified", "")
        domain = normalize_domain(data.get("url", ""), site_name)
        ud = {
            "sitename": site_name, "id": uid, "name": username,
            "verified": verified,
            # 不用 "无" 兜底：占位值会污染 LLM 输入和 CH 存量
            "verified_reason": pick(user.get("verified_reason")),
            "description": pick(user.get("description")),
            # wm_site_domain 是 v1 的下发字段名，下游按它读；domain 是内部用
            "wm_site_domain": domain,
            "domain": domain,
            "reason": "",
        }
        try:
            # 1) rank / 境外 → 丢弃
            idx = data.get("index_suffix", "")
            if idx.startswith("rank") or idx in ["facebook", "twitter", "oversea",
                                                 "youtube"]:
                return None

            # 1b) 人工名单（最高优先级，用来纠正媒体矩阵等上游标签的错误）
            ov = MANUAL_OVERRIDES.get((domain, uid)) if uid else None
            if ov:
                ud.update(kind=ov[0], source="manual",
                          reason="人工名单：%s" % (ov[1] or ov[0]))
                self._finalize_manual(ud)
                return ud

            # 2) 媒体矩阵（权威，命中即定；机构类结果注入 CH）
            mm = data.get("media_matrix", {}) or {}
            level = mm.get("mediaLevel", "无")
            if level in ["中央", "省级", "地方"]:
                ud.update(kind=level, source="media_matrix",
                          reason="媒体矩阵 mediaLevel=%s" % level)
                self._finalize_matrix(ud)
                return ud
            nature = mm.get("mediaNature", "无")
            if nature in ["党媒", "央媒"]:
                ud.update(kind="政务媒体", source="media_matrix",
                          reason="媒体矩阵 mediaNature=%s → 政务媒体" % nature)
                self._finalize_matrix(ud)
                return ud
            if nature in ["商媒"]:
                ud.update(kind="商业媒体", source="media_matrix",
                          reason="媒体矩阵 mediaNature=商媒 → 商业媒体")
                self._finalize_matrix(ud)
                return ud
            industry = mm.get("mediaIndustry", "无")
            if industry in INDUSTRY_MAP:  # 映射待定，当前不生效
                ud.update(kind=INDUSTRY_MAP[industry], source="media_matrix",
                          reason="媒体矩阵 mediaIndustry=%s" % industry)
                self._finalize_matrix(ud)
                return ud

            # 3) UGC 判定：user.uid 有效 且 非百度贴吧
            if uid and not site_name.startswith("百度贴吧"):
                # 3a) 高频过滤（db14/db15）
                if self._hf_hit(uid, domain):
                    ud.update(kind="自媒体", source="high_freq",
                              reason="命中高频库(db14/db15)，判定为自媒体")
                    return ud

                # 3b) 消息未认证 → 自媒体（快速门槛）
                # 用 is_unverified 而不是 `verified == 0`：字符串 "0"/"-1"
                # 比 int 0 不相等，会让未认证账号漏进下面的机构类判定。
                if is_unverified(verified):
                    ud.update(kind="自媒体", source="unverified",
                              reason="实时消息 user.verified 为空/0，未认证，判定为自媒体")
                    return ud

                # 3b-2) 短剧/剧场号 → 自媒体
                #   放在【查CH之前】：v1 存量把短剧号判成企业官方，若放在 ch_reuse
                #   之后，未过期的旧结论会绕过这条规则。只用消息字段即可判，
                #   顺带省掉一次 CH 查询 + 一次画像查询。
                is_drama, drama_why = is_drama_account(
                    username, ud["description"], ud["verified_reason"])
                if is_drama:
                    ud.update(kind="自媒体", source="drama",
                              reason="%s，属短剧/剧场类内容号，判定为自媒体" % drama_why)
                    return ud

                # 3c) 查 CH：命中未过期 → 复用结论，不查画像
                #     资料字段仍以【实时消息】为准，顺便刷新 CH 里的旧值
                cached = self._ch_query(domain, uid)
                if cached and self.ch.is_fresh(cached):
                    ud["name"] = pick(username, cached.get("name"))
                    ud["description"] = pick(user.get("description"),
                                             cached.get("description"))
                    ud["verified"] = str(verified)
                    ud["verified_reason"] = pick(user.get("verified_reason"),
                                                 cached.get("verified_reason"))
                    ud.update(
                        kind=cached["kind"], source="ch_reuse",
                        reason="复用认证账号库已有结论「%s」(原判定来源 %s)"
                               % (cached["kind"], cached.get("source", "")))
                    # ⚠️ 命中【不回写 CH】，三个原因：
                    # 1) 回写会续期 update_time，而活跃账号天天有消息，
                    #    等于永不过期、永不重算 —— 账号认证会变，30 天必须重算一次
                    # 2) 回写的 source 已是 ch_reuse，会覆盖原始 model/rule/media_matrix，
                    #    之后 ch_reuse 复用 ch_reuse，把一次结论永久固化
                    # 3) 命中是热路径(占比最高)，每命中一次 INSERT 一次
                    #    ≈480 次/秒打在 CH 上，parts 会堆爆
                    # 下发给下游的仍是实时消息里的最新资料，不受影响。
                    if ud["kind"] != "自媒体":
                        self._write_result_redis(ud)
                    return ud

                # 3d) CH 没有/过期 → 认证以【实时消息】为准
                #     画像 verified 大面积为 0/空且滞后（昵称也可能是改名前的旧值），
                #     不能当认证依据；实时消息已在 3b 过了认证门槛。
                #
                # ⚠️ 画像查询【按需】进行，不再每条都查：
                #   线上 92% 的结论是自媒体，而画像的主要价值是 similar_accounts，
                #   那只有机构类建主体时才用得上。每条都查等于 92% 白查一次 HTTP，
                #   还白占着消费线程（线程已被 LLM 等待占满，省一次 IO 就多一个并发位）。
                #   只有两种情况才查：
                #     a) 消息侧没有 verified_reason —— 判定依据不足，需要画像补
                #        （实测消息侧 98% 都有，所以这条很少触发）
                #     b) 判成机构类 —— 要拿 similar_accounts 建同源主体
                msg_reason = pick(user.get("verified_reason"))
                prof = {}
                if not msg_reason:
                    prof = self._profile(domain, uid, site_name)

                ud["name"] = pick(username, prof.get("name"))
                ud["verified"] = str(verified)
                ud["verified_reason"] = pick(msg_reason,
                                             prof.get("verified_reason"))
                ud["description"] = pick(user.get("description"),
                                         prof.get("description"))
                ud["update_time"] = None  # 计算时间=本次判定时间

                # 补到资料后再兜一次短剧特征（消息侧没有、画像简介里才有的情况）
                if prof:
                    is_drama2, drama_why2 = is_drama_account(
                        ud["name"], ud["description"], ud["verified_reason"])
                    if is_drama2:
                        ud.update(kind="自媒体", source="drama",
                                  reason="%s（画像补资料后），属短剧/剧场类内容号，"
                                         "判定为自媒体" % drama_why2)
                        self._ch_upsert(ud)
                        return ud

                # 企业官方关键词规则：认证状态以实时消息为准，认证【原因文本】两侧都提信号
                #   消息侧是具体执照名（"XX科技有限公司"），画像侧常是平台话术，
                #   任一命中企业词即企业官方，避免丢掉其中一侧的信号。
                is_qy, why = is_enterprise_official(ud["name"],
                                                    ud["verified_reason"])
                if not is_qy and prof:
                    prof_reason = pick(prof.get("verified_reason"))
                    if prof_reason and prof_reason != ud["verified_reason"]:
                        is_qy, why = is_enterprise_official(ud["name"], prof_reason)
                if is_qy:
                    kind, source = "企业官方", "rule"
                    reason = "%s，判定为企业官方账号" % why
                else:
                    kind, source, reason = self._llm_kind(ud)
                    if source == "model_error":
                        # ⚠️ LLM 失败绝不能写 CH：兜底的"自媒体"是假结论，
                        # 一旦落库就被 30 天 TTL 固化，还会被 ch_reuse 复用扩散。
                        # 直接放弃这条（不写库、不下发），等下次消息重新判定。
                        # 返回丢弃标记而不是裸 None：调用方要靠它把这次丢弃
                        # 记到 model_error 上，否则统计里 LLM 失败被丢的条数
                        # 会和 rank/境外的正常过滤混成一个数字，永远查不出来。
                        return {DROP_MARK: "model_error"}

                # 机构类 → 用 similar_accounts 建/更新同源主体。
                # 必须在一致性协调【之前】：协调靠 find_entity_by_uid 定位主体，
                # 主体没建出来的话收敛这一步会被直接跳过。
                # 这里才按需查画像（自媒体结论根本不走到这，省掉 92% 的查询）。
                if kind in ES.ORG_KINDS:
                    if not prof:
                        prof = self._profile(domain, uid, site_name)
                        # 拿到画像后把资料补全，再写 CH 时字段更完整
                        ud["name"] = pick(ud["name"], prof.get("name"))
                        ud["description"] = pick(ud["description"],
                                                 prof.get("description"))
                    self._build_entity(domain, uid, ud["name"], kind, profile=prof,
                                       site_name=site_name, source=source)
                # 一致性协调：同主体跨平台结论收敛（只认新口径、取最高权威）
                new_kind, new_source = consistency_reconcile(self.ch, ud, kind, source)
                if new_source == "entity_reconcile" and new_kind != kind:
                    reason = ("本账号判为「%s」，但同源主体已有更高权威结论「%s」，"
                              "按主体收敛" % (kind, new_kind))
                kind, source = new_kind, new_source
                ud.update(kind=kind, source=source, reason=reason)
                self._ch_upsert(ud)
                if kind != "自媒体":
                    self._write_result_redis(ud)
                return ud

            # 4) 非 UGC
            if site_name.startswith("百度贴吧"):
                ud.update(kind="其他", source="tieba", reason="百度贴吧 → 其他")
                return ud
            return None  # 网站类非 UGC：丢弃（沿用 v1，网站分类逻辑已停用）
        except Exception:  # noqa: BLE001
            # 用限流版而非 mylog_hd.exception：这是每条消息都可能进的兜底分支，
            # exception 会带整段堆栈（比 error 长一个量级），一旦有系统性异常
            # （某站点字段结构变了）就是每秒几百条完整堆栈直接写爆磁盘。
            log_err_throttled("judge", "判定异常(丢弃该条): %s"
                              % traceback.format_exc()[-300:])
            return None

    def close(self):
        # 等建主体的异步任务收尾，否则退出时会丢掉已提交的主体。
        # ⚠️ 但必须有上限：shutdown(wait=True) 会把已排队任务全部跑完，
        # 画像库慢时队列可能有几百项、每项几十秒，等下去必然超过 docker stop
        # 的 10s 宽限期被 SIGKILL —— 那样连 producer/统计都来不及收尾。
        # 所以放到独立线程里等固定秒数，超时就放弃剩余主体（daemon 线程随进程退出）。
        # 主体只服务于一致性收敛，丢掉一部分下次判定会重建，可以接受。
        if self._entity_pool is not None:
            try:
                th = threading.Thread(
                    target=lambda: self._entity_pool.shutdown(wait=True))
                th.daemon = True
                th.start()
                th.join(ENTITY_SHUTDOWN_WAIT)
                if th.is_alive():
                    st = self.entity_stats()
                    mylog_hd.error("建主体未在 %.0fs 内收尾，放弃剩余 %d 项"
                                   % (ENTITY_SHUTDOWN_WAIT, st["inflight"]))
            except Exception:  # noqa: BLE001
                pass
        for c in ("redis_conn_ugc", "huoshan_redis_conn_ugc"):
            try:
                getattr(self, c).close()
            except Exception:  # noqa: BLE001
                pass
        for obj in (getattr(self, "hf", None), getattr(self, "ch", None)):
            try:
                if obj is not None and hasattr(obj, "close"):
                    obj.close()
            except Exception:  # noqa: BLE001
                pass


class MessageProcessor:
    def __init__(self, producer):
        self.producer = producer
        self.user_data = UserData()
        self.n_in = 0
        self.n_out = 0
        self.n_drop = 0                      # 判定后丢弃（rank/境外、非UGC网站）
        self.by_source = Counter()           # 判定来源分布
        self.by_kind = Counter()             # 性质分布
        self._t0 = time.time()
        self._last_n = 0             # 上次打印时的计数，用来算"当前速率"
        self._last_t = self._t0
        self._lock = threading.Lock()
        # 每日统计（判定量 + LLM token 用量），周期性落盘到 stats/
        self.stats = DailyStats(STATS_DIR, os.environ.get("HOSTNAME"),
                                STATS_FLUSH_SEC)

    def flush_stats(self, force=False):
        """把统计增量落盘。llm token 用量从 llm_qwen 取走（取走即清零）。"""
        if not force and not self.stats.due():
            return
        usage = llm_qwen.take_usage()
        # llm_qwen 只统计到 HTTP 请求级失败；批量器侧的"请求成功但解析不到该条"
        # （截断/漏答）和"队列满被拒"才是丢结论的主要形态，必须并进来，
        # 否则明明在丢结论、统计上却显示 LLM 零失败。
        usage["fail"] = usage.get("fail", 0) + _batcher.take_fail()
        self.stats.flush(usage, force=force)

    def _tick(self, result_json, drop_source=""):
        """累计统计，并按 STAT_EVERY 周期打印一次。多线程消费，用锁保护。

        drop_source: 被丢弃条目的来源标记（如 model_error）。判定失败时
        run() 返回 None，source 信息在返回值里就丢了，不单独传进来的话
        daily_stats 的 model_error 列永远是 0，LLM 失败被丢弃的条数会和
        rank/境外、非 UGC 网站的正常丢弃混成同一个"丢弃量"，
        事后无法回答"今天有多少账号因为模型失败被丢了"。
        """
        # 每日统计（独立于控制台统计，会落盘）
        # 注意：下发量不在这里加 —— 见 DailyStats.bump 的说明，
        # 必须等 send_data 真正提交成功才算。
        self.stats.add(source=(result_json or {}).get("source") or drop_source,
                       dropped=result_json is None)
        with self._lock:
            self.n_in += 1
            if result_json is None:
                self.n_drop += 1
                # 控制台也把丢弃原因分开，否则 model_error 和 rank/境外
                # 混在一个"丢弃"数字里，看不出是模型在失败还是正常过滤
                self.by_source["drop:%s" % (drop_source or "filter")] += 1
            else:
                self.by_source[result_json.get("source") or "-"] += 1
                self.by_kind[result_json.get("kind") or "-"] += 1
            n = self.n_in
            if not STAT_EVERY or n % STAT_EVERY:
                return
            now = time.time()
            el = max(now - self._t0, 1e-6)
            # 当前速率必须单独算：只打累计均值 n/el 会被历史严重稀释，
            # 线上就出现过"均值 32.3 / 实际 43"被误读成速度下降的情况，
            # 中途停摆几小时也几乎看不出来。均值仍保留，用来看长期水位。
            cur = (n - self._last_n) / max(now - self._last_t, 1e-6)
            self._last_n, self._last_t = n, now
            src = " ".join("%s:%d" % (k, v) for k, v in self.by_source.most_common(8))
            knd = " ".join("%s:%d" % (k, v) for k, v in self.by_kind.most_common(9))
        print("[stat] 处理 %d 下发 %d 丢弃 %d | %.1f 条/秒(当前) %.1f(均值) "
              "| 来源 %s | 性质 %s"
              % (n, self.n_out, self.n_drop, cur, n / el, src, knd), flush=True)

    def send_data(self, result_json):
        if result_json is None:
            return
        kind = str(result_json.get("kind", "")).strip()
        # 自媒体不下发（v1 行为）
        if kind == "自媒体":
            return
        # 校验是合法标签再下发。注意这里【不能】用 normalize_kind：
        # 它的语义是「空或其他 → 自媒体」，会把百度贴吧的"其他"也转成自媒体从而不下发，
        # 而 v1 是把"其他"原样下发的。
        if kind not in DISPATCH_KINDS:
            log_err_throttled("bad_kind", "非法 kind「%s」不下发 (sitename=%s id=%s)"
                           % (kind, result_json.get("sitename"),
                              result_json.get("id")))
            return
        result_json["kind"] = kind
        # 按白名单构造消息体：v1 字段 + v2 附加，内部字段不下发
        payload = {k: result_json.get(k, "") for k in DISPATCH_FIELDS}
        key = "^".join([payload["sitename"],
                        payload["id"] or payload["wm_site_domain"]])
        if DRY_RUN:
            # 用 print 而不是 mylog_hd.info：控制台级别可能被设成 ERROR，
            # 那样 dry-run 的输出在 docker logs 里根本看不到
            print("[dry-run] 本应下发 %s -> %s (%s)"
                  % (key, payload["kind"], payload.get("source")), flush=True)
            with self._lock:
                self.n_out += 1
            self.stats.bump("下发量")
            return
        err = self.producer.send2mq(json.dumps(payload, ensure_ascii=False),
                                    key, DST_TOPIC)
        if err:
            log_err_throttled("mq_send", "下发 MQ 失败 key=%s: %s" % (key, err))
        else:
            with self._lock:
                self.n_out += 1
            # 落盘统计的「下发量」在这里加，与控制台 n_out 同一时机，
            # 保证两个口径一致（原来在 _tick 里预判，恒偏高）
            self.stats.bump("下发量")

    def process_message(self, data):
        try:
            result = self.user_data.run(data)
            # 丢弃标记：run() 用它带出"因为什么被丢的"，取出后按 None 处理，
            # 下面的下发/明细日志逻辑完全不变
            drop_source = ""
            if isinstance(result, dict) and result.get(DROP_MARK):
                drop_source = result[DROP_MARK]
                result = None
            self._tick(result, drop_source)
            if LOG_DETAIL and result is not None:
                print("[judge] %-10s %-22s -> %-6s [%-12s] %s"
                      % (str(result.get("sitename"))[:10],
                         str(result.get("name"))[:22],
                         result.get("kind"), result.get("source"),
                         str(result.get("reason"))[:70]), flush=True)
            self.send_data(result)
        except Exception:  # noqa: BLE001
            # 同上：每条消息都可能进这里，不能用带完整堆栈的 exception
            log_err_throttled("process", "消息处理异常: %s"
                              % traceback.format_exc()[-300:])

    def close(self):
        self.user_data.close()


# 字节级快速预筛用的标记。判定链只处理【原发(wtype=1) + 已认证】的消息，
# 而实测 95% 的流量不满足，先用子串挡掉，省下 json.loads 的开销。
# 只做"肯定不要"的判断，可能要的一律放过去走完整解析，不会漏。
_B_WTYPE1 = b'"wtype":1'
_B_WTYPE1_SP = b'"wtype": 1'
_B_VERIFIED = b'"verified"'


def _maybe_interesting(raw):
    """True = 可能需要判定（放过去解析）；False = 肯定不需要（直接跳过）。

    两个必要条件（不满足就一定会被预过滤掉）：
      1. wtype 必须是 1（原发）
      2. 必须有 verified 字段（认证判断要用）
    注意 wtype 可能是 "wtype":1 或 "wtype": 1 两种写法，都要认。
    """
    if not raw:
        return False
    if _B_WTYPE1 not in raw and _B_WTYPE1_SP not in raw:
        return False
    return _B_VERIFIED in raw


class MyListener(MessageListenerConcurrently):
    """MQ 消费回调。

    ⚠️ 这里要统计【原始接收量】和【预过滤跳过量】：预过滤 continue 掉的消息
    既不进 process_message、也不累加 n_in，如果不单独计数，日志上会完全静默——
    看起来像"卡住"，其实是在飞速接收并跳过（正常流量里认证原发只占 8~10%）。
    """

    def __init__(self, processor):
        self.processor = processor
        self.n_recv = 0       # 从 MQ 收到的原始消息数
        self.n_skip = 0       # 被预过滤跳过的数量
        self.n_bad = 0        # 解析失败
        self._lock = threading.Lock()

    def consume_message(self, msgs):
        recv = skip = bad = 0
        for msg in msgs:
            recv += 1
            try:
                raw = msg.body
                # 字节级快速预筛：实测 95% 的消息会被预过滤丢掉，
                # 但原来每条都要完整 json.loads 一遍（消息体几 KB），
                # 纯属浪费。这里先用子串判断挡掉绝大多数，再解析。
                if not _maybe_interesting(raw):
                    skip += 1
                    continue
                data = json.loads(raw.decode("utf-8", "ignore"))
                user = data.get("user") or {}
                uid = user.get("uid", "")
                verified = user.get("verified", "")
                wtype = data.get("wtype", 0)
                url = data.get("url", "") or ""
                # 预过滤（与 v1 一致）：未认证/非原发的有uid账号跳过
                # is_unverified 同时认 int 0 和字符串 "0"/"-1"（见 classify_core）
                if (is_unverified(verified) or wtype != 1) and uid:
                    skip += 1
                    continue
                if url.endswith(("#ocr", "#asr", "#att")):
                    skip += 1
                    continue
                self.processor.process_message(data)
            except Exception as e:  # noqa: BLE001
                bad += 1
                log_err_throttled("consume", "Message processing error: %s" % str(e))
        with self._lock:
            self.n_recv += recv
            self.n_skip += skip
            self.n_bad += bad
        return 0


_stop = threading.Event()


def main():
    producer = ProducerMQ(NAMESRV, PRODUCER_GROUP)
    processor = MessageProcessor(producer)
    consumer = DefaultMQPushConsumer(CONSUMER_GROUP)
    consumer.namesrv_addr = NAMESRV
    consumer.consume_thread_num = CONSUME_THREADS
    consumer.consume_message_batch_max_size = CONSUME_BATCH
    consumer.max_cache_msg_size_pre_queue = MAX_CACHE_PER_QUEUE
    # listener 必须持强引用：直接传临时对象的话，若客户端只存裸指针，
    # Python GC 回收后回调永远不会被触发（表现就是启动成功但收不到消息）
    listener = MyListener(processor)
    consumer.registerMessageListener(listener)
    consumer.subscribe(SRC_TOPIC, SRC_TAG)
    consumer.start()

    def cleanup(*_a):
        """优雅关闭：先停消费，再收尾 producer 与各连接。"""
        if _stop.is_set():
            return
        _stop.set()
        mylog_hd.info("收到退出信号，开始优雅关闭…")
        # 顺序很重要：
        # 1) 先停消费，不再有新消息进来
        # 2) 再停 LLM 批量器：它会把队列里没处理的请求唤醒为失败。不做这步的话，
        #    还阻塞在 judge() 上的消费线程要干等满 BATCH_TIMEOUT(120s)，
        #    优雅关闭直接被拖过 docker stop 的宽限期而被强杀。
        # 3) 然后 processor.close()（等建主体收尾，内部有超时上限）
        # 4) 统计放【最后】落盘：原来是第一步 flush，之后停消费期间处理掉的那批
        #    进了 _pending 却再也不会落盘，等于每次关闭都固定少记一段。
        for step, fn in (("consumer", consumer.shutdown),
                         ("llm_batcher", _batcher.stop),
                         ("processor", processor.close)):
            try:
                fn()
            except Exception:  # noqa: BLE001
                mylog_hd.error("关闭 %s 失败: %s" % (step, traceback.format_exc()[-200:]))
        try:
            processor.flush_stats(force=True)   # 落盘尾巴数据，避免丢当天增量
        except Exception:  # noqa: BLE001
            pass
        try:
            producer.close()
        except Exception:  # noqa: BLE001
            mylog_hd.error("关闭 producer 失败: %s" % traceback.format_exc()[-200:])
        print("已处理 %d 条，下发 %d 条，退出完成" % (processor.n_in, processor.n_out))

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("=" * 78, flush=True)
    print("发布者性质 v2 启动%s" % ("  [DRY-RUN 不下发/不写库]" if DRY_RUN else ""),
          flush=True)
    print("  消费     %s (tag=%s)" % (SRC_TOPIC, SRC_TAG), flush=True)
    print("  消费组   %s" % CONSUMER_GROUP, flush=True)
    print("  拉取     线程 %d  单批 %d 条  每队列缓存上限 %d MB"
          % (CONSUME_THREADS, CONSUME_BATCH, MAX_CACHE_PER_QUEUE), flush=True)
    print("  下发     %s" % DST_TOPIC, flush=True)
    print("  CH       %s@%s:%s/%s  TTL %d 天"
          % (os.environ.get("SA_CH_USER", "clickhouse_reader"),
             os.environ.get("SA_CH_HOST", "192.168.191.5"),
             os.environ.get("SA_CH_PORT", "9000"),
             os.environ.get("SA_CH_TABLE", "source_attr_accounts"),
             int(os.environ.get("SA_RESULT_TTL", 30 * 24 * 3600)) // 86400),
          flush=True)
    print("  日志     控制台=%s  统计每 %d 条  逐条明细=%s"
          % (os.environ.get("SA_LOG_LEVEL", "INFO"), STAT_EVERY,
             "开" if LOG_DETAIL else "关"), flush=True)
    print("  LLM      %s  批量 %d 条/请求(等 %.0fms) × %d 并发  限流 %s"
          % (llm_qwen.LLM_MODEL, _batcher.batch_size, _batcher.max_wait * 1000,
             _batcher.workers,
             ("%g 请求/秒" % llm_qwen.LLM_MAX_QPS) if llm_qwen.LLM_MAX_QPS > 0
             else "不限"), flush=True)
    print("  结果redis %s"
          % ("实时写入（v1 行为）" if WRITE_RESULT_REDIS
             else "【不实时写】改由每日同步 sync_result_redis.py 以 CH 为基准维护"),
          flush=True)
    print("  统计     %s/  每 %d 秒落盘" % (STATS_DIR, STATS_FLUSH_SEC), flush=True)
    print("=" * 78, flush=True)
    # 心跳：没消息时也要有输出，否则"进程卡住"和"上游没数据/没分到队列"
    # 在日志上完全看不出区别。连续为 0 时打印排查方向。
    try:
        beat = 0
        last_in = 0
        t_start = time.time()
        while not _stop.is_set():
            _stop.wait(HEARTBEAT_SEC)
            if _stop.is_set():
                break
            beat += 1
            n = processor.n_in
            delta = n - last_in
            last_in = n
            el = max(time.time() - t_start, 1e-6)
            print("[beat#%d] MQ收到 %d (跳过 %d 坏 %d) | 进判定 %d (本周期 +%d) "
                  "| 下发 %d 丢弃 %d | 收 %.0f 条/秒"
                  % (beat, listener.n_recv, listener.n_skip, listener.n_bad,
                     n, delta, processor.n_out, processor.n_drop,
                     listener.n_recv / el), flush=True)
            bs = _batcher.stats()
            if bs["batches"] or bs["pending"]:
                # 拒绝数是雪崩的早期信号：队列有上限，持续 >0 说明 LLM 供不上
                # （最常见的诱因是高频库抖动，79% 的流量突然涌进完整链路）
                print("[llm] 批量 %d 次 / %d 账号，均 %.1f 条/请求 | "
                      "并发 %d | 排队 %d/%d | 丢弃 %d 队列满拒绝 %d"
                      % (bs["batches"], bs["items"], bs["avg"], bs["workers"],
                         bs["pending"], _batcher.max_pending,
                         bs["fail"], bs["reject"]), flush=True)
            # 建主体堆积：不打出来就完全看不到它在涨（池队列无界，只能靠自己计数）。
            # inflight 持续贴着 limit、sync 在涨 = 画像库慢，已经在拿消费线程扛了。
            es = processor.user_data.entity_stats()
            if es["inflight"] or es["sync"]:
                print("[entity] 建主体在途 %d/%d (峰值 %d) 转同步 %d 次"
                      % (es["inflight"], es["limit"], es["peak"], es["sync"]),
                      flush=True)
            # 到周期就把每日统计落盘（判定量 + token 用量）
            processor.flush_stats()
            if listener.n_recv == 0 and beat >= 2:
                # 真的一条 MQ 消息都没收到 —— 是队列/连接问题，不是预过滤
                print("[beat] MQ 一条未收到，排查方向：\n"
                      "   1) 同消费组是否有其他实例占满 topic 队列 -> docker ps\n"
                      "   2) 控制台看消费组 %s 是否给本实例分配了队列\n"
                      "   3) 外部依赖自检 -> python3.6 smoke_realtime.py"
                      % CONSUMER_GROUP, flush=True)
            elif n == 0 and listener.n_recv > 0:
                # 收到了但全被预过滤挡掉：正常流量里认证原发只占 8~10%,
                # 短时间内全跳过是可能的；持续如此才需要看预过滤条件
                print("[beat] 收到 %d 条但全被预过滤跳过（只处理 认证+原发+有uid）"
                      % listener.n_recv, flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())

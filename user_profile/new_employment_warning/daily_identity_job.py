# -*- coding: utf-8 -*-
"""预警账号身份识别每日批量任务（画像回写主入口）。

每天运行一次，把人工预警索引里指定日期的账号算出身份并回写 ``media_*`` 画像索引。
不订阅 MQ、不常驻进程，跑完即退出。

完整流程::

    artificial_warning_push_*（按 publishTime 取指定日期）
        │  ES 侧先用身份词 match_phrase 收敛候选，避免全量扫描
        ▼
    [账号去重]  key = 归一 site_name|author_persona.id，每账号最多留 N 条帖
        ▼
    [平台映射]  siteName → 标准 site_name + media_* 目标索引，映射不到的跳过
        ▼
    [粗预筛]    actrie 身份别名匹配 + 官号排除（纯本地，零成本）
        ▼
    [资料回补]  批量查 media_* 已有文档，补回预警索引缺失的
                description / verified_reason（预警 author_persona 没有这两个字段）
        ▼
    [严格预筛]  general_judge 的本人身份直接信号校验
        ▼
    [模型判断]  一次调用覆盖 20 个标准身份（线上阿里云 qwen3.5-flash）
                + 证据接地校验 + 三新身份追加职业硬门槛
        ▼
    [回写]      三新 → community，其他 → identity
                已有账号只更新身份字段；新账号按 media_* mapping 完整插入
        ▼
    output/daily_identity_*.jsonl + .xlsx（审计明细与运行汇总）

运行示例::

    # 跑昨天（默认）
    python3 -m new_employment_warning.daily_identity_job

    # 指定日期，先不写库只看统计
    python3 -m new_employment_warning.daily_identity_job --date 2026-08-02 --dry-run

    # 小样本验证
    python3 -m new_employment_warning.daily_identity_job --date 2026-08-02 --max-accounts 200
"""
import argparse
import datetime
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from actrie import Matcher

from new_employment_warning.config import JOB_CONFIG, OUTPUT_DIR, SOURCE_INDEX
from new_employment_warning.general_judge import (
    ALLOWED_IDENTITIES,
    IDENTITY_ALIASES,
    IDENTITY_GROUPS,
    candidate_has_direct_signal,
    is_organization_account,
    judge_general_identity,
)
from new_employment_warning.identity_gates import passes_identity_gate
from new_employment_warning.judge import passes_new_employment_hard_gate
from new_employment_warning.llm_client import MODEL_NAME
from new_employment_warning.media_index_mapper import resolve_media_target
from new_employment_warning.media_writer import (
    NEW_EMPLOYMENT_COMMUNITIES,
    find_existing_docs,
    get_client,
    write_back,
)


SOURCE_FIELDS = ["url", "content", "title", "siteName", "publishTime", "author_persona"]

# 标准身份 -> 业务组，用于统计。
GROUP_BY_IDENTITY = {}
for _group, _labels in IDENTITY_GROUPS.items():
    for _label in _labels:
        GROUP_BY_IDENTITY[_label] = _group

# 全部身份别名合集，用于 ES 侧收敛和本地粗预筛。
ALL_ALIASES = []
_seen_alias = set()
for _identity in sorted(ALLOWED_IDENTITIES):
    for _alias in IDENTITY_ALIASES[_identity]:
        if _alias not in _seen_alias:
            _seen_alias.add(_alias)
            ALL_ALIASES.append(_alias)

# 粗预筛用的 actrie 匹配器（纯本地，命中才进入后续严格校验和模型）。
_alias_matcher = Matcher()
_alias_matcher.load_from_collection(ALL_ALIASES)

# OCR/ASR 派生文本噪声大、且多为电视节目与新闻转写，不用于身份判断。
_DERIVED_URL_SUFFIX = ("#ocr", "#asr", "#att")

_EXCEL_ILLEGAL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def yesterday():
    # type: () -> str
    """返回昨天的日期字符串（yyyy-MM-dd）。"""
    return (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


# 只清理增量路自己生成的明细文件，靠前缀识别，避免误删其它东西。
_CLEANUP_PREFIX = "daily_identity_"
_CLEANUP_SUFFIXES = (".xlsx", ".jsonl")


def cleanup_old_outputs(keep_days=None, output_dir=None, now=None):
    # type: (int, str, float) -> dict
    """删除超过保留期的增量路产物。

    每天一份 xlsx + jsonl，长期跑会堆几百个文件。这里在每次运行结束时清理。

    只删除形如 ``daily_identity_*.xlsx`` / ``daily_identity_*.jsonl`` 的文件，
    **不递归子目录**，所以回溯产物（``backfill/``）和断点文件绝不会被误删。

    Args:
        keep_days: 保留天数，<=0 表示不清理。默认取 ``JOB_CONFIG.output_keep_days``。
        output_dir: 产物目录，默认 ``OUTPUT_DIR``。
        now: 当前时间戳，仅用于测试注入。

    Returns:
        dict: ``{"removed": [文件名...], "kept": 保留数量, "failed": [(文件名, 原因)]}``。
    """
    if keep_days is None:
        keep_days = JOB_CONFIG.get("output_keep_days", 1)
    output_dir = output_dir or OUTPUT_DIR
    result = {"removed": [], "kept": 0, "failed": []}
    if not keep_days or keep_days <= 0 or not os.path.isdir(output_dir):
        return result

    now = time.time() if now is None else now
    deadline = now - keep_days * 86400
    for name in sorted(os.listdir(output_dir)):
        path = os.path.join(output_dir, name)
        if not os.path.isfile(path):
            continue
        if not name.startswith(_CLEANUP_PREFIX):
            continue
        if not name.endswith(_CLEANUP_SUFFIXES):
            continue
        try:
            if os.path.getmtime(path) < deadline:
                os.remove(path)
                result["removed"].append(name)
            else:
                result["kept"] += 1
        except OSError as exc:
            result["failed"].append((name, str(exc)))
    return result


def build_candidate_query(start_time, end_time):
    # type: (str, str) -> dict
    """构造候选帖查询：时间窗 + 有账号 id + 命中任一身份别名。

    身份别名过滤放在 ES 侧，可把一天 20 余万帖收敛到几万条，
    避免把当天全量帖文拉到本地。

    Args:
        start_time: 起始时间，``yyyy-MM-dd HH:mm:ss``。
        end_time: 结束时间，``yyyy-MM-dd HH:mm:ss``。

    Returns:
        dict: ES query 主体。
    """
    # 用 multi_match/phrase 跨三个字段表达一个别名，子句数从 别名×字段 降到 别名，
    # 显著减轻 ES 查询解析与打分开销（408 → 136）。
    should = [
        {"multi_match": {
            "query": alias,
            "type": "phrase",
            "fields": ["author_persona.name", "title", "content"],
        }}
        for alias in ALL_ALIASES
    ]
    return {
        "bool": {
            "filter": [
                {"range": {"publishTime": {
                    "gte": start_time, "lte": end_time,
                    "format": "yyyy-MM-dd HH:mm:ss", "time_zone": "+08:00",
                }}},
                {"exists": {"field": "author_persona.id"}},
                {"exists": {"field": "siteName.keyword"}},
                {"bool": {"should": should, "minimum_should_match": 1}},
            ]
        }
    }


_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def iter_time_windows(start_time, end_time, hours):
    # type: (str, str, int) -> list
    """把时间区间切成若干个左右闭合、互不重叠的小窗口。

    一天的候选集有 7 万+ 帖，在单个窗口里用 search_after 一路翻到底，
    ES 请求会越来越慢直到读超时。按小时切片后每片只有几千条、翻页很浅。

    Args:
        start_time: 起始时间 ``yyyy-MM-dd HH:mm:ss``。
        end_time: 结束时间 ``yyyy-MM-dd HH:mm:ss``。
        hours: 每个窗口的小时数，<=0 时不切片。

    Returns:
        list: ``[(窗口起, 窗口止), ...]``，秒级不重不漏。
    """
    if not hours or hours <= 0:
        return [(start_time, end_time)]
    start = datetime.datetime.strptime(start_time, _TIME_FORMAT)
    end = datetime.datetime.strptime(end_time, _TIME_FORMAT)
    step = datetime.timedelta(hours=hours)
    one_second = datetime.timedelta(seconds=1)
    windows = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + step - one_second, end)
        windows.append((cursor.strftime(_TIME_FORMAT),
                        window_end.strftime(_TIME_FORMAT)))
        cursor = window_end + one_second
    return windows


def search_with_retry(client, body, page_size, retries=None, timeout=None,
                      index=None):
    # type: (object, dict, int, int, int, str) -> dict
    """执行一次候选帖查询，读超时后重试。

    ES 偶发读超时（尤其分片负载高时），重试比整个任务失败划算得多。

    Args:
        client: OpenSearch 客户端。
        body: 查询主体。
        page_size: 每页条数。
        retries: 重试次数，默认取 ``JOB_CONFIG.es_retries``。
        timeout: 单次请求超时秒数，默认取 ``JOB_CONFIG.es_timeout``。
        index: 源索引，默认取 ``config.SOURCE_INDEX``。历史回溯要按年份
            切换索引（``artificial_warning_push_2025`` 等），所以做成参数。

    Returns:
        dict: ES 响应。

    Raises:
        Exception: 重试用尽后抛出最后一次异常。
    """
    retries = JOB_CONFIG.get("es_retries", 2) if retries is None else retries
    timeout = JOB_CONFIG.get("es_timeout", 300) if timeout is None else timeout
    index = index or SOURCE_INDEX
    last_error = None
    for attempt in range(retries + 1):
        try:
            return client.search(
                index=index, size=page_size, _source=SOURCE_FIELDS,
                body=body, request_timeout=timeout,
            )
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise last_error


def _text(value):
    # type: (object) -> str
    """把可能是列表的 ES 字段拼成一段文本（用于送模型和别名匹配）。"""
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _join_region(value):
    # type: (object) -> str
    """地域类多值字段用逗号拼接，与 media_* 里的既有写法保持一致。"""
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value if str(item).strip())
    return str(value or "").strip()


def flatten_post(hit):
    # type: (dict) -> dict
    """把预警 ES hit 展平成账号帖文。

    注意：预警索引的 ``author_persona`` 只有 name/id/verified/verified_type/
    gender/ip_region/his_location/cpt_location，**没有** description 和
    verified_reason，这两个字段先留空，后续从 ``media_*`` 回补。

    Args:
        hit: ES 命中项。

    Returns:
        dict: 展平后的帖文与账号资料。
    """
    source = hit.get("_source", {})
    persona = source.get("author_persona") or {}
    raw_site_name = _text(source.get("siteName")).strip()
    site_name, media_index = resolve_media_target(raw_site_name)
    return {
        "raw_site_name": raw_site_name,
        "site_name": site_name,
        "media_index": media_index,
        "uid": str(persona.get("id") or "").strip(),
        "name": _text(persona.get("name")).strip(),
        "title": _text(source.get("title")),
        "content": _text(source.get("content")),
        "url": _text(source.get("url")),
        "publish_time": _text(source.get("publishTime")),
        "verified": persona.get("verified", ""),
        "verified_type": persona.get("verified_type", ""),
        "gender": _text(persona.get("gender")),
        "ip_region": _join_region(persona.get("ip_region")),
        "cpt_location": _join_region(persona.get("cpt_location")),
        "freq_history_location": _join_region(persona.get("his_location")),
        # 预警索引的 author_persona 没有这两个字段，先占位留空，
        # 后续由 enrich_from_media 从 media_* 回补。
        "description": "",
        "verified_reason": "",
    }


def collect_accounts(client, start_time, end_time, max_accounts=None,
                     posts_per_account=3, page_size=500, stats=None,
                     index=None, skip_account=None, window_hours=None):
    # type: (object, str, str, int, int, int, dict, str, object, int) -> list
    """拉取候选帖并按账号去重聚合。

    用 ``search_after`` 顺序翻页（不用 scroll，避免长时间占用 scroll 上下文）。
    同一账号最多保留 ``posts_per_account`` 条帖文，且优先保留命中身份别名的帖子。

    Args:
        client: OpenSearch 客户端。
        start_time: 起始时间。
        end_time: 结束时间。
        max_accounts: 账号数上限，None 为不限。
        posts_per_account: 每账号保留的帖文数。
        page_size: 每页条数。
        stats: 统计字典，原地累加。
        index: 源索引，默认取 ``config.SOURCE_INDEX``。
        skip_account: 可选回调 ``fn(dedup_key) -> bool``，返回 True 表示该账号
            已处理过、直接跳过。历史回溯用它做跨天/跨运行的账号级去重，
            避免同一账号被反复判断。
        window_hours: 时间分片粒度，默认取 ``JOB_CONFIG.window_hours``。
            历史回溯扫的天数多，用更大的粒度可以减少窗口查询次数。

    Returns:
        list: 去重后的账号列表，每项含 ``posts`` 帖文列表。
    """
    stats = stats if stats is not None else {}
    stats.setdefault("candidate_posts", 0)
    stats.setdefault("skipped_no_uid", 0)
    stats.setdefault("skipped_derived_text", 0)
    stats.setdefault("skipped_unmapped_site", 0)
    stats.setdefault("skipped_already_done", 0)
    unmapped_sites = Counter()
    skipped_keys = set()

    accounts = {}
    reached_limit = False
    windows = iter_time_windows(
        start_time, end_time,
        JOB_CONFIG.get("window_hours", 1) if window_hours is None
        else window_hours)
    stats["time_windows"] = len(windows)

    for window_index, (window_start, window_end) in enumerate(windows, 1):
        if reached_limit:
            break
        query = build_candidate_query(window_start, window_end)
        search_after = None

        while True:
            body = {
                "query": query,
                "sort": [{"publishTime": "asc"}, {"_id": "asc"}],
                "track_total_hits": False,
            }
            if search_after:
                body["search_after"] = search_after
            response = search_with_retry(client, body, page_size, index=index)
            hits = response["hits"]["hits"]
            if not hits:
                break

            for hit in hits:
                stats["candidate_posts"] += 1
                post = flatten_post(hit)
                if not post["uid"]:
                    stats["skipped_no_uid"] += 1
                    continue
                if post["url"][-4:].lower() in _DERIVED_URL_SUFFIX:
                    stats["skipped_derived_text"] += 1
                    continue
                if not post["media_index"]:
                    stats["skipped_unmapped_site"] += 1
                    unmapped_sites[post["raw_site_name"]] += 1
                    continue

                dedup_key = "{}|{}".format(post["site_name"], post["uid"])
                if dedup_key in skipped_keys:
                    continue
                account = accounts.get(dedup_key)
                if account is None:
                    # 跨天/跨运行去重：历史回溯里同一账号会在多天反复出现，
                    # 已判断过的直接跳过，避免重复消耗模型调用。
                    if skip_account is not None and skip_account(dedup_key):
                        skipped_keys.add(dedup_key)
                        stats["skipped_already_done"] += 1
                        continue
                    if max_accounts and len(accounts) >= max_accounts:
                        # 账号数已达上限，不再新建账号也不再继续翻页。
                        reached_limit = True
                        break
                    account = {
                        "dedup_key": dedup_key,
                        "site_name": post["site_name"],
                        "raw_site_name": post["raw_site_name"],
                        "media_index": post["media_index"],
                        "platform": post["site_name"],
                        "uid": post["uid"],
                        "name": post["name"],
                        "verified": post["verified"],
                        "verified_type": post["verified_type"],
                        # 预警侧没有这两个字段，占位后从 media_* 回补
                        "verified_reason": "",
                        "description": "",
                        "gender": post["gender"],
                        "ip_region": post["ip_region"],
                        "cpt_location": post["cpt_location"],
                        "freq_history_location": post["freq_history_location"],
                        "posts": [],
                        "post_count": 0,
                    }
                    accounts[dedup_key] = account

                account["post_count"] += 1
                if len(account["posts"]) < posts_per_account:
                    account["posts"].append(post)
                elif _alias_matcher.findall(post["title"] + post["content"]):
                    # 已满时用命中别名的帖子替换掉没命中的，提升判断信噪比。
                    # 注意循环变量不能叫 index，会覆盖函数的 index 参数。
                    for post_index, kept in enumerate(account["posts"]):
                        if not _alias_matcher.findall(
                                kept["title"] + kept["content"]):
                            account["posts"][post_index] = post
                            break

            if reached_limit:
                break
            search_after = hits[-1].get("sort")
            if not search_after:
                break

        if window_index % 6 == 0 or window_index == len(windows):
            print("      时间窗 {}/{}：累计候选帖={} 去重账号={}".format(
                window_index, len(windows),
                stats["candidate_posts"], len(accounts)))

    stats["reached_account_limit"] = reached_limit
    stats["unmapped_sites_top"] = unmapped_sites.most_common(15)
    stats["unique_accounts"] = len(accounts)
    return list(accounts.values())


def account_alias_text(account):
    # type: (dict) -> str
    """拼出用于别名粗匹配的全量文本（不参与长度门槛，可以拼全）。"""
    parts = [account.get("name", ""), account.get("description", ""),
             account.get("verified_reason", "")]
    for post in account.get("posts", []):
        parts.append(post.get("title", ""))
        parts.append(post.get("content", ""))
    return " ".join(part for part in parts if part)


def rough_prefilter(account):
    # type: (dict) -> bool
    """粗预筛：排除官方/机构账号，且要求文本命中任一身份别名。

    纯本地规则，用于在查 ES 资料和调模型前砍掉绝大多数无关账号。

    Args:
        account: 账号记录。

    Returns:
        True 表示继续后续流程。
    """
    if is_organization_account(account):
        return False
    return bool(_alias_matcher.findall(account_alias_text(account)))


def select_judge_post(account):
    # type: (dict) -> dict
    """从账号保留的帖文里挑一条带本人身份直接信号的作为判断输入。

    这里刻意**逐帖**判断而不是把多条帖合并：``general_judge`` 的直接信号校验
    对正文有 1500 字长度上限（超长多为新闻稿、访谈，误归风险高），
    合并多帖很容易超限而被整体判为无信号。逐帖判断既能规避长度门槛，
    也让送模型的文本信噪比更高。

    Args:
        account: 账号记录。

    Returns:
        dict: 命中直接信号的帖文；都没有则返回空 dict。
    """
    max_len = JOB_CONFIG.get("max_content_len", 1200)
    for post in account.get("posts", []):
        probe = {
            "title": post.get("title", "")[:max_len],
            "content": post.get("content", "")[:max_len],
            "name": account.get("name", ""),
            "verified_reason": account.get("verified_reason", ""),
            "description": account.get("description", ""),
            "verified": account.get("verified", ""),
            "verified_type": account.get("verified_type", ""),
            "platform": account.get("platform", ""),
        }
        if candidate_has_direct_signal(probe):
            return post
    return {}


def enrich_from_media(client, accounts, stats=None):
    # type: (object, list, dict) -> dict
    """从 media_* 回补账号资料，并顺带拿到已有文档信息。

    预警索引没有 description / verified_reason，而这两个字段对官号识别和
    身份判断很关键（如简介写着"三甲医院儿科医师"）。这里批量查一次 media_*，
    既回补资料，又复用查询结果判断新旧账号，避免回写时重复查询。

    Args:
        client: OpenSearch 客户端。
        accounts: 通过粗预筛的账号列表，原地补充字段。
        stats: 统计字典。

    Returns:
        dict: ``find_existing_docs`` 的结果，供回写阶段复用。
    """
    stats = stats if stats is not None else {}
    existing = find_existing_docs(client, accounts)
    enriched = 0
    for account in accounts:
        hit = existing.get(account["dedup_key"])
        if not hit:
            continue
        source = hit.get("source") or {}
        for field in ("description", "verified_reason"):
            value = _text(source.get(field)).strip()
            if value and not account.get(field):
                account[field] = value
                enriched += 1
        if not account.get("name"):
            account["name"] = _text(source.get("name")).strip()
        account["existing_identity"] = _text(source.get("identity"))
        account["existing_community"] = _text(source.get("community"))
    stats["existing_accounts"] = len(existing)
    stats["new_accounts"] = len(accounts) - len(existing)
    stats["profile_fields_enriched"] = enriched
    return existing


def judge_account(account):
    # type: (dict) -> dict
    """对单个账号做身份判断，并对三新身份追加职业硬门槛。

    判断输入取 ``judge_post``（严格预筛选出的那条帖），不做多帖合并。

    Args:
        account: 账号记录，需已含 ``judge_post``。

    Returns:
        dict: 判断结果，含 ``standard_identities``、``details``、``log``。
    """
    max_len = JOB_CONFIG.get("max_content_len", 1200)
    post = account.get("judge_post") or {}
    title = post.get("title", "")[:max_len]
    content = post.get("content", "")[:max_len]
    result = judge_general_identity(
        title, content, account.get("name", ""),
        account.get("verified_reason", ""), account.get("description", ""),
        account.get("verified", ""), account.get("verified_type", ""),
        account.get("platform", ""),
    )

    # 硬门槛的判定文本必须带上简介和认证：很多账号的职业信息只写在简介里
    # （如简介「本人外卖骑手」），只看账号名+正文会把这类真实从业者误拦。
    source_text = " ".join(str(part or "") for part in (
        account.get("name", ""), account.get("verified_reason", ""),
        account.get("description", ""), title, content,
    ))
    accepted = []
    rejected = []
    for item in result.get("identities", []):
        identity = item.get("standard_identity", "")

        # 门槛一：每个身份都要过自己的职业锚点门槛（纯规则，零调用）。
        # 只靠模型 + 通用自述校验会把"沾边"账号放进来，比如只写
        # "劳动维权找我" 的代理人被判律师、做升学咨询的中介被判教师。
        passed, gate_reason = passes_identity_gate(
            identity,
            evidence=item.get("evidence", ""),
            name=account.get("name", ""),
            description=account.get("description", ""),
            verified_reason=account.get("verified_reason", ""),
            title=title,
            content=content,
        )
        if not passed:
            item["reject_reason"] = "身份门槛未通过: {}".format(gate_reason)
            rejected.append(item)
            continue
        item["gate_reason"] = gate_reason

        # 门槛二：三新身份误判代价最高，再叠加 judge.py 的确定性职业硬门槛。
        if identity in NEW_EMPLOYMENT_COMMUNITIES and not passes_new_employment_hard_gate(
                identity, source_text, account.get("name", "")):
            item["reject_reason"] = "三新职业硬门槛未通过"
            rejected.append(item)
            continue
        accepted.append(item)

    return {
        "standard_identities": [item["standard_identity"] for item in accepted],
        "details": accepted,
        "rejected": rejected,
        "request_id": result.get("request_id", ""),
        "log": result.get("log", ""),
    }


def _reject_row(account, item):
    # type: (dict, dict) -> dict
    """构造一行被门槛拦掉的记录，便于复核门槛是否过严。"""
    post = account.get("judge_post") or {}
    return {
        "id": account["dedup_key"],
        "platform": account.get("site_name", ""),
        "name": account.get("name", ""),
        "standard_identity": item.get("standard_identity", ""),
        "raw_identity": item.get("raw_identity", ""),
        "evidence": item.get("evidence", ""),
        "model_reason": item.get("reason", ""),
        "reject_reason": item.get("reject_reason", ""),
        "description": account.get("description", ""),
        "verified_reason": account.get("verified_reason", ""),
        "url": post.get("url", ""),
    }


def _audit_row(account, detail=None):
    # type: (dict, dict) -> dict
    """构造一行审计明细。"""
    max_len = JOB_CONFIG.get("max_content_len", 1200)
    post = account.get("judge_post") or {}
    title = post.get("title", "")[:max_len]
    content = post.get("content", "")[:max_len]
    identity = (detail or {}).get("standard_identity", "")
    return {
        "id": account["dedup_key"],
        "platform": account["site_name"],
        "raw_site_name": account["raw_site_name"],
        "uid": account["uid"],
        "name": account.get("name", ""),
        "identity_group": GROUP_BY_IDENTITY.get(identity, ""),
        "standard_identity": identity,
        "raw_identity": (detail or {}).get("raw_identity", ""),
        "write_field": "community" if identity in NEW_EMPLOYMENT_COMMUNITIES else "identity",
        "evidence": (detail or {}).get("evidence", ""),
        "reason": (detail or {}).get("reason", ""),
        "write_mode": account.get("write_mode", ""),
        "written_index": account.get("written_index", account.get("media_index", "")),
        "written_fields": json.dumps(
            account.get("identity_fields") or {}, ensure_ascii=False),
        "existing_identity": account.get("existing_identity", ""),
        "existing_community": account.get("existing_community", ""),
        "post_count": account.get("post_count", 0),
        "title": title,
        "content": content,
        "url": post.get("url", ""),
        "publish_time": post.get("publish_time", ""),
        "verified": account.get("verified", ""),
        "verified_type": account.get("verified_type", ""),
        "verified_reason": account.get("verified_reason", ""),
        "description": account.get("description", ""),
        "request_id": account.get("request_id", ""),
    }


AUDIT_COLUMNS = [
    ("id", "id(平台|uid)"),
    ("platform", "平台"),
    ("raw_site_name", "预警原始平台名"),
    ("uid", "账号id"),
    ("name", "账号名"),
    ("identity_group", "身份业务组"),
    ("standard_identity", "标准身份"),
    ("raw_identity", "原始细分身份"),
    ("write_field", "写入字段"),
    ("evidence", "证据原文"),
    ("reason", "判断原因"),
    ("write_mode", "写入方式"),
    ("written_index", "目标media索引"),
    ("written_fields", "实际写入字段"),
    ("existing_identity", "原有identity"),
    ("existing_community", "原有community"),
    ("post_count", "当日预警帖数"),
    ("title", "标题"),
    ("content", "正文"),
    ("url", "url"),
    ("publish_time", "发布时间"),
    ("verified", "认证状态"),
    ("verified_type", "认证类型"),
    ("verified_reason", "认证说明"),
    ("description", "账号简介"),
    ("request_id", "模型请求id"),
]


def _sanitize(value):
    # type: (object) -> object
    """去掉 Excel 不接受的控制字符。"""
    if isinstance(value, str):
        return _EXCEL_ILLEGAL.sub("", value)
    return value


REJECT_COLUMNS = [
    ("id", "id(平台|uid)"),
    ("platform", "平台"),
    ("name", "账号名"),
    ("standard_identity", "模型判定身份"),
    ("raw_identity", "原始细分身份"),
    ("reject_reason", "拦截原因"),
    ("evidence", "证据原文"),
    ("model_reason", "模型理由"),
    ("description", "账号简介"),
    ("verified_reason", "认证说明"),
    ("url", "url"),
]


def export_report(rows, stats, group_counter, output_path, reject_rows=None):
    # type: (list, dict, Counter, str, list) -> None
    """导出运行汇总、身份明细与门槛拦截明细 Excel。

    Args:
        rows: 审计明细行。
        stats: 运行统计。
        group_counter: 各身份业务组命中账号数。
        output_path: xlsx 输出路径。
        reject_rows: 被身份门槛拦掉的记录，用于复核门槛是否过严。
    """
    import pandas as pd

    keys = [key for key, _ in AUDIT_COLUMNS]
    headers = [header for _, header in AUDIT_COLUMNS]
    detail = pd.DataFrame(
        [[_sanitize(row.get(key, "")) for key in keys] for row in rows],
        columns=headers,
    )
    summary = pd.DataFrame(
        [[key, _sanitize(json.dumps(value, ensure_ascii=False)
                         if isinstance(value, (list, dict)) else value)]
         for key, value in stats.items()],
        columns=["指标", "结果"],
    )
    groups = pd.DataFrame(
        [[group, IDENTITY_GROUPS.get(group) and "/".join(IDENTITY_GROUPS[group]), count]
         for group, count in group_counter.most_common()],
        columns=["身份业务组", "包含标准身份", "命中账号数"],
    )
    reject_keys = [key for key, _ in REJECT_COLUMNS]
    reject_headers = [header for _, header in REJECT_COLUMNS]
    rejects = pd.DataFrame(
        [[_sanitize(row.get(key, "")) for key in reject_keys]
         for row in (reject_rows or [])],
        columns=reject_headers,
    )
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="运行汇总", index=False)
        groups.to_excel(writer, sheet_name="身份分布", index=False)
        detail.to_excel(writer, sheet_name="身份明细", index=False)
        rejects.to_excel(writer, sheet_name="门槛拦截明细", index=False)


def run(date=None, start_time=None, end_time=None, max_accounts=None,
        max_judge=None, workers=None, dry_run=False, output_path=None,
        source_index=None, keep_days=None):
    # type: (str, str, str, int, int, int, bool, str, str, int) -> dict
    """执行一天的预警账号身份识别与画像回写。

    Args:
        date: 目标日期 ``yyyy-MM-dd``，默认昨天。
        start_time: 自定义起始时间，优先于 date。
        end_time: 自定义结束时间，优先于 date。
        max_accounts: 账号数上限。
        max_judge: 模型调用次数上限。
        workers: 模型并发数。
        dry_run: 只判断不写库。
        output_path: 报告输出路径（xlsx）。
        source_index: 源索引，默认取 ``config.SOURCE_INDEX``。
        keep_days: 产物保留天数，<=0 不清理。默认取 ``JOB_CONFIG.output_keep_days``。

    Returns:
        dict: 运行统计。
    """
    source_index = source_index or SOURCE_INDEX
    date = date or yesterday()
    start_time = start_time or "{} 00:00:00".format(date)
    end_time = end_time or "{} 23:59:59".format(date)
    workers = workers or JOB_CONFIG["judge_workers"]
    max_accounts = max_accounts if max_accounts is not None else JOB_CONFIG["max_accounts"]
    max_judge = max_judge if max_judge is not None else JOB_CONFIG["max_judge"]

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "daily_identity_{}_{}.xlsx".format(
            date.replace("-", ""), time.strftime("%H%M%S")))
    jsonl_path = os.path.splitext(output_path)[0] + ".jsonl"

    stats = {
        "source_index": source_index,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "model": MODEL_NAME,
        "dry_run": dry_run,
    }
    started = time.time()
    client = get_client()

    print("[1/5] 拉取候选帖并按账号去重: {} ~ {}".format(start_time, end_time))
    accounts = collect_accounts(
        client, start_time, end_time,
        max_accounts=max_accounts,
        posts_per_account=JOB_CONFIG["posts_per_account"],
        page_size=JOB_CONFIG["page_size"],
        stats=stats,
        index=source_index,
    )
    print("      候选帖={} 去重账号={} 平台未映射跳过={}".format(
        stats["candidate_posts"], stats["unique_accounts"],
        stats["skipped_unmapped_site"]))

    print("[2/5] 本地粗预筛（官号排除 + 身份别名命中）")
    rough_passed = [account for account in accounts if rough_prefilter(account)]
    stats["rough_passed_accounts"] = len(rough_passed)
    print("      粗预筛通过={}".format(len(rough_passed)))

    print("[3/5] 从 media_* 回补账号资料并识别新旧账号")
    existing = enrich_from_media(client, rough_passed, stats)
    print("      已有账号={} 新账号={} 资料回补字段数={}".format(
        stats["existing_accounts"], stats["new_accounts"],
        stats["profile_fields_enriched"]))

    strict_passed = []
    for account in rough_passed:
        judge_post = select_judge_post(account)
        if judge_post:
            account["judge_post"] = judge_post
            strict_passed.append(account)
    stats["strict_passed_accounts"] = len(strict_passed)
    if max_judge:
        strict_passed = strict_passed[:max_judge]
    stats["judged_accounts"] = len(strict_passed)
    print("      严格预筛通过={} 实际送模型={}".format(
        stats["strict_passed_accounts"], stats["judged_accounts"]))

    print("[4/5] 模型判断 20 类身份 (并发={}, 模型={})".format(workers, MODEL_NAME))
    hit_accounts = []
    rows = []
    reject_rows = []
    group_counter = Counter()
    identity_counter = Counter()
    reject_counter = Counter()
    rejected_by_gate = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(judge_account, a): a for a in strict_passed}
        for index, future in enumerate(as_completed(futures), 1):
            account = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                account["judge_error"] = str(exc)[:200]
                continue
            account["request_id"] = result.get("request_id", "")
            for item in result.get("rejected", []):
                rejected_by_gate += 1
                reject_counter[item.get("standard_identity", "")] += 1
                reject_rows.append(_reject_row(account, item))
            if not result["standard_identities"]:
                continue
            account["standard_identities"] = result["standard_identities"]
            account["judge_details"] = result["details"]
            hit_accounts.append(account)
            for identity in result["standard_identities"]:
                identity_counter[identity] += 1
                group_counter[GROUP_BY_IDENTITY.get(identity, "未知")] += 1
            if index % 200 == 0:
                print("      已判断 {}/{}，命中 {}".format(
                    index, len(strict_passed), len(hit_accounts)))

    stats["hit_accounts"] = len(hit_accounts)
    stats["rejected_by_identity_gate"] = rejected_by_gate
    stats["rejected_by_identity"] = dict(reject_counter.most_common())
    stats["by_identity"] = dict(identity_counter)
    stats["by_group"] = dict(group_counter)
    print("      命中身份账号={} 身份门槛拦截={}".format(
        len(hit_accounts), rejected_by_gate))

    print("[5/5] 回写 media_*（三新→community，其他→identity）")
    from utils.identity_mapper import load_identity_mapping

    identity_map = load_identity_mapping()
    write_report = write_back(
        hit_accounts, identity_map=identity_map, client=client, dry_run=dry_run,
    )
    stats["write"] = {
        key: value for key, value in write_report.items()
        if key not in ("skipped", "errors")
    }
    stats["write_errors"] = write_report.get("errors", [])[:5]
    print("      更新已有账号={} 新插入账号={} 失败={}{}".format(
        write_report["update"], write_report["insert"], write_report["failed"],
        "（dry_run，未实际写入）" if dry_run else ""))

    for account in hit_accounts:
        for detail in account.get("judge_details", []):
            rows.append(_audit_row(account, detail))

    with open(jsonl_path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    stats["elapsed_seconds"] = round(time.time() - started, 1)
    stats["identity_records"] = len(rows)
    stats["jsonl_path"] = jsonl_path
    stats["excel_path"] = output_path
    export_report(rows, stats, group_counter, output_path, reject_rows)

    # 清理超期产物（在生成本次报告之后，所以本次的文件一定会保留）
    cleanup = cleanup_old_outputs(keep_days=keep_days)
    stats["output_cleanup"] = {
        "keep_days": keep_days if keep_days is not None
        else JOB_CONFIG.get("output_keep_days", 1),
        "removed": len(cleanup["removed"]),
        "kept": cleanup["kept"],
    }
    if cleanup["removed"]:
        print("      已清理过期产物 {} 个（保留 {} 天）".format(
            len(cleanup["removed"]), stats["output_cleanup"]["keep_days"]))

    print("\n===== 运行统计 =====")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("\nJSONL: {}\nExcel: {}".format(jsonl_path, output_path))
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="预警账号身份识别每日批量任务（回写 media_*）")
    parser.add_argument("--date", default=None,
                        help="目标日期 yyyy-MM-dd，默认昨天")
    parser.add_argument("--start", dest="start_time", default=None,
                        help="自定义起始时间 'yyyy-MM-dd HH:mm:ss'，优先于 --date")
    parser.add_argument("--end", dest="end_time", default=None,
                        help="自定义结束时间 'yyyy-MM-dd HH:mm:ss'，优先于 --date")
    parser.add_argument("--max-accounts", type=int, default=None,
                        help="账号数上限（验证时建议设小，如 200）")
    parser.add_argument("--max-judge", type=int, default=None,
                        help="模型调用次数上限")
    parser.add_argument("--workers", type=int, default=None,
                        help="模型并发数，默认取 JOB_CONFIG.judge_workers")
    parser.add_argument("--dry-run", action="store_true",
                        help="只判断不写库，用于验证")
    parser.add_argument("--output", default=None, help="报告输出路径（xlsx）")
    parser.add_argument("--keep-days", type=int, default=None,
                        help="产物保留天数，默认 1（只留当天）；设 0 表示不清理")
    args = parser.parse_args()
    run(
        date=args.date, start_time=args.start_time, end_time=args.end_time,
        max_accounts=args.max_accounts, max_judge=args.max_judge,
        workers=args.workers, dry_run=args.dry_run, output_path=args.output,
        keep_days=args.keep_days,
    )


if __name__ == "__main__":
    main()

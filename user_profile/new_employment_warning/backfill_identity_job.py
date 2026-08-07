# -*- coding: utf-8 -*-
"""预警账号身份识别历史回溯任务。

与每日增量任务（``daily_identity_job``）**共用同一套判断与回写逻辑**，
保证两路口径完全一致；差别只在取数范围和运行策略：

============  ==========================  ==============================
              增量路 daily_identity_job    历史路 backfill_identity_job
============  ==========================  ==============================
调度          K8s CronJob 每天一次         手动/一次性 Job，跑几十小时
范围          昨天一天                     指定年份索引 + 日期区间
账号去重      当天内去重                   **跨天 + 跨运行**去重（Redis 布隆）
断点          不需要（每天独立）           按天记录 checkpoint，可续跑
限速          不需要                       每天之间 sleep，可设调用上限
============  ==========================  ==============================

为什么必须做跨天账号去重：历史上同一个账号会在多天反复出现，
按天独立跑会把同一账号判断很多次。实测 2025 单年有 1116 万条身份词候选帖，
但去重后只有 528 万个账号，去重能省掉一半以上的模型调用。

日期默认**从新到旧**遍历，因为近期数据的画像价值更高，
即使中途停下来，也已经把最有价值的部分算完了。

运行示例::

    # 先小样本试跑，不写库
    python3 -m new_employment_warning.backfill_identity_job \\
        --index artificial_warning_push_2026 \\
        --start-date 2026-07-01 --end-date 2026-07-03 \\
        --max-judge-total 200 --dry-run

    # 正式回溯 2026 全年（可中断，重跑自动续）
    python3 -m new_employment_warning.backfill_identity_job \\
        --index artificial_warning_push_2026 \\
        --start-date 2026-01-01 --end-date 2026-12-31

    # 分批控制成本：本次只跑 5 万次模型调用就停
    python3 -m new_employment_warning.backfill_identity_job \\
        --index artificial_warning_push_2025 \\
        --start-date 2025-01-01 --end-date 2025-12-31 \\
        --max-judge-total 50000
"""
import argparse
import datetime
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from new_employment_warning.config import (
    BACKFILL_CONFIG,
    JOB_CONFIG,
    OUTPUT_DIR,
    SOURCE_INDEX,
)
from new_employment_warning.daily_identity_job import (
    GROUP_BY_IDENTITY,
    _audit_row,
    _reject_row,
    collect_accounts,
    enrich_from_media,
    judge_account,
    rough_prefilter,
    select_judge_post,
)
from new_employment_warning.llm_client import MODEL_NAME
from new_employment_warning.media_writer import get_client, write_back


class AccountDedup(object):
    """跨天、跨运行的账号级去重。

    优先用 Redis 布隆过滤器：多次运行、多个副本能共享同一份"已处理"状态，
    重跑不会重复消耗模型调用。Redis 不可用时退化为进程内集合（单次运行有效），
    保证任务仍能跑完而不是直接失败。

    Attributes:
        bloom: BloomFilter 实例，Redis 不可用时为 None。
        local: 进程内已处理账号集合，兼作 Redis 模式下的本次运行缓存。
    """

    def __init__(self, bloom_key=None, enabled=True):
        # type: (str, bool) -> None
        """初始化去重器。

        Args:
            bloom_key: Redis 布隆过滤器 key，None 时取 ``BACKFILL_CONFIG``。
            enabled: 为 False 时完全不去重（每个账号都重新判断）。
        """
        self.enabled = enabled
        self.local = set()
        self.bloom = None
        self.backend = "disabled"
        if not enabled:
            return
        bloom_key = bloom_key or BACKFILL_CONFIG["bloom_key"]
        try:
            from config.settings import config
            from utils.bloom import BloomFilter

            self.bloom = BloomFilter(
                config["redis"]["redis_url_identity_bloom"], bloom_key)
            self.backend = "redis:{}".format(bloom_key)
        except Exception as exc:
            print("[警告] Redis 布隆过滤器不可用（{}），"
                  "退化为进程内去重，重跑会重复判断".format(str(exc)[:80]))
            self.backend = "memory"

    def seen(self, dedup_key):
        # type: (str) -> bool
        """判断账号是否已处理过。"""
        if not self.enabled:
            return False
        if dedup_key in self.local:
            return True
        if self.bloom is not None:
            try:
                return bool(self.bloom.is_double(dedup_key))
            except Exception:
                return False
        return False

    def mark(self, dedup_key):
        # type: (str) -> None
        """标记账号已处理。"""
        if not self.enabled:
            return
        self.local.add(dedup_key)
        if self.bloom is not None:
            try:
                self.bloom.add_value(dedup_key)
            except Exception:
                pass


def iter_dates_desc(start_date, end_date):
    # type: (str, str) -> list
    """生成从新到旧的日期列表。

    近期数据画像价值更高，倒序遍历让中途停止时已完成的部分最有价值。

    Args:
        start_date: 起始日期 ``yyyy-MM-dd``（较早）。
        end_date: 结束日期 ``yyyy-MM-dd``（较晚）。

    Returns:
        list: 日期字符串列表，从 end_date 递减到 start_date。
    """
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    dates = []
    cursor = end
    while cursor >= start:
        dates.append(cursor.strftime("%Y-%m-%d"))
        cursor -= datetime.timedelta(days=1)
    return dates


def _load_checkpoint(path, meta):
    # type: (str, dict) -> dict
    """加载断点，参数不一致时报错以免混用两次不同口径的结果。"""
    if not os.path.exists(path):
        return {"meta": meta, "done_dates": [], "totals": {}}
    with open(path, "r", encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("meta") != meta:
        old = state.get("meta") or {}
        diff = sorted(
            key for key in set(old) | set(meta) if old.get(key) != meta.get(key)
        )
        raise ValueError(
            "断点参数与本次运行不一致，拒绝复用（避免把两次不同口径的结果混在一起）。\n"
            "  不一致的参数: {}\n"
            "  旧: {}\n"
            "  新: {}\n"
            "解决办法（二选一）：\n"
            "  1) 删掉旧断点重新开始:  rm -f {}\n"
            "  2) 换一个断点文件:      --checkpoint <新路径>".format(
                ", ".join(diff) or "(未知)", old, meta, path))
    return state


def _save_checkpoint(path, state):
    # type: (str, dict) -> None
    """保存断点。"""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def process_day(client, date, source_index, dedup, identity_map,
                workers, max_judge, skip_existing_identity, dry_run,
                max_accounts=None, window_hours=None):
    # type: (object, str, str, AccountDedup, dict, int, int, bool, bool, int, int) -> dict
    """处理单个日期：取数 → 去重 → 预筛 → 判断 → 回写。

    与增量路复用完全相同的函数，只是多了跨天去重和"跳过已有身份"两个开关。

    Args:
        client: OpenSearch 客户端。
        date: 目标日期 ``yyyy-MM-dd``。
        source_index: 源索引。
        dedup: 账号去重器。
        identity_map: 身份标准化映射表。
        workers: 模型并发数。
        max_judge: 本日模型调用上限，None 为不限。
        skip_existing_identity: 是否跳过 media_* 里已有身份的账号。
        dry_run: 只判断不写库。
        max_accounts: 本日收集账号数上限。设了它会提前停止扫描，
            换取速度但会漏掉当天剩余账号；追求全量覆盖时不要设。
        window_hours: 时间分片粒度。

    Returns:
        dict: 本日统计与明细。
    """
    stats = {"date": date}
    started = time.time()

    accounts = collect_accounts(
        client, "{} 00:00:00".format(date), "{} 23:59:59".format(date),
        max_accounts=max_accounts,
        posts_per_account=JOB_CONFIG["posts_per_account"],
        page_size=JOB_CONFIG["page_size"],
        stats=stats, index=source_index,
        skip_account=dedup.seen, window_hours=window_hours,
    )

    rough_passed = [a for a in accounts if rough_prefilter(a)]
    stats["rough_passed_accounts"] = len(rough_passed)

    enrich_from_media(client, rough_passed, stats)

    # 跳过已有身份的账号：历史回溯量大，这一步能省掉相当比例的模型调用。
    if skip_existing_identity:
        before = len(rough_passed)
        rough_passed = [
            a for a in rough_passed
            if not (a.get("existing_identity") or a.get("existing_community"))
        ]
        stats["skipped_existing_identity"] = before - len(rough_passed)

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

    hit_accounts = []
    rows = []
    reject_rows = []
    identity_counter = Counter()
    rejected_by_gate = 0
    if strict_passed:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(judge_account, a): a
                       for a in strict_passed}
            for future in as_completed(futures):
                account = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    account["judge_error"] = str(exc)[:200]
                    continue
                account["request_id"] = result.get("request_id", "")
                for item in result.get("rejected", []):
                    rejected_by_gate += 1
                    reject_rows.append(_reject_row(account, item))
                if not result["standard_identities"]:
                    continue
                account["standard_identities"] = result["standard_identities"]
                account["judge_details"] = result["details"]
                hit_accounts.append(account)
                for identity in result["standard_identities"]:
                    identity_counter[identity] += 1

    # 标记已处理，避免下次重复判断（命中与否都标记，未命中的重判也是浪费）。
    # 但 dry_run 只是试跑、没有真正写库，绝不能标记：否则正式运行会把这些账号
    # 当成"已处理"跳过，导致它们永远不会被写入 media_*。
    if not dry_run:
        for account in strict_passed:
            dedup.mark(account["dedup_key"])

    write_report = write_back(
        hit_accounts, identity_map=identity_map, client=client, dry_run=dry_run)

    for account in hit_accounts:
        for detail in account.get("judge_details", []):
            rows.append(_audit_row(account, detail))

    stats.update({
        "hit_accounts": len(hit_accounts),
        "rejected_by_identity_gate": rejected_by_gate,
        "by_identity": dict(identity_counter),
        "update": write_report["update"],
        "insert": write_report["insert"],
        "failed": write_report["failed"],
        "elapsed_seconds": round(time.time() - started, 1),
    })
    return {"stats": stats, "rows": rows, "reject_rows": reject_rows}


def run(source_index=None, start_date=None, end_date=None, workers=None,
        max_judge_per_day=None, max_judge_total=None,
        skip_existing_identity=None, dedup_enabled=True, bloom_key=None,
        dry_run=False, output_dir=None, checkpoint_path=None,
        day_sleep=None, max_accounts_per_day=None, window_hours=None):
    # type: (...) -> dict
    """执行历史回溯。

    Args:
        source_index: 源索引，如 ``artificial_warning_push_2025``。
        start_date: 起始日期（较早）。
        end_date: 结束日期（较晚）。
        workers: 模型并发数。
        max_judge_per_day: 单日模型调用上限。
        max_judge_total: 本次运行总上限，达到即停（便于分批跑）。
        skip_existing_identity: 是否跳过已有身份的账号。
        dedup_enabled: 是否启用跨天账号去重。
        bloom_key: 去重用的 Redis key。
        dry_run: 只判断不写库。
        output_dir: 每日明细输出目录。
        checkpoint_path: 断点文件路径。
        day_sleep: 每天之间的间隔秒数。
        max_accounts_per_day: 单日收集账号上限（会提前停止扫描，牺牲覆盖换速度）。
        window_hours: 时间分片粒度，回溯建议用 6 或 24 减少窗口查询次数。

    Returns:
        dict: 汇总统计。
    """
    source_index = source_index or SOURCE_INDEX
    workers = workers or BACKFILL_CONFIG["judge_workers"]
    day_sleep = (BACKFILL_CONFIG["day_sleep_seconds"]
                 if day_sleep is None else day_sleep)
    if skip_existing_identity is None:
        skip_existing_identity = BACKFILL_CONFIG["skip_existing_identity"]
    if max_judge_per_day is None:
        max_judge_per_day = BACKFILL_CONFIG["max_judge_per_day"]
    if max_judge_total is None:
        max_judge_total = BACKFILL_CONFIG["max_judge_total"]

    output_dir = output_dir or os.path.join(OUTPUT_DIR, "backfill")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if checkpoint_path is None:
        # 断点文件名带上参数指纹：不同日期区间、试跑与正式跑各用各的断点，
        # 避免"试跑完就没法正式跑"这种互相挡道的情况。
        fingerprint = "{}_{}_{}".format(
            source_index,
            (start_date or "").replace("-", ""),
            (end_date or "").replace("-", ""),
        )
        if dry_run:
            fingerprint += "_dryrun"
        checkpoint_path = os.path.join(
            output_dir, "backfill_{}.checkpoint.json".format(fingerprint))

    meta = {
        "source_index": source_index,
        "start_date": start_date,
        "end_date": end_date,
        "skip_existing_identity": bool(skip_existing_identity),
        "dedup_enabled": bool(dedup_enabled),
        "bloom_key": bloom_key or BACKFILL_CONFIG["bloom_key"],
        "dry_run": bool(dry_run),
    }
    state = _load_checkpoint(checkpoint_path, meta)
    done = set(state["done_dates"])

    dedup = AccountDedup(bloom_key=bloom_key, enabled=dedup_enabled)
    from utils.identity_mapper import load_identity_mapping

    identity_map = load_identity_mapping()
    client = get_client()

    dates = iter_dates_desc(start_date, end_date)
    pending = [d for d in dates if d not in done]
    print("历史回溯 {}".format(source_index))
    print("  日期区间   : {} ~ {}（从新到旧，共 {} 天）".format(
        start_date, end_date, len(dates)))
    print("  断点已完成 : {} 天，本次待跑 {} 天".format(len(done), len(pending)))
    print("  账号去重   : {}".format(dedup.backend))
    print("  跳过已有身份: {}".format(bool(skip_existing_identity)))
    print("  模型       : {}，并发 {}".format(MODEL_NAME, workers))
    print("  单日账号上限: {}".format(max_accounts_per_day or "不限（全量覆盖）"))
    print("  分片粒度   : {} 小时".format(
        window_hours if window_hours else JOB_CONFIG.get("window_hours", 1)))
    print("  写库       : {}".format("否（dry_run）" if dry_run else "是"))
    print("  断点文件   : {}".format(checkpoint_path))
    print("-" * 78)

    totals = Counter(state.get("totals") or {})
    identity_totals = Counter(state.get("identity_totals") or {})
    started = time.time()

    for index, date in enumerate(pending, 1):
        if max_judge_total and totals["judged_accounts"] >= max_judge_total:
            print("已达本次运行的模型调用上限 {}，停止（断点已保存，可续跑）".format(
                max_judge_total))
            break

        remaining = None
        if max_judge_total:
            remaining = max_judge_total - totals["judged_accounts"]
        day_limit = max_judge_per_day
        if remaining is not None:
            day_limit = remaining if day_limit is None else min(day_limit, remaining)

        result = process_day(
            client, date, source_index, dedup, identity_map,
            workers, day_limit, skip_existing_identity, dry_run,
            max_accounts=max_accounts_per_day, window_hours=window_hours)
        day_stats = result["stats"]

        for key in ("candidate_posts", "unique_accounts", "skipped_already_done",
                    "skipped_existing_identity", "rough_passed_accounts",
                    "strict_passed_accounts", "judged_accounts", "hit_accounts",
                    "rejected_by_identity_gate", "update", "insert", "failed"):
            totals[key] += day_stats.get(key, 0)
        identity_totals.update(day_stats.get("by_identity", {}))

        if result["rows"]:
            jsonl_path = os.path.join(
                output_dir, "backfill_{}.jsonl".format(date.replace("-", "")))
            with open(jsonl_path, "w", encoding="utf-8") as handle:
                for row in result["rows"]:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        done.add(date)
        state["done_dates"] = sorted(done)
        state["totals"] = dict(totals)
        state["identity_totals"] = dict(identity_totals)
        _save_checkpoint(checkpoint_path, state)

        print("[{}/{}] {} 候选帖={} 新账号={} 去重跳过={} 已有身份跳过={} "
              "送模型={} 命中={} 拦截={} 写入={} 耗时={}s".format(
                  index, len(pending), date,
                  day_stats.get("candidate_posts", 0),
                  day_stats.get("unique_accounts", 0),
                  day_stats.get("skipped_already_done", 0),
                  day_stats.get("skipped_existing_identity", 0),
                  day_stats.get("judged_accounts", 0),
                  day_stats.get("hit_accounts", 0),
                  day_stats.get("rejected_by_identity_gate", 0),
                  day_stats.get("update", 0) + day_stats.get("insert", 0),
                  day_stats.get("elapsed_seconds", 0)))

        if day_sleep:
            time.sleep(day_sleep)

    summary = {
        "source_index": source_index,
        "start_date": start_date,
        "end_date": end_date,
        "model": MODEL_NAME,
        "dry_run": dry_run,
        "dedup_backend": dedup.backend,
        "skip_existing_identity": bool(skip_existing_identity),
        "days_total": len(dates),
        "days_done": len(done),
        "elapsed_seconds": round(time.time() - started, 1),
        "totals": dict(totals),
        "by_identity": dict(identity_totals.most_common()),
        "checkpoint": checkpoint_path,
        "output_dir": output_dir,
    }
    print("\n===== 回溯汇总 =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="预警账号身份识别历史回溯（与每日增量共用判断逻辑）")
    parser.add_argument("--index", dest="source_index", default=None,
                        help="源索引，如 artificial_warning_push_2025")
    parser.add_argument("--start-date", required=True, help="起始日期(较早)")
    parser.add_argument("--end-date", required=True, help="结束日期(较晚)")
    parser.add_argument("--workers", type=int, default=None, help="模型并发数")
    parser.add_argument("--max-judge-per-day", type=int, default=None,
                        help="单日模型调用上限")
    parser.add_argument("--max-judge-total", type=int, default=None,
                        help="本次运行模型调用总上限，达到即停（可续跑）")
    parser.add_argument("--no-skip-existing", dest="skip_existing",
                        action="store_false", default=None,
                        help="不跳过已有身份的账号（全部重算，成本更高）")
    parser.add_argument("--no-dedup", dest="dedup", action="store_false",
                        default=True, help="关闭跨天账号去重（不推荐）")
    parser.add_argument("--bloom-key", default=None,
                        help="去重用的 Redis key；换口径重算时换一个")
    parser.add_argument("--dry-run", action="store_true", help="只判断不写库")
    parser.add_argument("--output-dir", default=None, help="每日明细输出目录")
    parser.add_argument("--checkpoint", dest="checkpoint_path", default=None,
                        help="断点文件路径")
    parser.add_argument("--day-sleep", type=float, default=None,
                        help="每天之间的间隔秒数，默认 2")
    parser.add_argument("--max-accounts-per-day", type=int, default=None,
                        help="单日收集账号上限。设了会提前停止扫描、跑得快很多，"
                             "但会漏掉当天剩余账号；追求全量覆盖时别设")
    parser.add_argument("--window-hours", type=int, default=None,
                        help="时间分片粒度（小时），默认 1；回溯建议 6 或 24，"
                             "减少窗口查询次数")
    args = parser.parse_args()

    run(
        source_index=args.source_index,
        start_date=args.start_date, end_date=args.end_date,
        workers=args.workers,
        max_judge_per_day=args.max_judge_per_day,
        max_judge_total=args.max_judge_total,
        skip_existing_identity=args.skip_existing,
        dedup_enabled=args.dedup, bloom_key=args.bloom_key,
        dry_run=args.dry_run, output_dir=args.output_dir,
        checkpoint_path=args.checkpoint_path, day_sleep=args.day_sleep,
        max_accounts_per_day=args.max_accounts_per_day,
        window_hours=args.window_hours,
    )


if __name__ == "__main__":
    main()

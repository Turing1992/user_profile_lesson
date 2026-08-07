# -*- coding: utf-8 -*-
"""按时间窗口统计人工预警数据的身份分布。

对每个身份业务组执行一次时间+身份词过滤查询，读取候选帖子总量和随机样本；
随机样本经硬规则和大模型严格判断后，估算该身份在候选帖子中的有效比例。
不使用 scroll，不逐条扫描时间窗口，不写入 media_*。
"""
import argparse
import json
import math
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from new_employment_warning.collect_general_identities import _make_row
from new_employment_warning.config import OUTPUT_DIR, SOURCE_INDEX
from new_employment_warning.general_judge import (
    IDENTITY_ALIASES,
    IDENTITY_GROUPS,
    candidate_has_direct_signal,
    judge_general_identity,
)
from new_employment_warning.scan import SOURCE_FIELDS, _flatten_hit, get_client


DEFAULT_START = "2026-07-20 00:00:00"
DEFAULT_END = "2026-07-27 23:59:59"
DEFAULT_SAMPLE_SIZE = 300
DEFAULT_MAX_JUDGE = 40


def _text(value):
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _normalize_hit(hit):
    doc = _flatten_hit(hit)
    for field in ("name", "title", "content", "verified_reason", "description"):
        doc[field] = _text(doc.get(field))
    doc["dedup_key"] = "{}|{}".format(doc.get("platform", ""), doc.get("uid", ""))
    return doc


def _group_query(group_name, start_time, end_time, seed, sample_size, stratum):
    labels = IDENTITY_GROUPS[group_name]
    aliases = []
    for identity in labels:
        aliases.extend(IDENTITY_ALIASES[identity])
    profile_should = [
        {"match_phrase": {"author_persona.name": alias}} for alias in aliases
    ]
    content_should = []
    for alias in aliases:
        for field in ("title", "content"):
            content_should.append({"match_phrase": {field: alias}})
    bool_query = {
        "filter": [{
            "range": {
                "publishTime": {
                    "gte": start_time,
                    "lte": end_time,
                    "format": "yyyy-MM-dd HH:mm:ss",
                    "time_zone": "+08:00",
                }
            }
        }],
    }
    if stratum == "profile":
        bool_query["should"] = profile_should
        bool_query["minimum_should_match"] = 1
    elif stratum == "content":
        bool_query["should"] = content_should
        bool_query["minimum_should_match"] = 1
        # 与账号名层互斥，避免重复估算同一帖子。
        bool_query["must_not"] = [{
            "bool": {"should": profile_should, "minimum_should_match": 1}
        }]
    else:
        raise ValueError("未知抽样层:{}".format(stratum))
    return {
        "size": sample_size,
        "track_total_hits": False,
        "_source": SOURCE_FIELDS,
        "query": {
            "function_score": {
                "query": {"bool": bool_query},
                "random_score": {"seed": seed, "field": "_seq_no"},
                "boost_mode": "replace",
            }
        },
        "aggs": {
            "by_day": {
                "date_histogram": {
                    "field": "publishTime",
                    "calendar_interval": "day",
                    "format": "yyyy-MM-dd",
                    "time_zone": "+08:00",
                    "min_doc_count": 1,
                }
            }
        },
    }


def query_group_sample(client, group_name, start_time, end_time, seed,
                       sample_size, stratum):
    body = _group_query(
        group_name, start_time, end_time, seed, sample_size, stratum,
    )
    response = client.search(
        index=SOURCE_INDEX,
        body=body,
        request_timeout=90,
        params={"request_cache": "true"},
    )
    docs = []
    for hit in response.get("hits", {}).get("hits", []):
        doc = _normalize_hit(hit)
        if doc["uid"] and doc["platform"]:
            docs.append(doc)
    daily = []
    for bucket in response.get("aggregations", {}).get("by_day", {}).get("buckets", []):
        daily.append({"date": bucket["key_as_string"], "candidate_posts": bucket["doc_count"]})
    return docs, daily, bool(response.get("timed_out"))


def _judge_doc(doc):
    result = judge_general_identity(
        doc["title"], doc["content"], doc["name"],
        doc.get("verified_reason", ""), doc.get("description", ""),
        doc.get("verified", ""), doc.get("verified_type", ""),
        doc.get("platform", ""),
    )
    return doc, result


def judge_accounts(accounts, workers):
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_judge_doc, doc) for doc in accounts]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _wilson_interval(successes, total, z=1.96):
    if total <= 0:
        return 0.0, 0.0
    rate = float(successes) / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    margin = z * math.sqrt((rate * (1.0 - rate) + z * z / (4.0 * total)) / total)
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


def _process_stratum(client, group_name, start_time, end_time, sample_size,
                      max_judge, workers, seed, stratum):
    labels = IDENTITY_GROUPS[group_name]
    sample_docs, daily_candidates, timed_out = query_group_sample(
        client, group_name, start_time, end_time, seed, sample_size, stratum,
    )
    unique_accounts = {}
    for doc in sample_docs:
        unique_accounts.setdefault(doc["dedup_key"], doc)
    hard_accounts = [
        doc for doc in unique_accounts.values()
        if candidate_has_direct_signal(doc, labels)
    ]
    random.Random(seed).shuffle(hard_accounts)
    judged_accounts = hard_accounts[:max_judge]
    judged_results = judge_accounts(judged_accounts, workers) if judged_accounts else []

    accepted_ids = set()
    detail_rows = []
    for doc, result in judged_results:
        target_items = [
            item for item in result.get("identities", [])
            if item.get("standard_identity") in labels
        ]
        if target_items:
            accepted_ids.add(doc["dedup_key"])
        for item in target_items:
            row = _make_row(doc, item)
            row["sample_query_group"] = group_name
            row["sample_stratum"] = "账号名" if stratum == "profile" else "正文"
            detail_rows.append(row)

    sample_doc_count = len(sample_docs)
    hard_account_ids = set(doc["dedup_key"] for doc in hard_accounts)
    hard_sample_docs = sum(
        1 for doc in sample_docs if doc["dedup_key"] in hard_account_ids
    )
    hard_doc_rate = (
        float(hard_sample_docs) / sample_doc_count if sample_doc_count else 0.0
    )
    judged_count = len(judged_results)
    accepted_count = len(accepted_ids)
    model_precision = float(accepted_count) / judged_count if judged_count else 0.0
    effective_rate = hard_doc_rate * model_precision
    precision_low, precision_high = _wilson_interval(accepted_count, judged_count)
    effective_low = hard_doc_rate * precision_low
    effective_high = hard_doc_rate * precision_high
    candidate_posts = sum(item["candidate_posts"] for item in daily_candidates)

    return {
        "stratum": stratum,
        "candidate_posts": candidate_posts,
        "sample_posts": sample_doc_count,
        "sample_unique_accounts": len(unique_accounts),
        "hard_pass_accounts": len(hard_accounts),
        "hard_sample_docs": hard_sample_docs,
        "judged_accounts": judged_count,
        "accepted_accounts": accepted_count,
        "hard_doc_rate": hard_doc_rate,
        "model_precision": model_precision,
        "effective_rate": effective_rate,
        "effective_low": effective_low,
        "effective_high": effective_high,
        "estimated_posts": int(round(candidate_posts * effective_rate)),
        "estimated_low": int(round(candidate_posts * effective_low)),
        "estimated_high": int(round(candidate_posts * effective_high)),
        "daily_candidates": daily_candidates,
        "details": detail_rows,
        "timed_out": timed_out,
    }


def process_group(client, group_name, start_time, end_time, sample_size,
                  max_judge, workers, seed):
    labels = IDENTITY_GROUPS[group_name]
    profile = _process_stratum(
        client, group_name, start_time, end_time, sample_size,
        max_judge, workers, seed, "profile",
    )
    time.sleep(0.3)
    content = _process_stratum(
        client, group_name, start_time, end_time, sample_size,
        max_judge, workers, seed + 1, "content",
    )
    strata = [profile, content]
    candidate_posts = sum(item["candidate_posts"] for item in strata)
    sample_posts = sum(item["sample_posts"] for item in strata)
    hard_sample_docs = sum(item["hard_sample_docs"] for item in strata)
    judged_count = sum(item["judged_accounts"] for item in strata)
    accepted_count = sum(item["accepted_accounts"] for item in strata)
    estimated_posts = sum(item["estimated_posts"] for item in strata)
    estimated_low = sum(item["estimated_low"] for item in strata)
    estimated_high = sum(item["estimated_high"] for item in strata)

    distribution = {
        "identity_group": group_name,
        "standard_identities": "/".join(labels),
        "candidate_posts": candidate_posts,
        "profile_candidate_posts": profile["candidate_posts"],
        "content_candidate_posts": content["candidate_posts"],
        "sample_posts": sample_posts,
        "sample_unique_accounts": sum(item["sample_unique_accounts"] for item in strata),
        "hard_pass_accounts": sum(item["hard_pass_accounts"] for item in strata),
        "judged_accounts": judged_count,
        "accepted_accounts": accepted_count,
        "hard_pass_rate": float(hard_sample_docs) / sample_posts if sample_posts else 0.0,
        "model_precision": float(accepted_count) / judged_count if judged_count else 0.0,
        "effective_rate": float(estimated_posts) / candidate_posts if candidate_posts else 0.0,
        "estimated_identity_posts": estimated_posts,
        "estimated_profile_posts": profile["estimated_posts"],
        "estimated_content_posts": content["estimated_posts"],
        "estimated_low_95": estimated_low,
        "estimated_high_95": estimated_high,
        "timed_out": profile["timed_out"] or content["timed_out"],
    }

    by_date = {}
    for item in strata:
        for daily in item["daily_candidates"]:
            row = by_date.setdefault(daily["date"], {
                "date": daily["date"], "candidate_posts": 0,
                "estimated_identity_posts": 0,
                "estimated_low_95": 0, "estimated_high_95": 0,
            })
            row["candidate_posts"] += daily["candidate_posts"]
            row["estimated_identity_posts"] += int(round(
                daily["candidate_posts"] * item["effective_rate"]))
            row["estimated_low_95"] += int(round(
                daily["candidate_posts"] * item["effective_low"]))
            row["estimated_high_95"] += int(round(
                daily["candidate_posts"] * item["effective_high"]))
    daily_rows = []
    for date_value in sorted(by_date):
        row = by_date[date_value]
        row["identity_group"] = group_name
        daily_rows.append(row)
    return {
        "distribution": distribution,
        "daily": daily_rows,
        "details": profile["details"] + content["details"],
    }


def count_window(client, start_time, end_time):
    body = {
        "query": {
            "range": {
                "publishTime": {
                    "gte": start_time,
                    "lte": end_time,
                    "format": "yyyy-MM-dd HH:mm:ss",
                    "time_zone": "+08:00",
                }
            }
        }
    }
    return client.count(index=SOURCE_INDEX, body=body, request_timeout=90).get("count", 0)


def _save_checkpoint(path, state):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def _load_checkpoint(path, meta):
    if not os.path.exists(path):
        return {"meta": meta, "groups": {}}
    with open(path, "r", encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("meta") != meta:
        raise ValueError("检查点参数与本次运行不一致，请更换输出文件名")
    return state


def export_excel(state, output_path, total_window_posts, started_at, elapsed_seconds):
    group_results = state["groups"]
    distribution_rows = [
        group_results[group]["distribution"]
        for group in IDENTITY_GROUPS if group in group_results
    ]
    total_estimated = sum(row["estimated_identity_posts"] for row in distribution_rows)
    for row in distribution_rows:
        row["identity_distribution_share"] = (
            float(row["estimated_identity_posts"]) / total_estimated
            if total_estimated else 0.0
        )
        row["window_post_coverage"] = (
            float(row["estimated_identity_posts"]) / total_window_posts
            if total_window_posts else 0.0
        )

    daily_rows = []
    detail_rows = []
    for group in IDENTITY_GROUPS:
        result = group_results.get(group)
        if result:
            daily_rows.extend(result["daily"])
            detail_rows.extend(result["details"])

    summary = pd.DataFrame([
        ["源索引", SOURCE_INDEX],
        ["开始时间", state["meta"]["start_time"]],
        ["结束时间", state["meta"]["end_time"]],
        ["时间窗口预警帖子总数", total_window_posts],
        ["身份业务组数", len(distribution_rows)],
        ["每层随机样本上限", state["meta"]["sample_size"]],
        ["每层模型判断上限", state["meta"]["max_judge"]],
        ["运行开始", started_at],
        ["本次耗时秒", round(elapsed_seconds, 1)],
        ["是否全量scroll", "否"],
        ["是否写入media索引", "否"],
        ["统计方法", "账号名命中层与正文命中层互斥分层；各层候选总量 × 随机样本硬规则通过率 × 模型准确率"],
        ["统计口径", "估算身份相关预警帖子数；同一帖子可能具有多个身份，类别间可重叠"],
        ["注意", "估算值不是逐条全量模型判断；请结合95%区间和命中明细使用"],
    ], columns=["指标", "结果"])

    distribution_columns = {
        "identity_group": "身份业务组",
        "standard_identities": "标准身份",
        "candidate_posts": "时间窗候选帖子数",
        "profile_candidate_posts": "账号名层候选帖子数",
        "content_candidate_posts": "正文层候选帖子数",
        "sample_posts": "随机样本帖子数",
        "sample_unique_accounts": "样本唯一账号数",
        "hard_pass_accounts": "硬规则通过账号数",
        "judged_accounts": "模型判断账号数",
        "accepted_accounts": "模型命中账号数",
        "hard_pass_rate": "样本硬规则通过率",
        "model_precision": "模型命中率",
        "effective_rate": "综合有效率",
        "estimated_identity_posts": "估算身份帖子数",
        "estimated_profile_posts": "账号名层估算帖子数",
        "estimated_content_posts": "正文层估算帖子数",
        "estimated_low_95": "估算下限95%",
        "estimated_high_95": "估算上限95%",
        "identity_distribution_share": "身份分布占比",
        "window_post_coverage": "占全部预警帖子比例",
        "timed_out": "查询是否超时",
    }
    distribution = pd.DataFrame(distribution_rows).rename(columns=distribution_columns)
    if not distribution.empty:
        distribution = distribution[list(distribution_columns.values())]

    daily = pd.DataFrame(daily_rows).rename(columns={
        "date": "日期",
        "identity_group": "身份业务组",
        "candidate_posts": "候选帖子数",
        "estimated_identity_posts": "估算身份帖子数",
        "estimated_low_95": "估算下限95%",
        "estimated_high_95": "估算上限95%",
    })
    if daily.empty:
        pivot = pd.DataFrame()
    else:
        pivot = daily.pivot_table(
            index="日期", columns="身份业务组", values="估算身份帖子数",
            aggfunc="sum", fill_value=0,
        ).reset_index()

    detail = pd.DataFrame(detail_rows).rename(columns={
        "sample_query_group": "采样身份组",
        "sample_stratum": "采样层",
        "id": "id(平台|uid)",
        "platform": "平台",
        "uid": "账号id",
        "name": "账号名",
        "identity_group": "身份业务组",
        "standard_identity": "标准身份",
        "raw_identity": "原始细分身份",
        "evidence": "证据原文",
        "reason": "判断原因",
        "confidence": "置信度",
        "target_index": "目标media索引",
        "title": "标题",
        "content": "正文",
        "url": "url",
        "publish_time": "发布时间",
        "verified_reason": "认证原因",
        "description": "账号简介",
    })

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="运行汇总", index=False)
        distribution.to_excel(writer, sheet_name="身份分布", index=False)
        daily.to_excel(writer, sheet_name="每日分布", index=False)
        pivot.to_excel(writer, sheet_name="每日透视", index=False)
        detail.to_excel(writer, sheet_name="命中明细", index=False)


def run(output_path, start_time, end_time, sample_size=DEFAULT_SAMPLE_SIZE,
        max_judge=DEFAULT_MAX_JUDGE, workers=8):
    output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    checkpoint_path = os.path.splitext(output_path)[0] + ".checkpoint.json"
    meta = {
        "algorithm_version": 2,
        "source_index": SOURCE_INDEX,
        "start_time": start_time,
        "end_time": end_time,
        "sample_size": sample_size,
        "max_judge": max_judge,
    }
    state = _load_checkpoint(checkpoint_path, meta)
    client = get_client()
    started = time.time()
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    total_window_posts = count_window(client, start_time, end_time)
    print("时间窗口预警帖子数: {}".format(total_window_posts))

    for index, group_name in enumerate(IDENTITY_GROUPS):
        if group_name in state["groups"]:
            print("[{}/{}] {}：检查点已完成，跳过".format(
                index + 1, len(IDENTITY_GROUPS), group_name))
            continue
        seed = 20260720 + index * 101
        result = process_group(
            client, group_name, start_time, end_time, sample_size,
            max_judge, workers, seed,
        )
        state["groups"][group_name] = result
        _save_checkpoint(checkpoint_path, state)
        row = result["distribution"]
        print("[{}/{}] {}：候选{}，样本{}，硬筛{}，模型命中{}/{}, 估算{}".format(
            index + 1, len(IDENTITY_GROUPS), group_name,
            row["candidate_posts"], row["sample_unique_accounts"],
            row["hard_pass_accounts"], row["accepted_accounts"],
            row["judged_accounts"], row["estimated_identity_posts"],
        ))
        time.sleep(0.5)

    export_excel(
        state, output_path, total_window_posts, started_at, time.time() - started,
    )
    print("Excel: {}".format(output_path))
    print("检查点: {}".format(checkpoint_path))
    return state


def main():
    parser = argparse.ArgumentParser(description="按时间窗口估算人工预警身份分布")
    parser.add_argument("--start", default=DEFAULT_START, help="开始时间，东八区")
    parser.add_argument("--end", default=DEFAULT_END, help="结束时间，东八区")
    parser.add_argument(
        "--output",
        default=os.path.join(OUTPUT_DIR, "预警身份分布_20260720_至今.xlsx"),
        help="Excel输出路径",
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--max-judge", type=int, default=DEFAULT_MAX_JUDGE)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    run(
        args.output, args.start, args.end,
        sample_size=max(50, min(args.sample_size, 1000)),
        max_judge=max(1, args.max_judge), workers=max(1, args.workers),
    )


if __name__ == "__main__":
    main()

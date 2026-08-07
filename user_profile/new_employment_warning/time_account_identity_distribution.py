# -*- coding: utf-8 -*-
"""按时间窗口估算唯一账号的身份分布。

账号唯一键为“siteName|author_persona.id”。每个身份业务组先计算候选唯一账号数，
再按账号键哈希分区抽样；每个抽中账号只判断一次，避免高频发帖账号被重复加权。
不使用 scroll，不写入 media_*。
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
DEFAULT_SAMPLE_ACCOUNTS = 300
DEFAULT_MAX_JUDGE = 40
ACCOUNT_KEY_SCRIPT = (
    "doc['siteName.keyword'].value + '|' + doc['author_persona.id'].value"
)


def _base_filters(start_time, end_time):
    return [
        {"range": {"publishTime": {
            "gte": start_time, "lte": end_time,
            "format": "yyyy-MM-dd HH:mm:ss", "time_zone": "+08:00",
        }}},
        {"exists": {"field": "siteName.keyword"}},
        {"exists": {"field": "author_persona.id"}},
    ]


def _stratum_filters(group_name):
    aliases = []
    for identity in IDENTITY_GROUPS[group_name]:
        aliases.extend(IDENTITY_ALIASES[identity])
    profile_should = [
        {"match_phrase": {"author_persona.name": alias}} for alias in aliases
    ]
    content_should = []
    for alias in aliases:
        for field in ("title", "content"):
            content_should.append({"match_phrase": {field: alias}})
    profile = {"bool": {
        "should": profile_should, "minimum_should_match": 1,
    }}
    content = {"bool": {
        "should": content_should,
        "minimum_should_match": 1,
        "must_not": [{"bool": {
            "should": profile_should, "minimum_should_match": 1,
        }}],
    }}
    return {"profile": profile, "content": content}


def _cardinality_aggs():
    unique = {
        "cardinality": {
            "script": {"lang": "painless", "source": ACCOUNT_KEY_SCRIPT},
            "precision_threshold": 40000,
        }
    }
    return {
        "unique_accounts": unique,
        "by_day": {
            "date_histogram": {
                "field": "publishTime", "calendar_interval": "day",
                "format": "yyyy-MM-dd", "time_zone": "+08:00",
                "min_doc_count": 1,
            },
            "aggs": {
                "unique_accounts": {
                    "cardinality": {
                        "script": {"lang": "painless", "source": ACCOUNT_KEY_SCRIPT},
                        "precision_threshold": 40000,
                    }
                }
            },
        },
    }


def query_candidate_cardinality(client, group_name, start_time, end_time):
    strata = _stratum_filters(group_name)
    body = {
        "size": 0,
        "query": {"bool": {"filter": _base_filters(start_time, end_time)}},
        "aggs": {
            name: {"filter": query, "aggs": _cardinality_aggs()}
            for name, query in strata.items()
        },
    }
    response = client.search(
        index=SOURCE_INDEX, body=body, request_timeout=120,
        params={"request_cache": "true"},
    )
    result = {"timed_out": bool(response.get("timed_out"))}
    for name in ("profile", "content"):
        aggregation = response["aggregations"][name]
        result[name] = {
            "candidate_accounts": int(aggregation["unique_accounts"]["value"]),
            "daily": [{
                "date": bucket["key_as_string"],
                "candidate_accounts": int(bucket["unique_accounts"]["value"]),
            } for bucket in aggregation["by_day"]["buckets"]],
        }
    return result


def _sample_terms_agg(candidate_accounts, sample_accounts, seed, top_hits_size):
    partitions = max(1, int(candidate_accounts / sample_accounts))
    partition = seed % partitions
    return {
        "terms": {
            "script": {"lang": "painless", "source": ACCOUNT_KEY_SCRIPT},
            "include": {"partition": partition, "num_partitions": partitions},
            "size": sample_accounts * 3,
        },
        "aggs": {
            "posts": {
                "top_hits": {
                    "size": top_hits_size,
                    "_source": SOURCE_FIELDS,
                }
            }
        },
    }


def query_account_samples(client, group_name, start_time, end_time,
                          cardinality, sample_accounts, seed):
    strata_filters = _stratum_filters(group_name)
    aggs = {}
    for offset, name in enumerate(("profile", "content")):
        candidate_count = cardinality[name]["candidate_accounts"]
        if not candidate_count:
            continue
        aggs[name] = {
            "filter": strata_filters[name],
            "aggs": {
                "accounts": _sample_terms_agg(
                    candidate_count, sample_accounts, seed + offset,
                    1 if name == "profile" else 3,
                )
            },
        }
    body = {
        "size": 0,
        "query": {"bool": {"filter": _base_filters(start_time, end_time)}},
        "aggs": aggs,
    }
    response = client.search(index=SOURCE_INDEX, body=body, request_timeout=120)
    output = {"timed_out": bool(response.get("timed_out"))}
    labels = IDENTITY_GROUPS[group_name]
    for name in ("profile", "content"):
        accounts = []
        truncated = 0
        if name in response.get("aggregations", {}):
            terms = response["aggregations"][name]["accounts"]
            truncated = int(terms.get("sum_other_doc_count", 0))
            for bucket in terms.get("buckets", []):
                docs = []
                for hit in bucket["posts"]["hits"]["hits"]:
                    doc = _flatten_hit(hit)
                    for field in ("name", "title", "content", "verified_reason", "description"):
                        value = doc.get(field, "")
                        doc[field] = " ".join(str(x) for x in value) if isinstance(value, list) else str(value or "")
                    doc["dedup_key"] = bucket["key"]
                    docs.append(doc)
                selected = next(
                    (doc for doc in docs if candidate_has_direct_signal(doc, labels)),
                    docs[0] if docs else None,
                )
                if selected:
                    accounts.append(selected)
        output[name] = {"accounts": accounts, "truncated_buckets": truncated}
    return output


def _judge_doc(doc):
    result = judge_general_identity(
        doc["title"], doc["content"], doc["name"],
        doc.get("verified_reason", ""), doc.get("description", ""),
        doc.get("verified", ""), doc.get("verified_type", ""),
        doc.get("platform", ""),
    )
    return doc, result


def judge_accounts(accounts, workers):
    output = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_judge_doc, doc) for doc in accounts]
        for future in as_completed(futures):
            output.append(future.result())
    return output


def _wilson_interval(successes, total, z=1.96):
    if total <= 0:
        return 0.0, 0.0
    rate = float(successes) / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    margin = z * math.sqrt((rate * (1.0 - rate) + z * z / (4.0 * total)) / total)
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


def _process_stratum(group_name, name, candidate_info, sample_info,
                      max_judge, workers, seed):
    labels = IDENTITY_GROUPS[group_name]
    sample_accounts = sample_info["accounts"]
    hard_accounts = [
        doc for doc in sample_accounts if candidate_has_direct_signal(doc, labels)
    ]
    random.Random(seed).shuffle(hard_accounts)
    judged = judge_accounts(hard_accounts[:max_judge], workers) if hard_accounts else []
    accepted_ids = set()
    details = []
    for doc, result in judged:
        items = [
            item for item in result.get("identities", [])
            if item.get("standard_identity") in labels
        ]
        if items:
            accepted_ids.add(doc["dedup_key"])
        for item in items:
            row = _make_row(doc, item)
            row["sample_query_group"] = group_name
            row["sample_stratum"] = "账号名" if name == "profile" else "正文"
            details.append(row)

    sample_count = len(sample_accounts)
    hard_rate = float(len(hard_accounts)) / sample_count if sample_count else 0.0
    judged_count = len(judged)
    accepted_count = len(accepted_ids)
    model_precision = float(accepted_count) / judged_count if judged_count else 0.0
    effective_rate = hard_rate * model_precision
    precision_low, precision_high = _wilson_interval(accepted_count, judged_count)
    effective_low = hard_rate * precision_low
    effective_high = hard_rate * precision_high
    candidate_accounts = candidate_info["candidate_accounts"]
    return {
        "name": name,
        "candidate_accounts": candidate_accounts,
        "sample_accounts": sample_count,
        "hard_pass_accounts": len(hard_accounts),
        "judged_accounts": judged_count,
        "accepted_accounts": accepted_count,
        "hard_pass_rate": hard_rate,
        "model_precision": model_precision,
        "effective_rate": effective_rate,
        "effective_low": effective_low,
        "effective_high": effective_high,
        "estimated_accounts": int(round(candidate_accounts * effective_rate)),
        "estimated_low": int(round(candidate_accounts * effective_low)),
        "estimated_high": int(round(candidate_accounts * effective_high)),
        "daily": candidate_info["daily"],
        "details": details,
        "truncated_buckets": sample_info["truncated_buckets"],
    }


def process_group(client, group_name, start_time, end_time,
                  sample_accounts, max_judge, workers, seed):
    cardinality = query_candidate_cardinality(
        client, group_name, start_time, end_time,
    )
    time.sleep(0.3)
    samples = query_account_samples(
        client, group_name, start_time, end_time,
        cardinality, sample_accounts, seed,
    )
    strata = []
    for offset, name in enumerate(("profile", "content")):
        strata.append(_process_stratum(
            group_name, name, cardinality[name], samples[name],
            max_judge, workers, seed + offset,
        ))

    candidate_total = sum(item["candidate_accounts"] for item in strata)
    estimated_total = sum(item["estimated_accounts"] for item in strata)
    sample_total = sum(item["sample_accounts"] for item in strata)
    hard_total = sum(item["hard_pass_accounts"] for item in strata)
    judged_total = sum(item["judged_accounts"] for item in strata)
    accepted_total = sum(item["accepted_accounts"] for item in strata)
    distribution = {
        "identity_group": group_name,
        "standard_identities": "/".join(IDENTITY_GROUPS[group_name]),
        "candidate_accounts": candidate_total,
        "profile_candidate_accounts": strata[0]["candidate_accounts"],
        "content_candidate_accounts": strata[1]["candidate_accounts"],
        "sample_accounts": sample_total,
        "hard_pass_accounts": hard_total,
        "judged_accounts": judged_total,
        "accepted_accounts": accepted_total,
        "hard_pass_rate": float(hard_total) / sample_total if sample_total else 0.0,
        "model_precision": float(accepted_total) / judged_total if judged_total else 0.0,
        "effective_rate": float(estimated_total) / candidate_total if candidate_total else 0.0,
        "estimated_identity_accounts": estimated_total,
        "estimated_profile_accounts": strata[0]["estimated_accounts"],
        "estimated_content_accounts": strata[1]["estimated_accounts"],
        "estimated_low_95": sum(item["estimated_low"] for item in strata),
        "estimated_high_95": sum(item["estimated_high"] for item in strata),
        "sample_truncated_buckets": sum(item["truncated_buckets"] for item in strata),
        "timed_out": cardinality["timed_out"] or samples["timed_out"],
    }

    by_date = {}
    for item in strata:
        for daily in item["daily"]:
            row = by_date.setdefault(daily["date"], {
                "date": daily["date"], "candidate_accounts": 0,
                "estimated_identity_accounts": 0,
                "estimated_low_95": 0, "estimated_high_95": 0,
            })
            row["candidate_accounts"] += daily["candidate_accounts"]
            row["estimated_identity_accounts"] += int(round(
                daily["candidate_accounts"] * item["effective_rate"]))
            row["estimated_low_95"] += int(round(
                daily["candidate_accounts"] * item["effective_low"]))
            row["estimated_high_95"] += int(round(
                daily["candidate_accounts"] * item["effective_high"]))
    daily_rows = []
    for date_value in sorted(by_date):
        row = by_date[date_value]
        row["identity_group"] = group_name
        daily_rows.append(row)
    return {
        "distribution": distribution,
        "daily": daily_rows,
        "details": strata[0]["details"] + strata[1]["details"],
    }


def count_window(client, start_time, end_time):
    valid_filter = {"bool": {"filter": [
        {"exists": {"field": "siteName.keyword"}},
        {"exists": {"field": "author_persona.id"}},
    ]}}
    body = {
        "size": 0,
        "query": {"bool": {"filter": _base_filters(start_time, end_time)[:1]}},
        "aggs": {
            "all_docs": {"filter": {"match_all": {}}},
            "valid_docs": {
                "filter": valid_filter,
                "aggs": {
                    "unique_accounts": {
                        "cardinality": {
                            "script": {"lang": "painless", "source": ACCOUNT_KEY_SCRIPT},
                            "precision_threshold": 40000,
                        }
                    }
                },
            },
        },
    }
    response = client.search(
        index=SOURCE_INDEX, body=body, request_timeout=120,
        params={"request_cache": "true"},
    )
    return {
        "posts": int(response["aggregations"]["all_docs"]["doc_count"]),
        "valid_posts": int(response["aggregations"]["valid_docs"]["doc_count"]),
        "unique_accounts": int(
            response["aggregations"]["valid_docs"]["unique_accounts"]["value"]),
        "timed_out": bool(response.get("timed_out")),
    }


def _save_checkpoint(path, state):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def _load_checkpoint(path, meta):
    if not os.path.exists(path):
        return {"meta": meta, "groups": {}}
    with open(path, "r", encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("meta") != meta:
        raise ValueError("检查点参数不一致，请更换输出文件名")
    return state


def export_excel(state, output_path, window_stats, started_at, elapsed_seconds):
    group_results = state["groups"]
    distribution_rows = [
        group_results[group]["distribution"]
        for group in IDENTITY_GROUPS if group in group_results
    ]
    estimated_total = sum(
        row["estimated_identity_accounts"] for row in distribution_rows)
    for row in distribution_rows:
        row["identity_distribution_share"] = (
            float(row["estimated_identity_accounts"]) / estimated_total
            if estimated_total else 0.0)
        row["all_account_coverage"] = (
            float(row["estimated_identity_accounts"]) / window_stats["unique_accounts"]
            if window_stats["unique_accounts"] else 0.0)

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
        ["时间窗口帖子总数", window_stats["posts"]],
        ["具有平台和账号ID的帖子数", window_stats["valid_posts"]],
        ["平台+账号ID唯一账号数（近似）", window_stats["unique_accounts"]],
        ["身份业务组数", len(distribution_rows)],
        ["每层目标抽样账号数", state["meta"]["sample_accounts"]],
        ["每层模型判断上限", state["meta"]["max_judge"]],
        ["运行开始", started_at],
        ["本次耗时秒", round(elapsed_seconds, 1)],
        ["是否全量scroll", "否"],
        ["是否写入media索引", "否"],
        ["去重键", "siteName|author_persona.id"],
        ["抽样方法", "账号键哈希分区抽样；一个账号最多判断一次"],
        ["统计方法", "候选唯一账号数 × 样本硬规则通过率 × 模型命中率"],
        ["统计口径", "身份账号估算数；一个账号可拥有多个身份，因此类别允许重叠"],
        ["注意", "唯一账号数和身份数使用高精度cardinality/抽样估算，并非逐账号全量模型判断"],
    ], columns=["指标", "结果"])

    distribution_columns = {
        "identity_group": "身份业务组",
        "standard_identities": "标准身份",
        "candidate_accounts": "候选唯一账号数",
        "profile_candidate_accounts": "账号名层候选账号数",
        "content_candidate_accounts": "正文层候选账号数",
        "sample_accounts": "哈希抽样账号数",
        "hard_pass_accounts": "硬规则通过账号数",
        "judged_accounts": "模型判断账号数",
        "accepted_accounts": "模型命中账号数",
        "hard_pass_rate": "样本硬规则通过率",
        "model_precision": "模型命中率",
        "effective_rate": "综合有效率",
        "estimated_identity_accounts": "估算身份账号数",
        "estimated_profile_accounts": "账号名层估算账号数",
        "estimated_content_accounts": "正文层估算账号数",
        "estimated_low_95": "估算下限95%",
        "estimated_high_95": "估算上限95%",
        "identity_distribution_share": "身份分布占比",
        "all_account_coverage": "占全部唯一账号比例",
        "sample_truncated_buckets": "抽样截断桶数",
        "timed_out": "查询是否超时",
    }
    distribution = pd.DataFrame(distribution_rows).rename(columns=distribution_columns)
    if not distribution.empty:
        distribution = distribution[list(distribution_columns.values())]

    daily = pd.DataFrame(daily_rows).rename(columns={
        "date": "日期", "identity_group": "身份业务组",
        "candidate_accounts": "候选活跃账号数",
        "estimated_identity_accounts": "估算身份活跃账号数",
        "estimated_low_95": "估算下限95%",
        "estimated_high_95": "估算上限95%",
    })
    if daily.empty:
        pivot = pd.DataFrame()
    else:
        pivot = daily.pivot_table(
            index="日期", columns="身份业务组", values="估算身份活跃账号数",
            aggfunc="sum", fill_value=0,
        ).reset_index()

    detail = pd.DataFrame(detail_rows).rename(columns={
        "sample_query_group": "采样身份组",
        "sample_stratum": "采样层",
        "id": "id(平台|uid)", "platform": "平台", "uid": "账号id",
        "name": "账号名", "identity_group": "身份业务组",
        "standard_identity": "标准身份", "raw_identity": "原始细分身份",
        "evidence": "证据原文", "reason": "判断原因", "confidence": "置信度",
        "target_index": "目标media索引", "title": "标题", "content": "正文",
        "url": "url", "publish_time": "发布时间",
        "verified_reason": "认证原因", "description": "账号简介",
    })
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="运行汇总", index=False)
        distribution.to_excel(writer, sheet_name="账号身份分布", index=False)
        daily.to_excel(writer, sheet_name="每日活跃账号", index=False)
        pivot.to_excel(writer, sheet_name="每日账号透视", index=False)
        detail.to_excel(writer, sheet_name="抽样命中明细", index=False)


def run(output_path, start_time, end_time, sample_accounts=DEFAULT_SAMPLE_ACCOUNTS,
        max_judge=DEFAULT_MAX_JUDGE, workers=8):
    output_path = os.path.abspath(output_path)
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))
    checkpoint_path = os.path.splitext(output_path)[0] + ".checkpoint.json"
    meta = {
        "algorithm_version": 1,
        "source_index": SOURCE_INDEX,
        "start_time": start_time,
        "end_time": end_time,
        "sample_accounts": sample_accounts,
        "max_judge": max_judge,
    }
    state = _load_checkpoint(checkpoint_path, meta)
    client = get_client()
    started = time.time()
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    window_stats = count_window(client, start_time, end_time)
    print("帖子数:{}，唯一账号约:{}".format(
        window_stats["posts"], window_stats["unique_accounts"]))

    for index, group_name in enumerate(IDENTITY_GROUPS):
        if group_name in state["groups"]:
            print("[{}/{}] {}：检查点已完成".format(
                index + 1, len(IDENTITY_GROUPS), group_name))
            continue
        result = process_group(
            client, group_name, start_time, end_time,
            sample_accounts, max_judge, workers, 20260720 + index * 101,
        )
        state["groups"][group_name] = result
        _save_checkpoint(checkpoint_path, state)
        row = result["distribution"]
        print("[{}/{}] {}：候选账号{}，抽样{}，命中{}/{}, 估算账号{}".format(
            index + 1, len(IDENTITY_GROUPS), group_name,
            row["candidate_accounts"], row["sample_accounts"],
            row["accepted_accounts"], row["judged_accounts"],
            row["estimated_identity_accounts"],
        ))
        time.sleep(0.5)

    export_excel(state, output_path, window_stats, started_at, time.time() - started)
    print("Excel: {}".format(output_path))
    print("检查点: {}".format(checkpoint_path))
    return state


def main():
    parser = argparse.ArgumentParser(description="按时间窗口估算唯一账号身份分布")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument(
        "--output",
        default=os.path.join(OUTPUT_DIR, "预警账号身份分布_20260720_至今.xlsx"),
    )
    parser.add_argument("--sample-accounts", type=int, default=DEFAULT_SAMPLE_ACCOUNTS)
    parser.add_argument("--max-judge", type=int, default=DEFAULT_MAX_JUDGE)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    run(
        args.output, args.start, args.end,
        sample_accounts=max(50, min(args.sample_accounts, 1000)),
        max_judge=max(1, args.max_judge), workers=max(1, args.workers),
    )


if __name__ == "__main__":
    main()

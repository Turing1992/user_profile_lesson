# -*- coding: utf-8 -*-
"""按时间窗口估算账号唯一主身份分布。

所有身份词构成一个统一候选池，账号按“平台|账号ID”去重并哈希抽样。
每个抽样账号只判断一次；多身份按固定业务优先级选出唯一主身份。
"""
import argparse
import json
import math
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from new_employment_warning.config import OUTPUT_DIR, SOURCE_INDEX
from new_employment_warning.general_judge import (
    ALLOWED_IDENTITIES,
    IDENTITY_ALIASES,
    IDENTITY_GROUPS,
    candidate_has_direct_signal,
    is_organization_account,
    judge_general_identity,
)
from new_employment_warning.scan import SOURCE_FIELDS, _flatten_hit, get_client
from new_employment_warning.time_account_identity_distribution import (
    ACCOUNT_KEY_SCRIPT,
    DEFAULT_END,
    DEFAULT_START,
    _base_filters,
    count_window,
)


# 当前具体职业优先；宽泛职业/社会角色其次；年龄身份最后。
PRIMARY_PRIORITY = [
    "医护人员", "教师", "律师", "警察", "公务员", "事业单位工作人员",
    "外卖员", "快递员", "网约车司机", "货车司机", "家政服务人员",
    "餐饮从业者", "维修人员", "农民", "牧民", "工人", "退役军人",
    "学生", "家长", "老人",
]
PRIORITY_INDEX = {identity: index for index, identity in enumerate(PRIMARY_PRIORITY)}
GROUP_BY_IDENTITY = {}
for _group, _identities in IDENTITY_GROUPS.items():
    for _identity in _identities:
        GROUP_BY_IDENTITY[_identity] = _group
OTHER_GROUP = "其他/无明确身份"


def _all_aliases():
    values = []
    seen = set()
    for identity in PRIMARY_PRIORITY:
        for alias in IDENTITY_ALIASES[identity]:
            if alias not in seen:
                seen.add(alias)
                values.append(alias)
    return values


def _union_identity_query():
    should = []
    for alias in _all_aliases():
        for field in ("author_persona.name", "title", "content"):
            should.append({"match_phrase": {field: alias}})
    return {"bool": {"should": should, "minimum_should_match": 1}}


def query_candidate_count(client, start_time, end_time):
    body = {
        "size": 0,
        "query": {"bool": {
            "filter": _base_filters(start_time, end_time) + [_union_identity_query()],
        }},
        "aggs": {
            "unique_accounts": {
                "cardinality": {
                    "script": {"lang": "painless", "source": ACCOUNT_KEY_SCRIPT},
                    "precision_threshold": 40000,
                }
            }
        },
    }
    response = client.search(
        index=SOURCE_INDEX, body=body, request_timeout=180,
        params={"request_cache": "true"},
    )
    return {
        "candidate_accounts": int(response["aggregations"]["unique_accounts"]["value"]),
        "timed_out": bool(response.get("timed_out")),
    }


def _normalize_hit(hit, account_key):
    doc = _flatten_hit(hit)
    for field in ("name", "title", "content", "verified_reason", "description"):
        value = doc.get(field, "")
        doc[field] = " ".join(str(x) for x in value) if isinstance(value, list) else str(value or "")
    doc["dedup_key"] = account_key
    return doc


def query_account_sample(client, start_time, end_time, candidate_accounts,
                         sample_accounts, seed):
    partitions = max(1, int(candidate_accounts / sample_accounts))
    body = {
        "size": 0,
        "query": {"bool": {
            "filter": _base_filters(start_time, end_time) + [_union_identity_query()],
        }},
        "aggs": {
            "accounts": {
                "terms": {
                    "script": {"lang": "painless", "source": ACCOUNT_KEY_SCRIPT},
                    "include": {
                        "partition": seed % partitions,
                        "num_partitions": partitions,
                    },
                    "size": sample_accounts * 2,
                },
                "aggs": {
                    "posts": {
                        "top_hits": {"size": 1, "_source": SOURCE_FIELDS}
                    }
                },
            }
        },
    }
    response = client.search(index=SOURCE_INDEX, body=body, request_timeout=180)
    terms = response["aggregations"]["accounts"]
    accounts = []
    for bucket in terms.get("buckets", []):
        docs = [
            _normalize_hit(hit, bucket["key"])
            for hit in bucket["posts"]["hits"]["hits"]
        ]
        selected = next(
            (doc for doc in docs if candidate_has_direct_signal(doc, ALLOWED_IDENTITIES)),
            docs[0] if docs else None,
        )
        if selected:
            accounts.append(selected)
    return {
        "accounts": accounts,
        "truncated_buckets": int(terms.get("sum_other_doc_count", 0)),
        "timed_out": bool(response.get("timed_out")),
        "partitions": partitions,
    }


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


def resolve_primary_identity(items):
    valid = [
        item for item in items
        if item.get("standard_identity") in PRIORITY_INDEX
    ]
    if not valid:
        return None
    return min(valid, key=lambda item: PRIORITY_INDEX[item["standard_identity"]])


def _wilson_interval(successes, total, z=1.96):
    if total <= 0:
        return 0.0, 0.0
    rate = float(successes) / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    margin = z * math.sqrt((rate * (1.0 - rate) + z * z / (4.0 * total)) / total)
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


def classify_sample(sample, candidate_accounts, total_accounts,
                    max_judge, workers, seed):
    accounts = sample["accounts"]
    official_count = sum(1 for doc in accounts if is_organization_account(doc))
    hard_accounts = [
        doc for doc in accounts if candidate_has_direct_signal(doc, ALLOWED_IDENTITIES)
    ]
    random.Random(seed).shuffle(hard_accounts)
    judged_docs = hard_accounts[:max_judge]
    judged = judge_accounts(judged_docs, workers) if judged_docs else []

    label_counts = {group: 0 for group in IDENTITY_GROUPS}
    audit_rows = []
    for doc, result in judged:
        primary = resolve_primary_identity(result.get("identities", []))
        if primary:
            standard_identity = primary["standard_identity"]
            group = GROUP_BY_IDENTITY[standard_identity]
            label_counts[group] += 1
            evidence = primary.get("evidence", "")
            reason = primary.get("reason", "")
            raw_identity = primary.get("raw_identity", standard_identity)
        else:
            standard_identity = OTHER_GROUP
            group = OTHER_GROUP
            evidence = ""
            reason = result.get("log", "未通过唯一身份校验")
            raw_identity = ""
        audit_rows.append({
            "id": doc["dedup_key"], "platform": doc.get("platform", ""),
            "uid": doc.get("uid", ""), "name": doc.get("name", ""),
            "verified": doc.get("verified", ""),
            "verified_type": doc.get("verified_type", ""),
            "verified_reason": doc.get("verified_reason", ""),
            "description": doc.get("description", ""),
            "unique_identity_group": group,
            "standard_identity": standard_identity,
            "raw_identity": raw_identity,
            "evidence": evidence, "reason": reason,
            "title": doc.get("title", ""), "content": doc.get("content", ""),
            "url": doc.get("url", ""), "publish_time": doc.get("publish_time", ""),
        })

    sample_count = len(accounts)
    hard_count = len(hard_accounts)
    judged_count = len(judged)
    hard_rate = float(hard_count) / sample_count if sample_count else 0.0
    rows = []
    estimated_target_total = 0
    bounds = {}
    for group in IDENTITY_GROUPS:
        successes = label_counts[group]
        model_share = float(successes) / judged_count if judged_count else 0.0
        effective_rate = hard_rate * model_share
        estimated = int(round(candidate_accounts * effective_rate))
        low_share, high_share = _wilson_interval(successes, judged_count)
        low = int(round(candidate_accounts * hard_rate * low_share))
        high = int(round(candidate_accounts * hard_rate * high_share))
        estimated_target_total += estimated
        bounds[group] = (low, high)
        rows.append({
            "identity_group": group,
            "standard_identities": "/".join(IDENTITY_GROUPS[group]),
            "sample_judged_accounts": judged_count,
            "sample_identity_accounts": successes,
            "estimated_unique_accounts": estimated,
            "estimated_low_95": low,
            "estimated_high_95": high,
        })

    other_estimated = max(0, total_accounts - estimated_target_total)
    other_low = max(0, total_accounts - sum(high for _, high in bounds.values()))
    other_high = max(0, total_accounts - sum(low for low, _ in bounds.values()))
    rows.append({
        "identity_group": OTHER_GROUP,
        "standard_identities": OTHER_GROUP,
        "sample_judged_accounts": judged_count,
        "sample_identity_accounts": judged_count - sum(label_counts.values()),
        "estimated_unique_accounts": other_estimated,
        "estimated_low_95": other_low,
        "estimated_high_95": other_high,
    })
    return rows, audit_rows, {
        "sample_accounts": sample_count,
        "official_accounts": official_count,
        "hard_pass_accounts": hard_count,
        "judged_accounts": judged_count,
        "hard_pass_rate": hard_rate,
    }


def export_excel(output_path, rows, audit_rows, summary_stats):
    identified_total = sum(
        row["estimated_unique_accounts"] for row in rows
        if row["identity_group"] != OTHER_GROUP
    )
    for row in rows:
        row["all_account_share"] = (
            float(row["estimated_unique_accounts"]) / summary_stats["unique_accounts"]
            if summary_stats["unique_accounts"] else 0.0
        )
        row["identified_share"] = (
            float(row["estimated_unique_accounts"]) / identified_total
            if identified_total and row["identity_group"] != OTHER_GROUP else 0.0
        )
    distribution = pd.DataFrame(rows).rename(columns={
        "identity_group": "唯一身份",
        "standard_identities": "包含标准身份",
        "sample_judged_accounts": "模型判断样本账号数",
        "sample_identity_accounts": "样本命中账号数",
        "estimated_unique_accounts": "估算唯一账号数",
        "estimated_low_95": "估算下限95%",
        "estimated_high_95": "估算上限95%",
        "all_account_share": "占全部账号比例",
        "identified_share": "已识别身份内部占比",
    })
    audit = pd.DataFrame(audit_rows).rename(columns={
        "id": "id(平台|uid)", "platform": "平台", "uid": "账号id",
        "name": "账号名", "verified": "认证状态",
        "verified_type": "认证类型", "verified_reason": "认证说明",
        "description": "账号简介", "unique_identity_group": "唯一身份",
        "standard_identity": "标准身份", "raw_identity": "原始细分身份",
        "evidence": "证据原文", "reason": "判断原因",
        "title": "标题", "content": "正文", "url": "url",
        "publish_time": "发布时间",
    })
    summary = pd.DataFrame([
        ["源索引", SOURCE_INDEX],
        ["开始时间", summary_stats["start_time"]],
        ["结束时间", summary_stats["end_time"]],
        ["时间窗口帖子总数", summary_stats["posts"]],
        ["平台+账号ID唯一账号数（近似）", summary_stats["unique_accounts"]],
        ["身份词候选唯一账号数（近似）", summary_stats["candidate_accounts"]],
        ["统一候选池哈希抽样账号数", summary_stats["sample_accounts"]],
        ["样本中官号/机构账号过滤数", summary_stats["official_accounts"]],
        ["硬规则通过账号数", summary_stats["hard_pass_accounts"]],
        ["模型实际判断账号数", summary_stats["judged_accounts"]],
        ["估算有明确目标身份账号数", identified_total],
        ["估算其他/无明确身份账号数", summary_stats["unique_accounts"] - identified_total],
        ["唯一性规则", "每个账号只能选择一个主身份"],
        ["主身份优先级", " > ".join(PRIMARY_PRIORITY)],
        ["去重键", "siteName|author_persona.id"],
        ["抽样方式", "统一候选池按账号键哈希分区抽样"],
        ["是否全量scroll", "否"],
        ["是否写入media索引", "否"],
        ["查询是否超时", summary_stats["timed_out"]],
        ["抽样截断桶数", summary_stats["truncated_buckets"]],
    ], columns=["指标", "结果"])
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="运行汇总", index=False)
        distribution.to_excel(writer, sheet_name="唯一身份分布", index=False)
        audit.to_excel(writer, sheet_name="唯一身份抽样明细", index=False)


def run(output_path, start_time, end_time, sample_accounts=2000,
        max_judge=500, workers=8):
    output_path = os.path.abspath(output_path)
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))
    client = get_client()
    started = time.time()
    window = count_window(client, start_time, end_time)
    candidate = query_candidate_count(client, start_time, end_time)
    print("唯一账号约:{}，身份词候选账号约:{}".format(
        window["unique_accounts"], candidate["candidate_accounts"]))
    sample = query_account_sample(
        client, start_time, end_time, candidate["candidate_accounts"],
        sample_accounts, 20260720,
    )
    print("哈希抽样账号:{}，抽样截断:{}".format(
        len(sample["accounts"]), sample["truncated_buckets"]))
    rows, audit_rows, classification = classify_sample(
        sample, candidate["candidate_accounts"], window["unique_accounts"],
        max_judge, workers, 20260720,
    )
    stats = {
        "start_time": start_time, "end_time": end_time,
        "posts": window["posts"], "unique_accounts": window["unique_accounts"],
        "candidate_accounts": candidate["candidate_accounts"],
        "sample_accounts": classification["sample_accounts"],
        "official_accounts": classification["official_accounts"],
        "hard_pass_accounts": classification["hard_pass_accounts"],
        "judged_accounts": classification["judged_accounts"],
        "timed_out": window["timed_out"] or candidate["timed_out"] or sample["timed_out"],
        "truncated_buckets": sample["truncated_buckets"],
        "elapsed_seconds": round(time.time() - started, 1),
    }
    export_excel(output_path, rows, audit_rows, stats)
    state_path = os.path.splitext(output_path)[0] + ".json"
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump({"stats": stats, "distribution": rows, "audit": audit_rows},
                  handle, ensure_ascii=False, indent=2)
    print("模型判断账号:{}，Excel:{}".format(
        classification["judged_accounts"], output_path))
    return rows, stats


def main():
    parser = argparse.ArgumentParser(description="按时间窗口估算账号唯一主身份分布")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument(
        "--output",
        default=os.path.join(OUTPUT_DIR, "预警账号唯一身份分布_20260720_至今.xlsx"),
    )
    parser.add_argument("--sample-accounts", type=int, default=2000)
    parser.add_argument("--max-judge", type=int, default=500)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    run(
        args.output, args.start, args.end,
        sample_accounts=max(200, min(args.sample_accounts, 5000)),
        max_judge=max(1, args.max_judge), workers=max(1, args.workers),
    )


if __name__ == "__main__":
    main()

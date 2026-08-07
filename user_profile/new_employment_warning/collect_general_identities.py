# -*- coding: utf-8 -*-
"""从人工预警索引限量收集通用高置信身份并导出 Excel。

安全约束：关键词限量查询、terminate_after、无 scroll、模型前硬规则预筛；
只生成 JSONL/Excel，不更新 media_*。
"""
import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from new_employment_warning.config import OUTPUT_DIR, SITENAME_TO_MEDIA_INDEX, SOURCE_INDEX
from new_employment_warning.general_judge import (
    IDENTITY_ALIASES,
    IDENTITY_GROUPS,
    candidate_has_direct_signal,
    identity_evidence_has_direct_signal,
    judge_general_identity,
)
from new_employment_warning.scan import SOURCE_FIELDS, _flatten_hit, get_client


QUERY_SIZE = 300
JUDGE_BATCH = 40
DEFAULT_ROUNDS = 3

GROUP_BY_IDENTITY = {}
for _group_name, _labels in IDENTITY_GROUPS.items():
    for _label in _labels:
        GROUP_BY_IDENTITY[_label] = _group_name

DETAIL_COLUMNS = [
    ("id", "id(平台|uid)"),
    ("platform", "平台"),
    ("uid", "账号id"),
    ("name", "账号名"),
    ("identity_group", "身份业务组"),
    ("standard_identity", "标准身份"),
    ("raw_identity", "原始细分身份"),
    ("evidence", "证据原文"),
    ("reason", "判断原因"),
    ("confidence", "置信度"),
    ("target_index", "目标media索引"),
    ("title", "标题"),
    ("content", "正文"),
    ("url", "url"),
    ("publish_time", "发布时间"),
    ("verified", "认证状态"),
    ("verified_type", "认证类型"),
    ("verified_reason", "认证原因"),
    ("description", "账号简介"),
    ("人工复核", "人工复核"),
    ("是否建议入库", "是否建议入库"),
    ("复核备注", "复核备注"),
]


def _text(value):
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _normalize_doc(hit):
    doc = _flatten_hit(hit)
    for field in ("name", "title", "content", "verified_reason", "description"):
        doc[field] = _text(doc.get(field))
    doc["dedup_key"] = "{}|{}".format(doc.get("platform", ""), doc.get("uid", ""))
    return doc


def query_candidates(client, group_name, seed):
    """单次有界随机查询，不使用 scroll。"""
    labels = IDENTITY_GROUPS[group_name]
    aliases = []
    for identity in labels:
        aliases.extend(IDENTITY_ALIASES[identity])
    should = []
    for alias in aliases:
        for field in (
                "title", "content", "author_persona.name",
                "author_persona.description", "author_persona.verified_reason"):
            should.append({"match_phrase": {field: alias}})
    body = {
        "track_total_hits": False,
        "terminate_after": 50000,
        "query": {
            "function_score": {
                "query": {"bool": {"should": should, "minimum_should_match": 1}},
                "random_score": {"seed": seed, "field": "_seq_no"},
                "boost_mode": "replace",
            }
        },
    }
    response = client.search(
        index=SOURCE_INDEX,
        size=QUERY_SIZE,
        _source=SOURCE_FIELDS,
        body=body,
        request_timeout=60,
    )
    docs = []
    for hit in response.get("hits", {}).get("hits", []):
        doc = _normalize_doc(hit)
        if not doc["uid"] or not doc["platform"]:
            continue
        if candidate_has_direct_signal(doc, labels):
            docs.append(doc)
    return docs


def _judge_doc(doc):
    result = judge_general_identity(
        doc["title"], doc["content"], doc["name"],
        doc.get("verified_reason", ""), doc.get("description", ""),
        doc.get("verified", ""), doc.get("verified_type", ""),
        doc.get("platform", ""),
    )
    return doc, result


def judge_candidates(candidates, workers):
    judged = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_judge_doc, doc) for doc in candidates]
        for future in as_completed(futures):
            judged.append(future.result())
    return judged


def _make_row(doc, identity):
    standard_identity = identity["standard_identity"]
    return {
        "id": doc["dedup_key"],
        "platform": doc["platform"],
        "uid": doc["uid"],
        "name": doc["name"],
        "identity_group": GROUP_BY_IDENTITY[standard_identity],
        "standard_identity": standard_identity,
        "raw_identity": identity["raw_identity"],
        "evidence": identity["evidence"],
        "reason": identity["reason"],
        "confidence": identity["confidence"],
        "target_index": SITENAME_TO_MEDIA_INDEX.get(doc["platform"]),
        "title": doc["title"],
        "content": doc["content"],
        "url": doc.get("url", ""),
        "publish_time": doc.get("publish_time", ""),
        "verified": doc.get("verified", ""),
        "verified_type": doc.get("verified_type", ""),
        "verified_reason": doc.get("verified_reason", ""),
        "description": doc.get("description", ""),
        "人工复核": "",
        "是否建议入库": "",
        "复核备注": "",
    }


def _load_checkpoint(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _save_checkpoint(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def export_excel(rows, output_path, stats, per_group):
    keys = [key for key, _ in DETAIL_COLUMNS]
    headers = [header for _, header in DETAIL_COLUMNS]
    detail = pd.DataFrame(
        [[row.get(key, "") for key in keys] for row in rows],
        columns=headers,
    )
    category_rows = []
    for group_name in IDENTITY_GROUPS:
        group_rows = [row for row in rows if row.get("identity_group") == group_name]
        labels = sorted(set(row["standard_identity"] for row in group_rows))
        category_rows.append([
            group_name, "/".join(IDENTITY_GROUPS[group_name]), len(group_rows),
            len(set(row["id"] for row in group_rows)), "/".join(labels),
        ])
    categories = pd.DataFrame(category_rows, columns=[
        "身份业务组", "允许标准身份", "身份记录数", "账号数", "实际命中标准身份",
    ])
    summary = pd.DataFrame([
        ["源索引", SOURCE_INDEX],
        ["目标业务组数", len(IDENTITY_GROUPS)],
        ["每组目标账号数", per_group],
        ["实际身份记录数", len(rows)],
        ["实际唯一账号数", len(set(row["id"] for row in rows))],
        ["抽取方式", "身份词限量随机查询 + 硬规则预筛 + 严格模型判断 + 证据接地"],
        ["是否全量扫描", "否"],
        ["是否写入media索引", "否"],
        ["ES查询次数", stats["es_queries"]],
        ["ES返回候选数", stats["es_returned"]],
        ["硬规则预筛通过数", stats["prefiltered"]],
        ["模型判断账号数", stats["judged"]],
        ["耗时秒", stats["seconds"]],
    ], columns=["指标", "结果"])
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="运行汇总", index=False)
        categories.to_excel(writer, sheet_name="类别统计", index=False)
        detail.to_excel(writer, sheet_name="身份明细", index=False)


def run(output_path, groups=None, per_group=5, workers=8, rounds=DEFAULT_ROUNDS):
    groups = groups or list(IDENTITY_GROUPS.keys())
    unknown = [group for group in groups if group not in IDENTITY_GROUPS]
    if unknown:
        raise ValueError("未知业务组:{}".format(",".join(unknown)))
    output_path = os.path.abspath(output_path)
    checkpoint_path = os.path.splitext(output_path)[0] + ".jsonl"
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    rows = _load_checkpoint(checkpoint_path)
    resume_seed_offset = 10000 if rows else 0
    # 规则升级后重跑时，先剔除不再满足当前硬门槛的旧检查点记录。
    rows = [row for row in rows if identity_evidence_has_direct_signal(
        row.get("standard_identity", ""), row.get("evidence", ""),
        row.get("name", ""), row.get("verified_reason", ""),
        row.get("description", ""), row.get("verified", ""),
        row.get("verified_type", ""), row.get("platform", ""),
    )]
    row_keys = set((row["id"], row["standard_identity"]) for row in rows)
    judged_accounts = set(row["id"] for row in rows)
    stats = {"es_queries": 0, "es_returned": 0, "prefiltered": 0, "judged": 0}
    started = time.time()
    client = get_client()

    for group_index, group_name in enumerate(groups):
        current_accounts = set(
            row["id"] for row in rows if row.get("identity_group") == group_name
        )
        for round_index in range(rounds):
            if len(current_accounts) >= per_group:
                break
            seed = 20260722 + resume_seed_offset + group_index * 100 + round_index
            candidates = query_candidates(client, group_name, seed)
            stats["es_queries"] += 1
            stats["es_returned"] += len(candidates)
            fresh = [doc for doc in candidates if doc["dedup_key"] not in judged_accounts]
            random.Random(seed).shuffle(fresh)
            fresh = fresh[:JUDGE_BATCH]
            stats["prefiltered"] += len(fresh)
            stats["judged"] += len(fresh)
            for doc, result in judge_candidates(fresh, workers):
                judged_accounts.add(doc["dedup_key"])
                for identity in result.get("identities", []):
                    row = _make_row(doc, identity)
                    row_key = (row["id"], row["standard_identity"])
                    if row_key in row_keys:
                        continue
                    row_keys.add(row_key)
                    rows.append(row)
                    if row["identity_group"] == group_name:
                        current_accounts.add(row["id"])
            _save_checkpoint(checkpoint_path, rows)
            print("[{}] 第{}批：预筛{}，累计账号{}/{}".format(
                group_name, round_index + 1, len(fresh),
                len(current_accounts), per_group,
            ))

    stats["seconds"] = round(time.time() - started, 1)
    _save_checkpoint(checkpoint_path, rows)
    export_excel(rows, output_path, stats, per_group)
    print("完成：{}条身份记录，{}个账号".format(
        len(rows), len(set(row["id"] for row in rows))))
    print("Excel: {}".format(output_path))
    print("JSONL: {}".format(checkpoint_path))
    return rows


def main():
    default_name = "通用身份预警复核_{}.xlsx".format(time.strftime("%Y%m%d_%H%M%S"))
    parser = argparse.ArgumentParser(description="限量收集人工预警通用高置信身份")
    parser.add_argument(
        "--output", default=os.path.join(OUTPUT_DIR, default_name),
        help="Excel输出路径；同名JSONL用于断点续跑",
    )
    parser.add_argument(
        "--groups", default="",
        help="逗号分隔业务组；默认全部，例如：家长,医护人员,教师",
    )
    parser.add_argument("--per-group", type=int, default=5, help="每个业务组目标账号数")
    parser.add_argument("--workers", type=int, default=8, help="模型调用并发数")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help="每组最多限量查询轮数")
    args = parser.parse_args()
    groups = [item.strip() for item in args.groups.split(",") if item.strip()] or None
    run(
        args.output, groups=groups, per_group=max(1, args.per_group),
        workers=max(1, args.workers), rounds=max(1, args.rounds),
    )


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""从人工预警索引定向收集 100 条高置信新就业群体身份。

每类目标 25 条。ES 仅执行职业关键词过滤后的限量随机查询，不使用 scroll；
本地硬规则预筛后才调用模型，减少 ES 压力和模型消耗。
"""
import argparse
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from new_employment_warning.config import OUTPUT_DIR, SOURCE_INDEX
from new_employment_warning.scan import (
    EXCEL_COLUMNS, SOURCE_FIELDS, _flatten_hit, get_client, judge_account,
)

CATEGORY_TERMS = {
    "外卖员": ["外卖员", "外卖骑手", "外卖小哥", "跑外卖", "送外卖", "美团骑手", "饿了么骑手"],
    "网约车司机": ["网约车司机", "滴滴司机", "跑滴滴", "出租车司机", "的士司机", "滴滴车主"],
    "货车司机": ["货车司机", "卡车司机", "货运司机", "跑货运", "卡友", "半挂司机", "大车司机"],
    "快递员": ["快递员", "快递小哥", "快递骑手", "送快递", "派件员"],
}
FIRST_PERSON_ACTION = re.compile(
    r"(?:我|本人|咱们|我们).{0,16}(?:跑|送|接|拉|开|派|揽|运|卸|装|抢|配送|营运)"
)
TARGET_PER_CATEGORY = 25
QUERY_SIZE = 500
MAX_ROUNDS = 12            # 单类别最多有限批次；支持断点续跑，不全量扫描
JUDGE_BATCH = 120

def _text(value):
    if isinstance(value, list):
        return " ".join(str(x) for x in value)
    return str(value or "")


def _normalize_doc(doc):
    for field in ("name", "title", "content"):
        doc[field] = _text(doc.get(field))
    doc["dedup_key"] = "{}|{}".format(doc.get("platform", ""), doc.get("uid", ""))
    return doc


def _prefilter(doc, category):
    terms = CATEGORY_TERMS[category]
    name = doc["name"]
    text = "{} {} {}".format(name, doc["title"], doc["content"])
    name_has_label = any(term in name for term in terms)
    text_has_label = any(term in text for term in terms)
    return name_has_label or (text_has_label and bool(FIRST_PERSON_ACTION.search(text)))


def query_candidates(client, category, seed):
    should = []
    for term in CATEGORY_TERMS[category]:
        for field in ("title", "content", "author_persona.name"):
            should.append({"match_phrase": {field: term}})
    body = {
        "track_total_hits": False,
        "terminate_after": 100000,
        "query": {
            "function_score": {
                "query": {"bool": {"should": should, "minimum_should_match": 1}},
                "random_score": {"seed": seed, "field": "_seq_no"},
                "boost_mode": "replace",
            }
        },
    }
    response = client.search(
        index=SOURCE_INDEX, size=QUERY_SIZE, _source=SOURCE_FIELDS, body=body,
        request_timeout=60,
    )
    docs = []
    for hit in response["hits"]["hits"]:
        doc = _normalize_doc(_flatten_hit(hit))
        if doc["uid"] and doc["platform"] and _prefilter(doc, category):
            doc["candidate_category"] = category
            docs.append(doc)
    return docs


def judge_candidates(candidates, category, workers):
    accepted = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(judge_account, doc) for doc in candidates]
        for future in as_completed(futures):
            result = future.result()
            if result and result.get("community") == category:
                accepted.append(result)
    return accepted

def export_results(results, output_path, stats):
    keys = [key for key, _ in EXCEL_COLUMNS]
    headers = [header for _, header in EXCEL_COLUMNS]
    rows = [[result.get(key, "") for key in keys] for result in results]
    detail = pd.DataFrame(rows, columns=headers)
    summary = pd.DataFrame([
        ["源索引", SOURCE_INDEX],
        ["目标数量", 100],
        ["实际数量", len(results)],
        ["抽取方式", "职业关键词限量随机查询 + 本地硬规则预筛 + 严格模型判断"],
        ["是否全量扫描", "否"],
        ["ES查询次数", stats["es_queries"]],
        ["ES候选返回数", stats["es_returned"]],
        ["本地预筛通过数", stats["prefiltered"]],
        ["模型判断账号数", stats["judged"]],
        ["耗时秒", stats["seconds"]],
    ], columns=["指标", "结果"])
    category_rows = []
    for category in CATEGORY_TERMS:
        category_rows.append([category, sum(1 for row in results if row["community"] == category)])
    categories = pd.DataFrame(category_rows, columns=["身份类别", "数量"])
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="运行汇总", index=False)
        categories.to_excel(writer, sheet_name="类别统计", index=False)
        detail.to_excel(writer, sheet_name="身份明细", index=False)


def run(output_path, workers=16):
    client = get_client()
    jsonl_path = os.path.splitext(output_path)[0] + ".jsonl"
    selected = []
    if os.path.exists(jsonl_path):
        with open(jsonl_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    selected.append(json.loads(line))
        print("断点续跑：已加载 {} 条结果".format(len(selected)))

    selected_ids = set(result["id"] for result in selected)
    candidate_ids = set(selected_ids)
    stats = {"es_queries": 0, "es_returned": 0, "prefiltered": 0, "judged": 0}
    started = time.time()
    resume_seed_offset = 10000 if selected else 0

    for category_index, category in enumerate(CATEGORY_TERMS):
        category_hits = [row for row in selected if row.get("community") == category]
        for round_index in range(MAX_ROUNDS):
            if len(category_hits) >= TARGET_PER_CATEGORY:
                break
            seed = 20260722 + resume_seed_offset + category_index * 100 + round_index
            candidates = query_candidates(client, category, seed)
            stats["es_queries"] += 1
            stats["es_returned"] += QUERY_SIZE
            fresh = []
            for doc in candidates:
                doc_id = "{}|{}".format(doc["platform"], doc["uid"])
                if doc_id in candidate_ids or doc_id in selected_ids:
                    continue
                candidate_ids.add(doc_id)
                fresh.append(doc)
            random.Random(seed).shuffle(fresh)
            fresh = fresh[:JUDGE_BATCH]
            stats["prefiltered"] += len(fresh)
            stats["judged"] += len(fresh)
            accepted = judge_candidates(fresh, category, workers)
            for result in accepted:
                if result["id"] not in selected_ids:
                    selected_ids.add(result["id"])
                    category_hits.append(result)
                    selected.append(result)
                if len(category_hits) >= TARGET_PER_CATEGORY:
                    break
            print("[{}] 第{}批: 预筛{}，本批命中{}，累计{}/{}".format(
                category, round_index + 1, len(fresh), len(accepted),
                len(category_hits), TARGET_PER_CATEGORY,
            ))

    selected = selected[:len(CATEGORY_TERMS) * TARGET_PER_CATEGORY]
    stats["seconds"] = round(time.time() - started, 1)
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))
    with open(jsonl_path, "w", encoding="utf-8") as handle:
        for result in selected:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    export_results(selected, output_path, stats)
    print("\n完成: {} 条".format(len(selected)))
    print("Excel: {}".format(output_path))
    print("JSONL: {}".format(jsonl_path))
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return selected

def main():
    parser = argparse.ArgumentParser(description="定向收集100条高置信新就业群体身份")
    parser.add_argument(
        "--output",
        default=os.path.join(OUTPUT_DIR, "warning_identity_100.xlsx"),
        help="Excel 输出路径",
    )
    parser.add_argument("--workers", type=int, default=16, help="模型判断并发数")
    args = parser.parse_args()
    run(os.path.abspath(args.output), workers=args.workers)


if __name__ == "__main__":
    main()

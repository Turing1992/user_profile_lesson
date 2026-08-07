# -*- coding: utf-8 -*-
"""扫描人工预警索引，判断新就业群体身份。

流程：
1. scroll 扫描源索引 artificial_warning_push_2026
2. 抽取 siteName(平台) + author_persona.id(账号id) + name + title + content
3. 按 "平台|id" 去重（同一账号只判断一次）
4. 复用 judge.judge_identity 判断是否为新就业群体
5. 命中的账号解析出目标 media_* 索引，写入结果文件，供后续 update 使用

注意：本脚本只做"前置"——扫描 + 判断 + 去重 + 目标索引解析，
不执行对 media_* 的实际写入（更新逻辑后续再定）。
"""
import os
import json
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from opensearchpy import OpenSearch

from new_employment_warning.config import (
    ES_CONFIG,
    SOURCE_INDEX,
    SCAN_CONFIG,
    OUTPUT_DIR,
    SITENAME_TO_MEDIA_INDEX,
)
from new_employment_warning.judge import judge_identity


def get_client():
    # type: () -> OpenSearch
    """获取 OpenSearch 客户端。"""
    return OpenSearch(**ES_CONFIG)


SOURCE_FIELDS = ["url", "content", "title", "siteName", "publishTime", "author_persona"]


def _flatten_hit(h):
    """把 ES hit 转成精简账号帖文 dict。"""
    src = h.get("_source", {})
    persona = src.get("author_persona") or {}
    ip_region = persona.get("ip_region") or []
    if isinstance(ip_region, list):
        ip_region = ",".join(str(x) for x in ip_region)
    return {
        "platform": (src.get("siteName") or "").strip(),
        "uid": str(persona.get("id") or "").strip(),
        "name": (persona.get("name") or "").strip(),
        "title": src.get("title") or "",
        "content": src.get("content") or "",
        "url": src.get("url") or "",
        "publish_time": src.get("publishTime") or "",
        "verified": persona.get("verified", ""),
        "verified_type": persona.get("verified_type", ""),
        "verified_reason": persona.get("verified_reason", ""),
        "description": persona.get("description", ""),
        "gender": persona.get("gender", ""),
        "ip_region": ip_region,
    }


def iter_source_docs(client, max_docs=None, random_seed=None):
    """遍历源索引，yield 精简后的账号帖文。

    Args:
        client: OpenSearch 客户端。
        max_docs: 最多遍历的原始帖文数，None 表示全量。
        random_seed: 非 None 时启用随机采样（单次 search，size=max_docs，
            上限 10000），每次换 seed 得到不同批次，便于反复抽样测试。

    Yields:
        dict: 精简账号帖文。
    """
    # 随机采样模式：单次 search，适合测试不同批次
    if random_seed is not None:
        size = min(max_docs or 1000, 10000)
        resp = client.search(
            index=SOURCE_INDEX,
            size=size,
            _source=SOURCE_FIELDS,
            body={
                "query": {
                    "function_score": {
                        "query": {"match_all": {}},
                        "random_score": {"seed": random_seed, "field": "_seq_no"},
                    }
                }
            },
        )
        for h in resp["hits"]["hits"]:
            yield _flatten_hit(h)
        return

    # 全量模式：scroll 顺序遍历
    batch = SCAN_CONFIG["batch_size"]
    scroll_ttl = SCAN_CONFIG["scroll_ttl"]

    resp = client.search(
        index=SOURCE_INDEX,
        scroll=scroll_ttl,
        size=batch,
        _source=SOURCE_FIELDS,
        body={"query": {"match_all": {}}},
    )
    scroll_id = resp.get("_scroll_id")
    hits = resp["hits"]["hits"]
    seen = 0

    try:
        while hits:
            for h in hits:
                yield _flatten_hit(h)
                seen += 1
                if max_docs and seen >= max_docs:
                    return
            resp = client.scroll(scroll_id=scroll_id, scroll=scroll_ttl)
            scroll_id = resp.get("_scroll_id")
            hits = resp["hits"]["hits"]
    finally:
        if scroll_id:
            try:
                client.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass


def dedup_accounts(docs_iter):
    """按 "平台|id" 去重，同一账号只保留首条帖文。

    Args:
        docs_iter: iter_source_docs 产出的帖文迭代器。

    Returns:
        tuple(list, dict): (去重后的账号列表, 统计信息)。
    """
    seen = set()
    accounts = []
    total = 0
    no_id = 0
    for doc in docs_iter:
        total += 1
        if not doc["uid"] or not doc["platform"]:
            no_id += 1
            continue
        key = "{}|{}".format(doc["platform"], doc["uid"])
        if key in seen:
            continue
        seen.add(key)
        doc["dedup_key"] = key
        accounts.append(doc)
    stats = {
        "total_docs": total,
        "no_platform_or_id": no_id,
        "unique_accounts": len(accounts),
    }
    return accounts, stats


def judge_account(doc):
    """对单个去重后账号做身份判断，并解析目标 media 索引。

    Args:
        doc: 去重后的账号 dict。

    Returns:
        dict or None: 命中新就业群体则返回结果，否则 None。
    """
    result = judge_identity(
        title=doc["title"],
        content=doc["content"],
        name=doc["name"],
    )
    if not result.get("identity2"):
        return None

    target_index = SITENAME_TO_MEDIA_INDEX.get(doc["platform"])
    return {
        "id": doc["dedup_key"],          # 平台|uid，与 media_* 的 _id 规则一致
        "platform": doc["platform"],
        "uid": doc["uid"],
        "name": doc["name"],
        "community": result["identity2"],
        "identity": result["identity"],
        "evidence": result.get("evidence", ""),
        "log": result.get("log", ""),
        "target_index": target_index,    # None 表示 siteName 无对应 media 索引
        "title": doc["title"],
        "content": doc["content"],
        "url": doc["url"],
        "publish_time": doc.get("publish_time", ""),
        "verified": doc.get("verified", ""),
        "verified_type": doc.get("verified_type", ""),
        "gender": doc.get("gender", ""),
        "ip_region": doc.get("ip_region", ""),
    }


EXCEL_COLUMNS = [
    ("id", "id(平台|uid)"),
    ("platform", "平台"),
    ("uid", "账号id"),
    ("name", "账号名"),
    ("community", "判定群体"),
    ("identity", "身份大类"),
    ("evidence", "证据原文"),
    ("log", "判断原因"),
    ("target_index", "目标media索引"),
    ("title", "标题"),
    ("content", "正文"),
    ("url", "url"),
    ("publish_time", "发布时间"),
    ("verified", "认证"),
    ("verified_type", "认证类型"),
    ("gender", "性别"),
    ("ip_region", "IP归属"),
]


def export_excel(hits, excel_path):
    # type: (list, str) -> None
    """将命中结果导出为 Excel，包含全部字段。

    Args:
        hits: judge_account 产出的命中结果列表。
        excel_path: 输出 xlsx 路径。
    """
    import pandas as pd

    keys = [k for k, _ in EXCEL_COLUMNS]
    headers = [h for _, h in EXCEL_COLUMNS]
    rows = [[r.get(k, "") for k in keys] for r in hits]
    df = pd.DataFrame(rows, columns=headers)
    df.to_excel(excel_path, index=False)


def run(max_docs=None, output_path=None, random_seed=None):
    """执行完整扫描 + 判断 + 去重流程。

    Args:
        max_docs: 最多扫描原始帖文数，覆盖 config。
        output_path: 结果 JSONL 输出路径。
        random_seed: 非 None 时随机采样（测试不同批次用）。

    Returns:
        dict: 运行统计。
    """
    if max_docs is None:
        max_docs = SCAN_CONFIG.get("max_docs")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    if output_path is None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        tag = "rand{}_".format(random_seed) if random_seed is not None else ""
        output_path = os.path.join(OUTPUT_DIR, "hits_{}_{}{}.jsonl".format(SOURCE_INDEX, tag, ts))

    client = get_client()

    mode = "随机采样 seed={}".format(random_seed) if random_seed is not None else "顺序scroll"
    print("[1/3] 扫描源索引: {} (max_docs={}, {})".format(SOURCE_INDEX, max_docs, mode))
    t0 = time.time()
    accounts, dedup_stats = dedup_accounts(iter_source_docs(client, max_docs, random_seed))
    print("      原始帖文={total_docs} 无平台/id={no_platform_or_id} 去重后账号={unique_accounts} "
          "(耗时{:.1f}s)".format(time.time() - t0, **dedup_stats))

    print("[2/3] 大模型判断新就业群体身份 (并发={})...".format(SCAN_CONFIG["judge_workers"]))
    t1 = time.time()
    hits = []
    community_counter = {}
    no_target_index = 0
    with ThreadPoolExecutor(max_workers=SCAN_CONFIG["judge_workers"]) as ex:
        futures = [ex.submit(judge_account, doc) for doc in accounts]
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            if r:
                hits.append(r)
                community_counter[r["community"]] = community_counter.get(r["community"], 0) + 1
                if not r["target_index"]:
                    no_target_index += 1
            if i % 200 == 0:
                print("      已判断 {}/{}，命中 {}".format(i, len(accounts), len(hits)))

    print("[3/3] 写入结果: {}".format(output_path))
    with open(output_path, "w", encoding="utf-8") as f:
        for r in hits:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 同时导出 Excel，含全部字段，便于人工核对判断结果
    excel_path = os.path.splitext(output_path)[0] + ".xlsx"
    export_excel(hits, excel_path)
    print("      Excel: {}".format(excel_path))

    stats = {
        "source_index": SOURCE_INDEX,
        "output_path": output_path,
        "excel_path": excel_path,
        "scan": dedup_stats,
        "judged_accounts": len(accounts),
        "hit_new_employment": len(hits),
        "by_community": community_counter,
        "hit_without_media_index": no_target_index,
        "judge_seconds": round(time.time() - t1, 1),
    }
    print("\n===== 运行统计 =====")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return stats


def main():
    parser = argparse.ArgumentParser(description="扫描人工预警索引，判断新就业群体身份")
    parser.add_argument("--max-docs", type=int, default=None,
                        help="最多扫描的原始帖文数（验证时建议设小，如 500）")
    parser.add_argument("--output", type=str, default=None, help="结果 JSONL 输出路径")
    parser.add_argument("--random", dest="random_seed", type=int, default=None,
                        help="随机采样种子，指定后每次换种子得到不同批次（size<=10000）")
    args = parser.parse_args()
    run(max_docs=args.max_docs, output_path=args.output, random_seed=args.random_seed)


if __name__ == "__main__":
    main()

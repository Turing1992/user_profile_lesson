# -*- coding: utf-8 -*-
"""按日期估算预警活跃账号的唯一主身份数量分布。"""
import argparse
import datetime
import json
import os
import re
import time

import pandas as pd


_EXCEL_ILLEGAL_CHARACTERS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _sanitize_excel_value(value):
    """移除 Excel 单元格不支持的控制字符，保留换行和制表符。"""
    if isinstance(value, str):
        return _EXCEL_ILLEGAL_CHARACTERS.sub("", value)
    return value


def _sanitize_excel_frame(frame):
    mapper = getattr(frame, "map", None)
    if mapper is not None:
        return mapper(_sanitize_excel_value)
    return frame.applymap(_sanitize_excel_value)

from new_employment_warning.config import OUTPUT_DIR, SOURCE_INDEX
from new_employment_warning.scan import get_client
from new_employment_warning.time_account_identity_distribution import count_window
from new_employment_warning.time_unique_identity_distribution import (
    OTHER_GROUP,
    PRIMARY_PRIORITY,
    classify_sample,
    query_account_sample,
    query_candidate_count,
)


def iter_dates(start_date, end_date):
    current = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    last = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    while current <= last:
        yield current.strftime("%Y-%m-%d")
        current += datetime.timedelta(days=1)


def _save_checkpoint(path, state):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def _load_checkpoint(path, meta):
    if not os.path.exists(path):
        return {"meta": meta, "days": {}}
    with open(path, "r", encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("meta") != meta:
        raise ValueError("检查点参数不一致，请更换输出文件名")
    return state


def process_day(client, date_value, sample_accounts, max_judge, workers):
    start_time = "{} 00:00:00".format(date_value)
    end_time = "{} 23:59:59".format(date_value)
    seed = int(date_value.replace("-", ""))
    window = count_window(client, start_time, end_time)
    candidate = query_candidate_count(client, start_time, end_time)
    sample = query_account_sample(
        client, start_time, end_time, candidate["candidate_accounts"],
        sample_accounts, seed,
    )
    rows, audit_rows, classification = classify_sample(
        sample, candidate["candidate_accounts"], window["unique_accounts"],
        max_judge, workers, seed,
    )
    for row in rows:
        row["date"] = date_value
        row["daily_unique_accounts"] = window["unique_accounts"]
        row["daily_share"] = (
            float(row["estimated_unique_accounts"]) / window["unique_accounts"]
            if window["unique_accounts"] else 0.0
        )
    for row in audit_rows:
        row["date"] = date_value
    identified = sum(
        row["estimated_unique_accounts"] for row in rows
        if row["identity_group"] != OTHER_GROUP
    )
    stats = {
        "date": date_value,
        "posts": window["posts"],
        "unique_accounts": window["unique_accounts"],
        "candidate_accounts": candidate["candidate_accounts"],
        "sample_accounts": classification["sample_accounts"],
        "official_accounts": classification["official_accounts"],
        "hard_pass_accounts": classification["hard_pass_accounts"],
        "judged_accounts": classification["judged_accounts"],
        "identified_accounts": identified,
        "other_accounts": window["unique_accounts"] - identified,
        "timed_out": (
            window["timed_out"] or candidate["timed_out"] or sample["timed_out"]
        ),
        "truncated_buckets": sample["truncated_buckets"],
    }
    return {"stats": stats, "distribution": rows, "audit": audit_rows}


def export_excel(state, output_path):
    day_results = [state["days"][day] for day in sorted(state["days"])]
    summary_rows = [result["stats"] for result in day_results]
    distribution_rows = []
    audit_rows = []
    for result in day_results:
        distribution_rows.extend(result["distribution"])
        audit_rows.extend(result["audit"])

    summary = pd.DataFrame(summary_rows).rename(columns={
        "date": "日期", "posts": "预警帖子数",
        "unique_accounts": "当日唯一活跃账号数",
        "candidate_accounts": "身份词候选账号数",
        "sample_accounts": "哈希抽样账号数",
        "official_accounts": "官号/机构账号过滤数",
        "hard_pass_accounts": "硬规则通过账号数",
        "judged_accounts": "模型判断账号数",
        "identified_accounts": "估算明确身份账号数",
        "other_accounts": "其他/无明确身份账号数",
        "timed_out": "查询是否超时",
        "truncated_buckets": "抽样截断桶数",
    })
    distribution = pd.DataFrame(distribution_rows).rename(columns={
        "date": "日期", "identity_group": "唯一身份",
        "standard_identities": "包含标准身份",
        "daily_unique_accounts": "当日唯一活跃账号数",
        "sample_judged_accounts": "模型判断样本账号数",
        "sample_identity_accounts": "样本命中账号数",
        "estimated_unique_accounts": "估算身份账号数",
        "estimated_low_95": "估算下限95%",
        "estimated_high_95": "估算上限95%",
        "daily_share": "占当日账号比例",
    })
    identity_order = list(dict.fromkeys(
        [
            "医护人员", "教师", "律师", "警察", "公职人员",
            "外卖员", "快递员", "网约车司机", "货车司机",
            "家政服务人员", "餐饮从业者", "维修人员", "农牧从业者",
            "工人", "退役军人", "学生", "家长", "老人",
            OTHER_GROUP,
        ]
    ))
    count_pivot = distribution.pivot_table(
        index="日期", columns="唯一身份", values="估算身份账号数",
        aggfunc="sum", fill_value=0,
    ).reindex(columns=identity_order, fill_value=0).reset_index()
    share_pivot = distribution.pivot_table(
        index="日期", columns="唯一身份", values="占当日账号比例",
        aggfunc="sum", fill_value=0,
    ).reindex(columns=identity_order, fill_value=0).reset_index()
    audit = pd.DataFrame(audit_rows).rename(columns={
        "date": "日期", "id": "id(平台|uid)", "platform": "平台",
        "uid": "账号id", "name": "账号名", "verified": "认证状态",
        "verified_type": "认证类型", "verified_reason": "认证说明",
        "description": "账号简介", "unique_identity_group": "唯一身份",
        "standard_identity": "标准身份", "raw_identity": "原始细分身份",
        "evidence": "证据原文", "reason": "判断原因",
        "title": "标题", "content": "正文",
        "url": "url", "publish_time": "发布时间",
    })
    summary = _sanitize_excel_frame(summary)
    distribution = _sanitize_excel_frame(distribution)
    count_pivot = _sanitize_excel_frame(count_pivot)
    share_pivot = _sanitize_excel_frame(share_pivot)
    audit = _sanitize_excel_frame(audit)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="每日运行汇总", index=False)
        distribution.to_excel(writer, sheet_name="日期身份长表", index=False)
        count_pivot.to_excel(writer, sheet_name="日期身份数量透视", index=False)
        share_pivot.to_excel(writer, sheet_name="日期身份占比透视", index=False)
        audit.to_excel(writer, sheet_name="每日抽样明细", index=False)


def run(output_path, start_date, end_date, sample_accounts=1000,
        max_judge=300, workers=8):
    output_path = os.path.abspath(output_path)
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))
    checkpoint_path = os.path.splitext(output_path)[0] + ".checkpoint.json"
    meta = {
        "algorithm_version": 2,
        "source_index": SOURCE_INDEX,
        "start_date": start_date,
        "end_date": end_date,
        "sample_accounts": sample_accounts,
        "max_judge": max_judge,
    }
    state = _load_checkpoint(checkpoint_path, meta)
    client = get_client()
    dates = list(iter_dates(start_date, end_date))
    for index, date_value in enumerate(dates):
        if date_value in state["days"]:
            print("[{}/{}] {}：检查点已完成".format(
                index + 1, len(dates), date_value))
            continue
        result = process_day(
            client, date_value, sample_accounts, max_judge, workers,
        )
        state["days"][date_value] = result
        _save_checkpoint(checkpoint_path, state)
        stats = result["stats"]
        print("[{}/{}] {}：唯一账号{}，抽样{}，官号过滤{}，模型判断{}，明确身份估算{}".format(
            index + 1, len(dates), date_value,
            stats["unique_accounts"], stats["sample_accounts"],
            stats["official_accounts"], stats["judged_accounts"],
            stats["identified_accounts"],
        ))
        time.sleep(0.5)
    export_excel(state, output_path)
    print("Excel: {}".format(output_path))
    print("检查点: {}".format(checkpoint_path))
    return state


def main():
    parser = argparse.ArgumentParser(description="按日期统计预警账号唯一身份数量分布")
    parser.add_argument("--start-date", default="2026-07-20")
    parser.add_argument("--end-date", default="2026-07-27")
    parser.add_argument(
        "--output",
        default=os.path.join(OUTPUT_DIR, "预警账号唯一身份按日期分布_20260720_至今.xlsx"),
    )
    parser.add_argument("--sample-accounts", type=int, default=1000)
    parser.add_argument("--max-judge", type=int, default=300)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    run(
        args.output, args.start_date, args.end_date,
        sample_accounts=max(200, min(args.sample_accounts, 5000)),
        max_judge=max(1, args.max_judge), workers=max(1, args.workers),
    )


if __name__ == "__main__":
    main()

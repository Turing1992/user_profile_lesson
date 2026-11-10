#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计道钉 ES 账号 user_info_extract_6801 在某个月的用量（只读日志，不打 ES）。

覆盖两个常驻业务：
  1. 高频库内容判定 content_worker（high_freq_filter）
     - 账号数：outputs/content_judged.log，每个判定过的账号一行，带完整日期。
       跳过的已入库账号（skip_cached）不抽帖，不在这个日志里，也不打 ES。
     - 请求数：每个账号先查 1 次收窄索引；窗口内 0 条再回退全通配 xgks_*_* 查 1 次。
       content_worker.log 里的「抽帖:{...}」只有时分秒没有日期，没法按月切，
       所以用日志里最后一次打印的累计计数算回退比例，再乘账号数估算。
  2. 负面账号分类 negative_account
     - 实时 realtime_worker：logs/realtime.log 每轮「发帖量>N 合格 X」，
       这 X 个账号每个调一次 fetch_user_posts（1 次请求，失败最多重试 3 次）。
     - 每日兜底 pipeline_negative_daily：logs/daily_YYYYMMDD.log 的
       「stage4+5 完成：{...'已取帖': N...}」或「stage4 完成：取帖 N」。
       daily_cron.sh 只保留 30 天日志，月初的可能已经被删了，脚本会列出缺哪几天。

用法（Python 3.7，只用标准库）：
  python3 es6801_usage_stats.py --month 2026-10 \
      --hf-dir /root/high_freq_filter --neg-dir /data/negative_account
"""
import argparse
import ast
import calendar
import os
import re
from collections import Counter


# ---------------------------------------------------------------- 高频库
def hf_accounts(hf_dir, month):
    """content_judged.log：时间\\tuid-domain\\t入库\\t理由"""
    path = os.path.join(hf_dir, "outputs", "content_judged.log")
    by_day, by_dom, by_store = Counter(), Counter(), Counter()
    if not os.path.exists(path):
        print("  [缺] %s" % path)
        return by_day, by_dom, by_store
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith(month):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            by_day[parts[0][:10]] += 1
            key = parts[1]
            by_dom[key.rsplit("-", 1)[1] if "-" in key else "?"] += 1
            by_store[parts[2]] += 1
    return by_day, by_dom, by_store


def hf_fetch_ratio(hf_dir):
    """取 content_worker.log 最后一条「抽帖:{...}」累计计数。"""
    path = os.path.join(hf_dir, "content_worker.log")
    if not os.path.exists(path):
        print("  [缺] %s" % path)
        return None
    last = None
    pat = re.compile(r"抽帖:(\{[^}]*\})")
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pat.search(line)
            if m:
                last = m.group(1)
    if not last:
        return None
    try:
        return ast.literal_eval(last)
    except (ValueError, SyntaxError):
        return None


def report_hf(hf_dir, month, days):
    print("=" * 70)
    print("【高频库内容判定 content_worker】 %s" % hf_dir)
    by_day, by_dom, by_store = hf_accounts(hf_dir, month)
    total = sum(by_day.values())
    print("  抽帖账号数（%s）: %s" % (month, "{:,}".format(total)))
    missing = [d for d in days if d not in by_day]
    if missing:
        print("  无记录的日期 %d 天: %s" % (len(missing), ", ".join(m[5:] for m in missing)))
    print("  按平台 Top10: " + "  ".join(
        "%s=%s" % (k, "{:,}".format(v)) for k, v in by_dom.most_common(10)))
    print("  按入库结果: " + "  ".join("%s=%s" % (k, "{:,}".format(v))
                                  for k, v in by_store.most_common()))

    st = hf_fetch_ratio(hf_dir)
    if st:
        # 每次 fetch_recent_texts：先 1 次收窄查询；结果为 [] 时 fallback_all 再 1 次全通配
        first = (st.get("narrow_hit", 0) + st.get("fallback_all", 0)
                 + st.get("http_error", 0) + st.get("exception", 0))
        # http_error/exception 也可能出在回退那次，这里一律按第一次算，略偏保守
        first = max(first, 1)
        fb = st.get("fallback_all", 0) / float(first)
        print("  抽帖计数（content_worker.log 最后一次累计）: %s" % st)
        print("  回退全通配比例 ≈ %.1f%%" % (fb * 100))
        print("  估算 ES 请求数 ≈ %s（收窄 %s + 全通配 %s）" % (
            "{:,}".format(int(total * (1 + fb))), "{:,}".format(total),
            "{:,}".format(int(total * fb))))
    else:
        print("  未找到抽帖计数，ES 请求数 ≥ 账号数 %s（每账号至少 1 次）" % "{:,}".format(total))
    print("  按天账号数:")
    for d in days:
        if by_day.get(d):
            print("    %s  %s" % (d, "{:,}".format(by_day[d])))
    return total


# ---------------------------------------------------------------- 负面账号
RT_ROUND = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) [\d:]+\]\s+发帖量>\d+ 合格 (\d+)")
RT_FAIL = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) [\d:]+\]\s+\[warn\] 取帖失败")
RT_NOPOST = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) [\d:]+\]\s+判定完成 \d+ 个 .*无帖 (\d+)")


def neg_realtime(neg_dir, month):
    path = os.path.join(neg_dir, "logs", "realtime.log")
    fetched, fail, nopost = Counter(), Counter(), Counter()
    if not os.path.exists(path):
        print("  [缺] %s" % path)
        return fetched, fail, nopost
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("[" + month):
                continue
            m = RT_ROUND.match(line)
            if m:
                fetched[m.group(1)] += int(m.group(2))
                continue
            m = RT_FAIL.match(line)
            if m:
                fail[m.group(1)] += 1
                continue
            m = RT_NOPOST.match(line)
            if m:
                nopost[m.group(1)] += int(m.group(2))
    return fetched, fail, nopost


DAILY_DICT = re.compile(r"stage4\+5 完成：(\{.*?\}) \|")
DAILY_S4 = re.compile(r"stage4 完成：取帖 (\d+)")


def neg_daily(neg_dir, month, days):
    """daily_YYYYMMDD.log 的日期是「被处理的那天」，cron 在次日 3 点跑。"""
    out = {}
    for d in days:
        path = os.path.join(neg_dir, "logs", "daily_%s.log" % d.replace("-", ""))
        if not os.path.exists(path):
            continue
        n = 0
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = DAILY_DICT.search(line)
                if m:
                    try:
                        n += int(ast.literal_eval(m.group(1)).get("已取帖", 0))
                    except (ValueError, SyntaxError):
                        pass
                    continue
                m = DAILY_S4.search(line)
                if m:
                    n += int(m.group(1))
        out[d] = n
    return out


def report_neg(neg_dir, month, days):
    print("=" * 70)
    print("【负面账号分类 negative_account】 %s" % neg_dir)
    fetched, fail, nopost = neg_realtime(neg_dir, month)
    rt_total = sum(fetched.values())
    print("  实时链路 取帖账号数: %s（每账号 1 次请求，失败重试另计）" % "{:,}".format(rt_total))
    print("    其中取帖失败 %s 次，无帖 %s 个" % (
        "{:,}".format(sum(fail.values())), "{:,}".format(sum(nopost.values()))))
    missing = [d for d in days if d not in fetched]
    if missing:
        print("    无记录的日期 %d 天: %s" % (len(missing), ", ".join(m[5:] for m in missing)))

    daily = neg_daily(neg_dir, month, days)
    dl_total = sum(daily.values())
    print("  每日兜底 取帖账号数: %s（有日志 %d/%d 天）" % (
        "{:,}".format(dl_total), len(daily), len(days)))
    lost = [d for d in days if d not in daily]
    if lost:
        print("    缺日志 %d 天（daily_cron 只保留 30 天）: %s" % (
            len(lost), ", ".join(m[5:] for m in lost)))
    print("  合计 ES 请求数 ≈ %s" % "{:,}".format(rt_total + dl_total))
    print("  按天（实时 / 兜底）:")
    for d in days:
        a, b = fetched.get(d, 0), daily.get(d, 0)
        if a or b:
            print("    %s  %8s / %8s" % (d, "{:,}".format(a), "{:,}".format(b)))
    return rt_total + dl_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="2026-10", help="YYYY-MM")
    ap.add_argument("--hf-dir", default="/root/high_freq_filter")
    ap.add_argument("--neg-dir", default="/data/negative_account")
    ap.add_argument("--only", choices=["hf", "neg"], default=None)
    a = ap.parse_args()

    y, m = map(int, a.month.split("-"))
    days = ["%04d-%02d-%02d" % (y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]
    if a.only != "neg":
        report_hf(a.hf_dir, a.month, days)
    if a.only != "hf":
        report_neg(a.neg_dir, a.month, days)


if __name__ == "__main__":
    main()

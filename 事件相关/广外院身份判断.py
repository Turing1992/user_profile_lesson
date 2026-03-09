import json
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


# ========== 配置 ==========
API_KEY = "9ae7fe44-6195-4c9f-93b0-e95a250415a2"
API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

promts3 = """
我想让你扮演高中或高职学生身份判断专家，我会给你输入一个账号的发帖的贴文，你帮我从文章中判断出他的身份
判断要求为：1，如果是广告则不做判断
2，如果发帖人语气是老师，或是家长则不判断
3，请注意发帖人所述是初中生还是高中生/高职生

5，输出格式为：
    {
    "identity":"高中生/高职生",
    "log":"判断原因"
    }

请只返回判断的分类名称，信息如下：
"""

MAX_WORKERS = 10  # 最大并发线程数，建议 5~20，根据 API 限流调整
REQUEST_DELAY = 0.2  # 每个请求最小间隔（秒），可设为 0 如果 API 允许高并发


def get_kind(txt, index=None):
    """带索引返回，便于多线程后对齐结果"""
    if not txt.strip():
        return index, {"identity": "", "log": "标题和正文均为空"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    body = {
        "model": "ep-20250425133839-bmrjf",
        "messages": [
            {"role": "system", "content": promts3},
            {"role": "user", "content": txt}
        ],
        "extra_headers": {
            "x-ark-moderation-scene": "skip-ark-moderation"
        },
    }

    for attempt in range(3):
        try:
            response = requests.post(API_URL, headers=headers, json=body, timeout=30)
            response.raise_for_status()
            resp_json = response.json()
            content = resp_json["choices"][0]["message"]["content"].strip()

            if content:
                parsed = json.loads(content)
                # 确保字段存在
                identity = parsed.get("identity", "")
                log = parsed.get("log", "无日志")
                return index, {"identity": identity, "log": log}
            else:
                return index, {"identity": "", "log": "模型返回空内容"}

        except Exception as e:
            if attempt == 2:
                return index, {"identity": "", "log": f"请求失败: {str(e)[:100]}"}
            time.sleep(1)

    return index, {"identity": "", "log": "未知错误"}


def main():
    input_file = "云贵高中身份_去重.xlsx"
    output_file = "云贵高中生身份判断.xlsx"

    df = pd.read_excel(input_file)

    if "标题" not in df.columns or "内容" not in df.columns:
        raise ValueError("Excel文件必须包含'标题'和'内容'两列！")

    # 准备输入文本列表（带索引）
    tasks = []
    for idx, row in df.iterrows():
        title = str(row["标题"]) if pd.notna(row["标题"]) else ""
        content = str(row["内容"]) if pd.notna(row["内容"]) else ""
        text = (title + "\n" + content).strip()
        tasks.append((idx, text))

    print(f"共需处理 {len(tasks)} 行数据，使用 {MAX_WORKERS} 个线程...")

    results = [None] * len(df)  # 预分配结果列表，按索引写入

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(get_kind, txt, idx): idx for idx, txt in tasks
        }

        completed = 0
        for future in as_completed(future_to_index):
            idx, result_dict = future.result()
            results[idx] = result_dict
            completed += 1
            if completed % 10 == 0:
                print(f"✅ 已完成 {completed}/{len(tasks)}")

            # 可选：轻微延时防止突发流量
            time.sleep(REQUEST_DELAY)

    # 提取 identity 和 log
    df["identity"] = [r["identity"] for r in results]
    df["log"] = [r["log"] for r in results]

    df.to_excel(output_file, index=False)
    print(f"🎉 处理完成！结果已保存至：{output_file}")


if __name__ == "__main__":
    main()
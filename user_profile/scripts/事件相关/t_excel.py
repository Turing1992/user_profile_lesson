import json
import re
import pandas as pd
import requests
import json
import openai



API_KEY="9ae7fe44-6195-4c9f-93b0-e95a250415a2"
API_URL="https://ark.cn-beijing.volces.com/api/v3/chat/completions"

promts3="""
我想让你扮演高中学生身份判断专家，我会给你输入一个账号的发帖的贴文，你帮我从文章中判断出他的身份
判断要求为：1，如果是广告则不做判断
2，如果发帖人语气是老师，或是家长则不判断
3，请注意发帖人所述是初中生还是高中生



5，输出格式为：
    {
    "identity":"高中生",
    "log":"判断原因"
    }

请只返回判断的分类名称，信息如下：
"""


def get_kind(txt):
    """
    pass
    :return:
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    body = {
        "model": "ep-20250618113756-95fzt",
        "messages": [
            {"role": "system", "content": promts3},
            {"role": "user", "content": txt}
        ],
        "extra_headers":{
            "x-ark-moderation-scene": "skip-ark-moderation"
        },
    }
    try:
        response = requests.post(API_URL, headers=headers, json=body)
        response.raise_for_status()
        response = response.json()
        response_content = response["choices"][0]["message"]["content"]
        if response_content != "":
            # response_content = response_content.replace(",]", "]").replace("\n", "")
            # match = re.search(r'\[.*?\]', response_content, re.DOTALL)
            # if match:
            #     json_str = match.group(0)  # 提取匹配到的 JSON 部分
            # else:
            #     raise ValueError("No JSON content found in the input string.")
            return json.loads(response_content)
        else:
            return {"identity": "", "identity2": ""}
    except Exception:
        return {"identity": "", "identity2": ""}


def get_kind2(txt):
    api_key = "sk-POKFI9rdc2olh-HduAH_kw"
    base_url = "https://llmapi.paratera.com/v1/chat/completions"  # 注意：这里是完整 endpoint

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "DeepSeek-V3.2-Exp",
        "messages": [
            {"role": "system", "content": promts3},
            {"role": "user", "content": txt}
        ],
        "temperature": 0.0  # 可选：提高输出稳定性
    }

    try:
        response = requests.post(
            base_url,
            headers=headers,
            json=payload,
            timeout=30  # 建议设置超时
        )
        response.raise_for_status()  # 抛出 HTTP 错误（如 4xx/5xx）

        data = response.json()
        # 提取回复内容
        response_content = data["choices"][0]["message"]["content"]

        if response_content.strip():
            return json.loads(response_content)
        else:
            return {"identity": "", "identity2": ""}

    except (json.JSONDecodeError, KeyError) as e:
        # 模型返回非 JSON 或格式错误
        print(f"⚠️ 解析响应失败: {e}, 原始内容: {response.text}")
        return {"identity": "", "identity2": ""}

    except requests.RequestException as e:
        # 网络、超时、HTTP 错误等
        print(f"❌ 请求失败: {e}")
        return {"identity": "", "identity2": ""}

    except Exception as e:
        print(f"💥 未知错误: {e}")
        return {"identity": "", "identity2": ""}


def parse_concatenated_json(text):
    """
    将连续拼接的 JSON 对象（如 {...}{...}）分割并解析为字典列表
    """
    # 使用正则在每个 }{ 之间插入分隔符
    normalized = re.sub(r'}\s*{', '}<SPLIT>{', text)
    json_strings = normalized.split('<SPLIT>')
    records = []
    for js in json_strings:
        try:
            record = json.loads(js.strip())
            records.append(record)
        except json.JSONDecodeError as e:
            print(f"⚠️ 跳过无效 JSON 片段: {str(e)[:100]}...")
    return records


# 读取文件
with open('外卖员抽取.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# 解析
data = parse_concatenated_json(content)
for rec in data:
    try:
        cont = rec['content']
        results=get_kind2(cont)
        rec['repair_com']=results['identity2']
        rec['new_log']=results['log']
        print(rec)
    except:
        rec['repair_com'] = ""
        rec['new_log'] = ""

if not data:
    print("❌ 未解析到任何有效记录，请检查 id.txt 内容")
else:
    # 转 DataFrame
    df = pd.DataFrame(data)

    # 可选：只保留你需要的列（按你之前提到的字段）
    desired_columns = [
        "id", "url", "content", "sitename", "verified_reason", "description",
        "gender", "ip_region", "followers_count", "friends_count", "input_id",
        "user_name", "three_new_identity", "community", "log","repair_com","new_log"
    ]
    # 如果某些列不存在，pandas 会自动填充 NaN，不影响
    df = df[desired_columns] if all(col in df.columns for col in desired_columns) else df

    # 保存为 Excel
    output_file = "output7.xlsx"
    df.to_excel(output_file, index=False, engine="openpyxl")
    print(f"✅ 成功生成 Excel 文件：{output_file}（共 {len(data)} 条记录）")
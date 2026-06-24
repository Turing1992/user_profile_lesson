# -*- coding: utf-8 -*-
"""LLM API 客户端工厂模块。

封装了对 qwen3.5-flash 大模型 API 的调用逻辑，提供观点抽取、用户信息分析、
年龄推断、身份分类、性质判断、养成身份识别等多种 LLM 推理接口。
所有接口均内置重试机制，确保在网络波动时的调用稳定性。
"""
import time
import traceback
import re
import json
import requests
# import dirtyjson
from actrie import Matcher

# ===== 统一 LLM 配置：TokenHub qwen3.5-flash =====
LLM_API_KEY = "sk-umee4PbV8mMTdbrh9YtmZowvQLlbizsoyu1id0rSM0VmIW4O"
url = "https://tokenhub.tencentmaas.com/v1/chat/completions"
LLM_MODEL = "qwen3.5-flash"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LLM_API_KEY}"
}

# 身份(identity)抽取专用模型（与全局一致，保留常量供外部引用）
IDENTITY_LLM_API_KEY = LLM_API_KEY
IDENTITY_LLM_URL = url
IDENTITY_LLM_MODEL = LLM_MODEL
identity_headers = headers
kind_md = Matcher()
kind_md.load_from_collection(["政务媒体", "商业媒体", "企业官方", "社会组织", "自媒体", "其他", "中央", "省级", "地方"])
kind_md2= Matcher()
kind_md2.load_from_collection(["学生", "家长", "老师", "企业员工", "医护人员", "公务员", "警察", "农民", "残障人士", "律师", "退役军人", "自媒体创作者", "未成年人", "老年人", "其他"])



# 定义接口调用函数
def  get_opinin_info(text):
    # type: (str) -> tuple
    """调用 qwen3.5-flash 模型抽取帖文中的观点信息。

    对输入的帖文内容进行观点抽取，自动过滤广告和日常类内容。
    内置 3 次重试机制。

    Args:
        text: 待分析的帖文文本内容。

    Returns:
        成功时返回 (结果字典, 请求ID, 原始响应内容) 三元组；
        失败时返回 {"result": ""} 单个字典。
    """
    promts = """
    我想让你扮演做言论立场判断员，我会给你输入一个账号的发帖的贴文，你帮我抽取出这个帖文涉及的观点，如果是广告，日常之类的就别抽取了
    你自行判帖文内容是否涉及某个产品或者某个政府部门，然后抽取观点信息


    ## 输出要求：
    1,抽取的观点最好简短一些
    2，如果判断为广告贴输出
    {"result":""}
    3，输出格式为：
        {
        "result":"观点详情",
        }

    请只返回判断的分类名称，信息如下：
    """
    times = 3
    while times>0:
        try:
            data = {
                "model": LLM_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{promts}+"\n"+{text}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "stream": False
            }
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                response_json = response.json()
                response_id = response_json["id"]
                response_content = response_json["choices"][0]["message"]["content"]
                try:
                    results = json.loads(response_content)
                except json.JSONDecodeError:
                    results = {"result":""}
                return results, response_id,response_content
            elif response.status_code == 429:
                time.sleep(15)
                times-=1
                continue
            else:
                response_id = ""
                time.sleep(4)
                times-=1
                continue
        except Exception:
            time.sleep(4)
            times -= 1
            continue
    return {"result":""}



def get_user_infos(prompt,txt,log):
    # type: (str, str, object) -> tuple
    """调用 qwen3.5-flash 大模型获取用户综合信息（身份抽取）。

    根据自定义 prompt 和帖文内容，调用 TokenHub qwen3.5-flash 进行用户信息分析。
    内置 3 次重试机制。

    Args:
        prompt: 自定义的系统提示词。
        txt: 待分析的帖文文本内容。
        log: 日志记录器实例，用于记录异常信息。

    Returns:
        成功时返回 (结果列表/字典, 请求ID, 原始响应内容) 三元组；
        失败时返回 ([], 0, "") 三元组。
    """
    times = 3
    while times>0:
        try:
            data = {
                "model": IDENTITY_LLM_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+"\n"+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "stream": False
            }
            response = requests.post(IDENTITY_LLM_URL, headers=identity_headers, data=json.dumps(data))
            if response.status_code == 200:
                response_json = response.json()
                response_id = response_json["id"]
                response_content = response_json["choices"][0]["message"]["content"]
                try:
                    results = json.loads(response_content)
                except json.JSONDecodeError:
                    log.exception(f"结果解析失败{response_content}--{response_id}--{traceback.format_exc()}")
                    results = []
                return results, response_id,response_content
            elif response.status_code == 429:
                log.warning(f"触发限流(429)，等待15秒后重试: {response.text}")
                time.sleep(15)
                times-=1
                continue
            else:
                response_id = ""
                log.exception(f"Request failed with status code {response.status_code}")
                log.exception(response.text)
                time.sleep(4)
                times-=1
                continue
        except Exception:
            log.exception(traceback.format_exc())
            time.sleep(4)
            times -= 1
            continue
    return [],0,""


def get_age_info(prompt,txt,log):
    # type: (str, str, object) -> tuple
    """调用 qwen3.5-flash 模型推断用户年龄信息。

    根据自定义 prompt 和帖文内容，调用 LLM 推断用户的年龄范围。
    返回结果为年龄数值列表。内置 3 次重试机制。

    Args:
        prompt: 自定义的系统提示词。
        txt: 待分析的帖文文本内容。
        log: 日志记录器实例，用于记录异常信息。

    Returns:
        成功时返回 (年龄列表, 原始响应内容, 请求ID) 三元组；
        失败时返回 ([], 原始响应内容, 请求ID) 三元组。
    """
    times = 3
    while times > 0:
        try:
            response_id = 0
            data = {
                "model": LLM_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+"\n"+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "stream": False
            }

            response = requests.post(url, headers=headers, data=json.dumps(data))

            if response.status_code == 200:
                response_json = response.json()
                response_id = response_json["id"]
                response_content = response_json["choices"][0]["message"]["content"]
                if "【N】" in response_content:
                    return [], response_content, response_id
                result_content = re.findall(r"\[.*?\]", response_content, re.DOTALL)[0]
                result_content = result_content.replace("\n", "")
                if " - " in result_content:
                    result_content = [int(item.split("-")[0]) - int(item.split("-")[1]) for item in result_content[1:-1].split(" - ")]
                else:
                    result_content = [int(item) for item in result_content[1:-1].split("-")]
                return result_content, response_content, response_id
            elif response.status_code == 429:
                log.warning(f"触发限流(429)，等待15秒后重试: {response.text}")
                time.sleep(15)
                times-=1
                continue
            else:
                log.exception(f"Request failed with status code {response.status_code}")
                log.exception(response.text)
                time.sleep(4)
                times-=1
                continue
        except Exception:
            log.exception(traceback.format_exc())
            time.sleep(4)
            times-=1
            continue
    return [], response_content, response_id

def format_kind(prompt,txt,log):
    # type: (str, str, object) -> tuple
    """调用 qwen3.5-flash 模型判断用户身份格式化分类。

    根据自定义 prompt 和帖文内容，调用 LLM 进行身份分类，
    并通过 actrie 模式匹配提取标准化的身份标签。
    无限重试直到成功。

    Args:
        prompt: 自定义的系统提示词。
        txt: 待分析的帖文文本内容。
        log: 日志记录器实例，用于记录异常信息。

    Returns:
        (匹配到的身份分类字符串, 原始响应内容) 二元组。
    """
    while True:
        try:
            data = {
                "model": LLM_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "stream": False
            }

            response = requests.post(url, headers=headers, data=json.dumps(data))

            if response.status_code == 200:
                response_json = response.json()
                response_content = response_json["choices"][0]["message"]["content"]
                break
            elif response.status_code == 429:
                log.warning(f"触发限流(429)，等待15秒后重试: {response.text}")
                time.sleep(15)
                continue
            else:
                log.exception(f"Request failed with status code {response.status_code}")
                log.exception(response.text)
                time.sleep(4)
                continue
        except Exception:
            log.exception(traceback.format_exc())
            time.sleep(4)
            continue
    result_content = re.findall(r"\[.*\]", response_content, re.DOTALL)[0]
    result_content = result_content.replace("\n", "")
    result_content = kind_md2.findall(result_content)[0][0]
    return result_content,response_content


def xingzhi_kind(prompt,txt,log):
    # type: (str, str, object) -> tuple
    """调用 qwen3.5-flash 模型判断账号性质分类。

    根据自定义 prompt 和帖文内容，调用 LLM 判断账号的媒体性质
    （如政务媒体、商业媒体、企业官方等），并通过 actrie 模式匹配
    提取标准化的性质标签列表。无限重试直到成功。

    Args:
        prompt: 自定义的系统提示词。
        txt: 待分析的帖文文本内容。
        log: 日志记录器实例，用于记录异常信息。

    Returns:
        (性质标签列表, 原始响应内容) 二元组。
        若响应包含「【N】」标记，返回 ([], 原始响应内容)。
    """
    while True:
        try:
            data = {
                "model": LLM_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+"\n"+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "stream": False
            }
            response = requests.post(url, headers=headers, data=json.dumps(data))

            if response.status_code == 200:
                response_json = response.json()
                response_content = response_json["choices"][0]["message"]["content"]
                break
            elif response.status_code == 429:
                log.warning(f"触发限流(429)，等待15秒后重试: {response.text}")
                time.sleep(15)
                continue
            else:
                log.exception(f"Request failed with status code {response.status_code}")
                log.exception(response.text)
                time.sleep(4)
                continue
        except Exception:
            log.exception(traceback.format_exc())
            time.sleep(4)
            continue
    logg = response_content
    if "【N】" in response_content:
        return [],logg
    result_content = re.findall(r"\[.*?\]", response_content, re.DOTALL)[-1]
    result_content = result_content.replace("\n", "")
    # r = json.loads(result_content)
    r = [item[0] for item in kind_md.findall(result_content)]
    return r,logg


def yangcheng_identity(prompt,txt,log):
    # type: (str, str, object) -> tuple
    """调用 qwen3.5-flash 模型批量识别养成类账号身份。

    根据自定义 prompt 和批量帖文 JSON 数据，调用 LLM 进行身份识别。
    会校验返回结果数量与输入数量是否匹配。无限重试直到成功。

    Args:
        prompt: 自定义的系统提示词。
        txt: 待分析的帖文 JSON 字符串（列表格式）。
        log: 日志记录器实例，用于记录异常信息。

    Returns:
        (识别结果列表, 请求ID) 二元组。
        若结果数量不匹配，返回 ([], 请求ID)。
    """
    while True:
        try:
            data = {
                "model": LLM_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+":\n"+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "stream": False
            }
            response = requests.post(url, headers=headers, data=json.dumps(data))

            if response.status_code == 200:
                response_json = response.json()
                response_content = response_json["choices"][0]["message"]["content"]
                result = json.loads(response_content.replace("\n", ""))
                if len(result) != len(json.loads(txt)):
                    print(f"警告: 批次处理结果数量不匹配 - {len(result)} vs {len(json.loads(txt))}")
                    print(result)
                    print(json.loads(txt))
                    print(response_json["id"])
                    return [],response_json["id"]
                return result,response_json["id"]
            elif response.status_code == 429:
                log.warning(f"触发限流(429)，等待15秒后重试: {response.text}")
                time.sleep(15)
                continue
            else:
                log.exception(f"Request failed with status code {response.status_code}")
                log.exception(response.text)
                time.sleep(10)
                continue
        except Exception:
            log.exception(traceback.format_exc())
            time.sleep(10)
            continue

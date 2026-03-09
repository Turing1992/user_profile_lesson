import time
import traceback
import re
import json
import requests
# import dirtyjson
from actrie import Matcher

url = "https://api.hunyuan.cloud.tencent.com/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer sk-EzfEPX79KDf9nZOS4QkhmZhrJZteVyfXrMAOvgHai26WVSNv"
}
kind_md = Matcher()
kind_md.load_from_collection(["政务媒体", "商业媒体", "企业官方", "社会组织", "自媒体", "其他", "中央", "省级", "地方"])
kind_md2= Matcher()
kind_md2.load_from_collection(["学生", "家长", "老师", "企业员工", "医护人员", "公务员", "警察", "农民", "残障人士", "律师", "退役军人", "自媒体创作者", "未成年人", "老年人", "其他"])



# 定义接口调用函数
def  get_opinin_info(text):
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
                "model": "hunyuan-turbos-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{promts}+"\n"+{text}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "enable_enhancement": False
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
    times = 3
    while times>0:
        try:
            data = {
                "model": "hunyuan-turbos-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+"\n"+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "enable_enhancement": False
            }
            response = requests.post(url, headers=headers, data=json.dumps(data))
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
    times = 3
    while times > 0:
        try:
            response_id = 0
            data = {
                "model": "hunyuan-turbos-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+"\n"+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "enable_enhancement": False
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
    while True:
        try:
            data = {
                "model": "hunyuan-turbos-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "enable_enhancement": False
            }

            response = requests.post(url, headers=headers, data=json.dumps(data))

            if response.status_code == 200:
                response_json = response.json()
                response_content = response_json["choices"][0]["message"]["content"]
                break
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
    while True:
        try:
            data = {
                "model": "hunyuan-turbos-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+"\n"+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "enable_enhancement": False
            }
            response = requests.post(url, headers=headers, data=json.dumps(data))

            if response.status_code == 200:
                response_json = response.json()
                response_content = response_json["choices"][0]["message"]["content"]
                break
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
    while True:
        try:
            data = {
                "model": "hunyuan-turbos-latest",
                "messages": [
                    {
                        "role": "user",
                        "content": f"""{prompt}+":\n"+{txt}"""
                    }
                ],
                "temperature": 0.01,
                "top_p": 0.01,
                "enable_enhancement": False
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
            else:
                log.exception(f"Request failed with status code {response.status_code}")
                log.exception(response.text)
                time.sleep(10)
                continue
        except Exception:
            log.exception(traceback.format_exc())
            time.sleep(10)
            continue
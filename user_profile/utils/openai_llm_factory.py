import time
import traceback
import re
import json
from openai import OpenAI
# from json_repair import repair_json

# 构造 client（TokenHub qwen3.5-flash）
client = OpenAI(
    api_key="sk-umee4PbV8mMTdbrh9YtmZowvQLlbizsoyu1id0rSM0VmIW4O",  # qwen3.5 APIKey
    base_url="https://tokenhub.tencentmaas.com/v1",  # qwen3.5 endpoint
)

LLM_MODEL = "qwen3.5-flash"


def get_user_infos(prompt,txt,log):
    while True:
        try:
            completion = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": f"""{prompt}+"\n"+{txt}"""
                    }
                ],
                temperature=0.01,
                top_p=0.01,
            )
            response_content = completion.choices[0].message.content
            break
        except Exception:
            log.exception(traceback.format_exc())
            time.time(2)
            continue
    # log.info(response_content)
    if "【N】" in response_content:
        return {}, 0, response_content
        # print(response_dict["Choices"][0]["Message"]["Content"])
    result_content = re.findall(r"\{.*?\}", response_content, re.DOTALL)[0]
    result_content = result_content.replace("\n", "")
    result_content = repair_json(result_content)
    try:
        r = json.loads(result_content)
    except Exception:
        print(result_content)
        raise json.decoder.JSONDecodeError
    return r, 1, response_content


def get_age_info(prompt,txt,log):
    while True:
        try:
            completion = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": f"""{prompt}+"\n"+{txt}"""
                    }
                ],
            temperature = 0.01,
            top_p = 0.01,
            )
            response_content = completion.choices[0].message.content
            break
        except Exception:
            log.exception(traceback.format_exc())
            time.sleep(2)
            continue
    if "【N】" in response_content:
        return [],response_content
        # print(response_dict["Choices"][0]["Message"]["Content"])
    result_content = re.findall(r"\[.*?\]", response_content, re.DOTALL)[0]
    result_content = result_content.replace("\n", "")
    if " - " in result_content:
        result_content = [int(item.split("-")[0])-int(item.split("-")[1]) for item in result_content[1:-1].split(" - ")]
    else:
        result_content = [int(item) for item in result_content[1:-1].split("-")]
    return result_content,response_content


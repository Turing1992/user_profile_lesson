import json
import traceback
import os
import pandas as pd
import requests
import json
import openai


API_KEY="9ae7fe44-6195-4c9f-93b0-e95a250415a2"
API_URL="https://ark.cn-beijing.volces.com/api/v3/chat/completions"

promts="""
我想让你扮演一个精确信息抽取专家，我会给你账号的发帖数据，你需要帮我抽取几个信息，以下为任务详情
1，先判断是否为广告，生活日常向等不重要信息，如果是则不做任何抽取
2，如果是涉及一些事件评论的信息则进行抽取（这里的事件一般为负面事件，包括涉及政府，企业等）观点，对事件的看法，立场等
3，判断里面是否有涉及账号人的组织，职位，学校，学历，婚姻状况，家庭组成，薪资状态等详细信息，有的话一并抽取到一个json中
4,判断该账号经常参与的话题有哪些（经常参与的阈值=相似话题数>3),如果有的话请判断该账号的兴趣爱好放在一个列表中

## 输出要求：
1,抽取的观点最好简短一些
2，输出格式为：
    {
    "content_opinin":"观点详情",
    "user_info":{"职位":"","学历"：""...},
    "hobbies":[摄影，绘画...]
    }

请只返回判断的分类名称，信息如下：
"""

promts2="""
我想让你扮演做言论立场判断员和身份类型、社会组织判断员，我会给你输入一个账号的发帖的贴文，你帮我抽取出这个帖文涉及的观点和判断这个人的身份
任务1:抽取给定贴文的立场，如涉证涉民生，以及一些事件的看法等，如果是一些广告，追星，电视剧，等评论就不用抽取，输出空字符串“”
任务2:我需要你对账号发帖人做一个身份识别，属于什么类别，和具体的职业，输出到identity和identity2中
平台配送与运输从业者：网约配送员（外卖骑手）快递员，网约车司机，货车司机（长途货运）等
互联网内容生产与服务从业者：网络主播，自媒体创作者，网络服务提供者，包括电商主播、娱乐主播，公众号博主、短视频UP主，在线教师、在线设计师、远程客服
生活服务与共享经济从业者：网约家政服务人员，社交电商从业者，共享经济服务者，通过平台提供保洁、保姆、维修等服务
自由职业与多元兼职从业者：自由职业者/“斜杠青年”，创意工作者，无固定雇主，从事多元职业，如独立设计师、摄影师，或“白天上班族+夜间网约车司机
其他

任务3:我需要你判断账号的言行是否涉及他是下列组织的一员，
互联网平台企业：电商平台、社交平台、本地生活平台等，
共享经济企业：共享出行、共享空间、共享技能平台等
科技创新型初创企业：聚焦前沿技术研发和应用的中小微企业
传统非公有制经济组织：民营企业、外资企业、个体工商户等
“枢纽型”社会组织：联合会、联盟、联合性协会等,区域社会组织联合会、全国性公益联盟
专业型社会组织：社会服务机构、民办非企业单位、智库、行业协会等,法律援助中心、心理咨询机构、环保组织、养老服务协会、律师/注册会计师协会
“草根”组织/社区社会组织：社区志愿服务队、文化兴趣小组、公益小组等,社区广场舞队、老年合唱团、邻里矛盾调解小组、儿童托管服务组
基金会：各种公募、非公募基金会
社会中介组织：提供评估、鉴证等服务的中介机构
其他


任务3:判断账号是否属于以下几个分类，
美妆、穿搭、健身、母婴、数码、美食、财经、旅游、医美、情感、影视、娱乐、知识、游戏、运动、汽车、音乐、教育

## 输出要求：
1,抽取的观点最好简短一些
2，广告贴不做处理
3,输出身份类别和具体的职业，比如平台配送与运输业者，外卖员，网约车司机，卡车司机等
3，输出格式为：
    {
    "opinin":"观点详情",
    "identity":"平台配送与运输从业者",
    "identity2":"外卖员",
    "org":"互联网平台企业",
    "industry":"财经"
    }

请只返回判断的分类名称，信息如下：
"""


# 企业用promt
qiye_promt="""
你是一个KOL分析家，我会给你一个KOL账号的发帖信息，你需要帮我完成以下几个任务
1，判断账号的所属垂类，美妆、穿搭、健身、母婴、数码、美食、财经、旅游、医美、情感、影视、娱乐、知识、游戏、运动、汽车、音乐、教育等；允许出现多个
2，从场景，目的，品类，产品四个维度总结该账号的定位核心价值（如：干货教程、专业测评、VLOG日常、剧情搞笑等），有涉及品类产品的就加上，没有就不加
3，判断该账号的文章风格账号传递的整体感觉（如：专业严谨、幽默风趣、治愈温暖、高级冷淡等）
4，判断内容质量从 脚本创意、文案深度、拍摄剪辑、逻辑清晰度等分为 极低，低，中等，高，极高五类，并给出理由附在后面
5，判断贴文中是否有品类或者品牌产品，并判断是否为拉踩，输出格式为“屈臣氏-护手霜-拉”，“李医生-护手霜-踩”,一定是按照品牌-产品-拉踩的方式输出，如果只有品类，则只输出品类名


输出格式为：
    {
    "industry":"财经,母婴，穿搭",
    "account_location":"专业评测",
    "content _style":"专业严谨",
    "content_quelity":"高。脚本扎实，测评维度全面深入，有行业独家观点。",
    "past_brands": ["屈臣氏-护手霜-拉","李医生-护手霜-踩"]
    }
请只返回判断的分类名称，信息如下：
"""

promts3="""
我想让你扮演外卖员身份判断专家，我会给你输入一个账号的发帖的贴文，你帮我从文章中判断出他的身份
判断要求为：1，如果是广告则不做判断
2，如果是描述他人送外卖的不算
3，如果贴文是新闻类型或者小说，短剧，则不做判断
4，注意区分点外卖的和送外卖的，如果是点外卖的人怎不做判断
5，优先判断称自己是外卖员，骑手的发文，不要一看到外卖员就下结论
6，一定是描述发帖人自己送外卖，只要出现名字，第三人称，引号中的我是xxx，都不算
7，出现“我送外卖XXXX”这类表达要注意是否是小说
8，文本长度超过200字都不是外卖员


5，输出格式为：
    {
    "identity":"平台配送与运输从业者",
    "identity2":"外卖员",
    "log":"判断原因"
    }

请只返回判断的分类名称，信息如下：
"""

#网约车司机身份判断
promts4="""
我想让你扮演网约车身份判断专家，我会给你输入一个账号的发帖的贴文，你帮我从文章中判断出他的身份
判断要求为：1，如果是广告则不做判断
2，如果是描述他人跑网约车的不算
3，如果贴文是新闻类型或者小说，短剧，则不做判断
4，注意区分乘坐网约车的和跑网约车的，如果是乘坐网约车的人怎不做判断
5，优先判断称自己是跑网约车的，跑滴滴的发文，不要一看到网约车就下结论
6，一定是描述发帖人自己跑网约车，只要出现名字，第三人称，引号中的我是xxx，都不算
7，出现“我跑网约车XXXX”这类表达要注意是否是小说
8，文本长度超过200字都不是网约车司机


5，输出格式为：
    {
    "identity":"平台配送与运输从业者",
    "identity2":"网约车司机",
    "log":"判断原因"
    }

请只返回判断的分类名称，信息如下：
"""

#货车司机判断
promts5="""
我想让你扮演货车司机身份判断专家，我会给你输入一个账号的发帖的贴文，你帮我从文章中判断出他的身份
判断要求为：1，如果是广告则不做判断
2，如果是描述他人跑货车的不算
3，如果贴文是新闻类型或者小说，短剧，则不做判断
5，优先判断称自己是跑货车的，开货车的发文，不要一看到货车司机就下结论
6，一定是描述发帖人自己跑货车，只要出现名字，第三人称，引号中的我是xxx，都不算
7，出现"我跑货车XXXX"这类表达要注意是否是小说
8，文本长度超过200字都不是货车司机

5，输出格式为：
    {
    "identity":"平台配送与运输从业者",
    "identity2":"货车司机",
    "log":"判断原因"
    }

请只返回判断的分类名称，信息如下："""

#快递员判断
promts6="""
我想让你扮演快递员身份判断专家，我会给你输入一个账号的发帖的贴文，你帮我从文章中判断出他的身份
判断要求为：1，如果是广告则不做判断
2，如果是描述他人送快递的不算
3，如果贴文是新闻类型或者小说，短剧，则不做判断
5，优先判断称自己是送快递的，快递员的发文，不要一看到快递员就下结论
6，一定是描述发帖人自己送快递，只要出现名字，第三人称，引号中的我是xxx，都不算
7，出现"我送快递XXXX"这类表达要注意是否是小说
8，文本长度超过200字都不是快递员

5，输出格式为：
    {
    "identity":"平台配送与运输从业者",
    "identity2":"快递员",
    "log":"判断原因"
    }

请只返回判断的分类名称，信息如下："""

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
            return {"identity":"","identity2":"","log":""}
    except Exception:
        return {"identity":"","identity2":"","log":""}


#网约车司机身份判断
def get_kind2(txt):
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
            {"role": "system", "content": promts5},
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
            return {"identity":"","identity2":"","log":""}
    except Exception:
        return {"identity":"","identity2":"","log":""}


def identity_auto(promts,txt):
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
            {"role": "system", "content": promts},
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
            return {"identity":"","identity2":"","log":""}
    except Exception:
        return {"identity":"","identity2":"","log":""}

# def get_kind(txt):
#     api_key = "sk-POKFI9rdc2olh-HduAH_kw"
#     # base_url = "https://llmapi.paratera.com/v1/chat/completions"
#     base_url = "https://llmapi.paratera.com/v1/"
#     client = openai.OpenAI(api_key=api_key, base_url=base_url)
#     try:
#         response = client.chat.completions.create(
#             # model="DeepSeek-V3.1",  # model to send to the proxy
#             model="DeepSeek-V3.2-Exp",  # model to send to the proxy
#             #model="DeepSeek-R1-0528",  # model to send to the proxy
#             messages=[
#                 {"role": "system", "content": promts2},
#                 {"role": "user","content": txt}])
#         response_content=response.choices[0].message.content
#         if response_content != "":
#             # response_content = response_content.replace(",]", "]").replace("\n", "")
#             # match = re.search(r'\[.*?\]', response_content, re.DOTALL)
#             # if match:
#             #     json_str = match.group(0)  # 提取匹配到的 JSON 部分
#             # else:
#             #     raise ValueError("No JSON content found in the input string.")
#             return json.loads(response_content)
#         else:
#             return {"result":""}
#     except Exception:
#         return {"result",""}


# def get_kind(txt):
#     """
#     pass
#     :return:
#     """
#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {API_KEY}"
#     }
#     body = {
#         "model": "ep-20250618113756-95fzt",
#         "messages": [
#             {"role": "system", "content": promts3},
#             {"role": "user", "content": txt}
#         ],
#         "extra_headers":{
#             "x-ark-moderation-scene": "skip-ark-moderation"
#         },
#     }
#     try:
#         response = requests.post(API_URL, headers=headers, json=body)
#         response.raise_for_status()
#         response = response.json()
#         response_content = response["choices"][0]["message"]["content"]
#         if response_content != "":
#             # response_content = response_content.replace(",]", "]").replace("\n", "")
#             # match = re.search(r'\[.*?\]', response_content, re.DOTALL)
#             # if match:
#             #     json_str = match.group(0)  # 提取匹配到的 JSON 部分
#             # else:
#             #     raise ValueError("No JSON content found in the input string.")
#             return json.loads(response_content)
#         else:
#             return {"identity": "", "identity2": ""}
#     except Exception:
#         return {"identity": "", "identity2": ""}



def qiye_expect(txt):
    api_key = "sk-POKFI9rdc2olh-HduAH_kw"
    # base_url = "https://llmapi.paratera.com/v1/chat/completions"
    base_url = "https://llmapi.paratera.com/v1/"
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(
            # model="DeepSeek-V3.1",  # model to send to the proxy
            model="DeepSeek-V3.2-Exp",  # model to send to the proxy
            # model="DeepSeek-R1-0528",  # model to send to the proxy
            messages=[
                {"role": "system", "content": qiye_promt},
                {"role": "user", "content": txt}])
        response_content = response.choices[0].message.content
        if response_content != "":
            # response_content = response_content.replace(",]", "]").replace("\n", "")
            # match = re.search(r'\[.*?\]', response_content, re.DOTALL)
            # if match:
            #     json_str = match.group(0)  # 提取匹配到的 JSON 部分
            # else:
            #     raise ValueError("No JSON content found in the input string.")
            return json.loads(response_content)
        else:
            return {"result": ""}
    except Exception:
        return {"result", ""}

if __name__ == '__main__':
    test = "一个晚睡早起的足球搬运工"
    result=get_kind(test)
    print(result)



promts="""
我想让你做意图识别专家，我会给你输入一个用户的需求文本，你帮我判断出这个用户的真实意图
改意图尽量分为三元组的形式，就是该账号针对谁或者什么事发表了什么观点
例如：针对“中国南海撞船事件”发表了“这种行为极为不妥，有失大国风范”等


## 输出要求：
1,输出该意图属于哪种意图
2，输出你的判断依据
3，输出格式为：
    {
    "评论主体":"人或事",
    "评论内容"："抽取摘要"
    "log":"判断依据"
    }

请判断下面的信息进行判断，信息如下：
"""

import json
import traceback
import pymysql
import os
import requests
import numpy as np
import faiss
import torch
import pandas as pd
from volcenginesdkarkruntime import Ark
import json
# 请在环境变量中设置 VOLC_ACCESSKEY 和 VOLC_SECRETKEY
# os.environ['VOLC_ACCESSKEY'] = 'your_access_key'
# os.environ['VOLC_SECRETKEY'] = 'your_secret_key'
client = Ark(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)


os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
API_URL="http://192.168.184.137:5000/get_scores"
index_path = "faiss_index.bin"

faiss_index = faiss.read_index(index_path)


config = {
        'host': '192.168.19.64',
        'port': 3306,
        'user': 'buser',
        'password': 'p3jnmja3',
        'database':'event_data',  # 指定您要连接的数据库名
        'charset':'utf8mb4',
        'cursorclass':pymysql.cursors.DictCursor
    }


# 插入新款数据
def profile_search(faiss_id):
    conn = pymysql.connect(**config)
    try:
        with conn.cursor() as cursor:
            sql = "select * from profile_test where faiss_id = %s"
            cursor.execute(sql, (faiss_id))
            result = cursor.fetchone()
        conn.commit()
    finally:
        conn.close()
    return result


def embedding_api(source_identity):
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps({"queries": source_identity}, ensure_ascii=False).encode('utf-8'))

    if response.status_code == 200:
        result = response.json()
        # print(json.dumps(result, indent=2, ensure_ascii=False))
        result = [np.array(embedding , dtype=np.float32) for embedding in result['embedings']]
        return result


def search_similar(faiss_index, query_vector, k=10):
    """
    搜索最相似的 k 个向量

    Args:
        faiss_index: 加载的 Faiss 索引（必须是 IndexIDMap 类型）
        query_vector: 查询向量 (768,) 或 list/tensor
        k: 返回前 k 个结果

    Returns:
        scores: 相似度分数（越高越相似，如果是 IP）
        indices: Faiss 内部索引（0,1,2,...），用于定位
    """
    if isinstance(query_vector, list):
        query_vector = np.array(query_vector)
    elif isinstance(query_vector, torch.Tensor):
        query_vector = query_vector.cpu().numpy()

    if query_vector.ndim == 1:
        query_vector = query_vector.reshape(1, -1)
    elif query_vector.ndim > 2:
        query_vector = query_vector.reshape(1, -1)

    query_vector = query_vector.astype('float32')
    faiss.normalize_L2(query_vector)
    distances, indices = faiss_index.search(query_vector, k)
    return distances[0], indices[0]


def  get_kind(txt):
    """
    获取文本中的关键词
    :param txt: strig
    :return: list
    """
    completion = client.chat.completions.create(
        model="ep-20250211104009-7x2bd",
        messages=[
            dict(role="system", content=promts),
            {"role": "user", "content": txt},
        ],
    )
    try:
        response = completion.choices[0].message.content
        results_text=response
    except Exception:
        print(traceback.print_exc())
        results_text = {}
    return results_text


def main():
    #输入用户需求
    text = '想要涉及男女对立的账号'
    print("输入想要搜索的账号",text)
    llm_result = json.loads(get_kind(text))
    yitu=str(llm_result['评论主体'])+str(llm_result['评论内容'])
    search_vector = embedding_api([yitu])
    D, I = search_similar(faiss_index, search_vector[0])
    for i in list(I):
        try:
            data=profile_search(i)
            if '无' in data['opinion']:
                continue
        except:
            continue
        print(data)

if __name__ == '__main__':
    main()

import json
import requests
import faiss
import torch
import numpy as np
import os

API_URL = "http://192.168.184.137:5000/get_scores"
dimension = 1024
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
faiss_index = faiss.IndexFlatIP(dimension)

label={
    "学生":"大学生、小学生、中学生、研究生、博士生、预科生、在校生、备考生、高考生、中考生、考研党等",
    "家长": "学生的家长、宝妈、宝爸、孩子家长、家有儿女等",
    "老师":"学校的老师、教授、讲师、辅导员、班主任、校长、教导主任、幼儿园老师、培训机构老师等",
    "企业员工": "企业单位的员工、职员、白领、上班族、打工人、公司雇员、管理者、高管、部门经理、HR、产品经理、程序员、运营、销售、市场人员等（不含公务员、医护人员、律师等有特定分类的职业)",
    "医护人员": "医生、护士、麻醉师、医师、药师、医学生（实习/规培阶段）、防疫人员、疾控中心人员等",
    "公务员": "政府公职人员、事业单位编制内人员（非教师、医生）、体制内（指政府机关或部分事业单位）等",
    "警察": "警察、民警、辅警、警校学生（未来明确成为警察）等",
    "农民": "农人、农民、村民、种地的、搞养殖的、务农人员、返乡创业（农业相关）、新农人、农村妇女（主要从事农业）等",
    "残障人士": "明确表述为残障人士、残疾人、听障、视障、肢残等",
    "律师": "律师助理、律师、律所从业人员、实习律师、法务（特指律所或专业法律服务机构）、法律顾问（职业）等",
    "退役军人": "退伍军人、退役士兵、转业干部等",
    "自媒体创作者": "主播、博主、UP主、网红、视频创作者、内容创作者、Vlogger、播客主理人等",
    "未成年人": "明确提及年龄小于18岁，或身份描述为小学生、初中生、高中生、中学生（结合出生年份判断，当前年份为2024年）",
    "老年人": "退休人员、明确表述是老年人、60岁以上（结合出生年份判断，当前年份为2024年）、银发族、返聘人员（已退休）、老人、空巢老人、留守老人等"
}

def input_data(batch_embeddings):
    for vector in batch_embeddings:
        # 确保 vector 是一个 NumPy 数组而不是 CUDA 张量
        if isinstance(vector, torch.Tensor):
            vector = vector.cpu().numpy()  # 确保张量在 CPU 上
        # 确保 vector 是一维数组
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)
        faiss.normalize_L2(vector)# 显式转为 float32 的 ndarray    faiss.normalize_L2(vector)
        faiss_index.add(vector)


def search(vector,datas,key):
    if len(vector.shape) == 1:
        vector = vector.reshape(1, -1)
    faiss.normalize_L2(vector)
    D, I = faiss_index.search(vector, k=100)
    similar_scores = D[0]
    similar_ids =  I[0]
    return zip(similar_scores, similar_ids)
    # for score, id in zip(similar_scores, similar_ids):
    #     print(score,id,datas[id][0],key)


def lable_to_vec(label):
    label_embeddings = {}
    for key,value in label.items():
        response = requests.post(
            API_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"queries": [key]}, ensure_ascii=False).encode('utf-8'))

        if response.status_code == 200:
            result = response.json()
            label_embeddings[key]=np.array(result['embedings'][0], dtype=np.float32)
    return label_embeddings



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



def process_file(file_path: str, start_line: int = 200000, group_size: int = 1000, output_json: str = "embeddings_output.json"):

    label_embeddings = lable_to_vec(label)
    batch_identitys = []
    source_identitys = []

    fi = open(file_path, 'r', encoding='utf-8')
    fo = open(output_json, 'w', encoding='utf-8')
    i = 0
    for line in fi:
        i+=1
        # if i<200000:
        #     continue
        source_identity, fre = line.strip().split("\t")
        batch_identitys.append([source_identity, {}])
        source_identitys.append(source_identity)
        if source_identitys.__len__()<100:
            continue
        if source_identitys.__len__() == 100:
            batch_embeddings = embedding_api(source_identitys)
            # .append(source_identity_embedding)
        # source_identity_embedding = embedding_api(source_identity)
        # batch_identitys.append([source_identity,{}])
        # batch_embeddings.append(source_identity_embedding)
        # if batch_identitys.__len__() == 10:
            faiss_index.reset()
            input_data(batch_embeddings)
            for key,label_embedding in label_embeddings.items():
                result = search(label_embedding,batch_identitys,key)
                for score,id in result:
                    batch_identitys[id][1][key] = float(score)
            for batch_identity in batch_identitys:
                print({"原始身份":batch_identity[0],"scores":batch_identity[1]})
                fo.write(json.dumps({"原始身份":batch_identity[0],"scores":sorted(batch_identity[1].items(), key=lambda item: item[1], reverse=True)}, ensure_ascii=False)+"\n")
            batch_identitys = []
            source_identitys = []

# 调用函数
if __name__ == "__main__":
    file_path = "identitys_o.txt"  # 替换为你的文件路径
    process_file(file_path)
# -*- coding: utf-8 -*-
import queue
import threading
import traceback
import time
import redis
from collections import defaultdict
# 在全局区域添加以下配置
TASK_QUEUE = queue.Queue(maxsize=1000)  # 定长队列
import ujson as json
from actrie import Matcher
from utils.prompts import *
from utils.http_llm_factory import *
from utils.about_log import *
from utils.opinin_extract import *
from config.config import *
from utils.bloom import BloomFilter
import pandas as pd
from datetime import datetime
from utils.es_updata_new import *


from rocketmq import (
    DefaultMQProducer,
    DefaultMQPushConsumer,
    Message,
    MessageListenerConcurrently,
)
mylog_hd = config_log("draw_graph", "WARNING")
flush_thread_ref = None


#处理所有入库字段
def data_process(data):
    # 字段映射：{ 输入字段名: 输出字段名 }
    field_mapping = {
        'id': 'uid',
        'sitename': 'site_name',          # 修改为 site_name
        'identity': 'identity',
        'identity_standerd': 'identity_standerd',
        # 注意：这里用 user_name 作为 name，忽略 data["name"]
        'user_name': 'name',              # user_name → name
        'verified_reason': 'verified_reason',
        'description': 'description',
        'ip_region': 'ip_region',
        'gender': 'gender',
        'followers_count': 'followers_count',
        'three_new_identity': 'three_new_identity',
        'community': 'community',
        # 注意：原始 data["name"] 被跳过，未包含在此映射中
    }

    processed_data = {}

    for src_key, dst_key in field_mapping.items():
        value = data.get(src_key)

        # 跳过空值：None, "", [], {}, 空字符串等
        if value is None:
            continue
        if isinstance(value, (str, list, dict, set, tuple)) and len(value) == 0:
            continue

        # 类型处理
        if isinstance(value, list):
            processed_value = ",".join(str(item) for item in value)
        elif isinstance(value, (dict, set, tuple)):
            processed_value = json.dumps(value, ensure_ascii=False)
        else:
            processed_value = str(value)  # 或保留原类型：processed_value = value

        processed_data[dst_key] = processed_value
    processed_data['id']=processed_data['site_name']+'|'+processed_data['uid']
    processed_data['create_time']=datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return processed_data


# 读取Excel身份映射
def load_identity_mapping(excel_path="final_stanterd.xlsx"):
    df_excel = pd.read_excel(excel_path,engine='openpyxl')
    identity_map = dict(zip(df_excel["原始身份"], df_excel["最终身份"]))
    return identity_map

identity_map = load_identity_mapping()

class ProducerMQ():
    def __init__(self,host,groupid):
        self.host = host
        self.groupid = groupid
        self.producer = DefaultMQProducer(self.groupid)
        self.producer.namesrv_addr = self.host
        self.producer.send_latency_fault_enable = False
        self.producer.max_message_size=30000000
        self.producer.start()
    def send2mq(self,info_json,key,topic):
        msg = Message(topic=topic, body=info_json)
        msg.wait_store_msg_ok = True
        msg.keys = key
        error = ""
        for _ in range(3):
            try:
                self.producer.sendOneway(msg=msg)
                return ""
            except Exception as e:
                print(e)
                error = str(e)
        return error
    def close(self):
        self.producer.shutdown()

class Drawing():
    def __init__(self):
        self.redis_cache_identity_bloom = config["redis"]["redis_url_identity_bloom"]
        self.identity_bloom_key = config["redis"]["identity_bloom_key"]
        self.age_cache = defaultdict(list)
        self.bloom_filter = BloomFilter( self.redis_cache_identity_bloom,self.identity_bloom_key)
    def run(self,datas):
        output_file=open("test_output.txt",'a')
        # print(f"run 接收到数据{len(datas)}")
        inputs = []
        try:
            for name_index,yaunshi_data in enumerate(datas):
                dd = {}
                yaunshi_data["input_id"] = str(name_index)
                yaunshi_data["user_name"] = yaunshi_data["name"]
                del yaunshi_data["name"]
                if yaunshi_data["user_name"]:
                    dd["账号名"]= yaunshi_data["user_name"]
                if yaunshi_data["verified_reason"]:
                    dd["账号认证原因"]= yaunshi_data["verified_reason"]
                if yaunshi_data["description"]:
                    dd["账号自我介绍"]= yaunshi_data["content"]+yaunshi_data["description"]
                #修改1--空mapping不再输入模型
                if dd=={}:
                    continue
                dd['input_id'] = str(name_index)
                #修改2--替换name为批次以内的编号
                # dd = {
                #     "账号名": data["name"] ,
                #     "账号认证原因": data["verified_reason"] ,
                #     "账号自我介绍": data["description"],
                # }
                inputs.append(json.dumps(dd, ensure_ascii=False))
            # print(f"run 数据整合完毕{len(datas)}")
            mylog_hd.info(json.dumps(inputs, ensure_ascii=False, indent=2))
            results,info_response_id,response_content = get_user_infos(USER_INFOS, json.dumps(inputs, ensure_ascii=False, indent=2), mylog_hd)
            if info_response_id ==0:
                mylog_hd.error(f"{'请求出错'}-{json.dumps(inputs, ensure_ascii=False, indent=2)}")
                return

            # 修改3--长度结果不一致的数据也进行处理
            if len(results)!=len(inputs):
                mylog_hd.error(f"{'结果数量不一致'}-{info_response_id}-{json.dumps(inputs, ensure_ascii=False, indent=2)}--{response_content}")
                #return
            mylog_hd.info(f"{len(results)}-{len(inputs)}")
            # mylog_hd.info(f"{response_content}")
            #构建标记编号key
            results_lookup = {}
            mylog_hd.info(f"请求id-{info_response_id}")
            mylog_hd.info(json.dumps(results, ensure_ascii=False, indent=2))
            for result in results:
                results_lookup[str(result['input_id'])] = result
            # 使用编号一一对应
            for data in datas:
                mylog_hd.info(f"input_id-{data}")
                idx=data["input_id"]
                if idx in results_lookup:
                    final_result = results_lookup[idx]
                    data["info_response_id"] = info_response_id
                    data["identity"] = final_result.get('identity', []) #身份
                    identity_str = str(data['identity']) if data['identity'] is not None else ""
                    if not identity_str.strip():
                        data['identity_standerd'] = ""
                    elif identity_str == "":
                        data['identity_standerd'] = ""
                    elif ',' not in identity_str:
                        mapped = identity_map.get(identity_str.strip(), "其他")
                        data['identity_standerd'] = [mapped]
                    else:
                        items = [x.strip() for x in identity_str.split(',') if x.strip()]
                        mapped_list = [identity_map.get(item, "其他") for item in items]
                        data['identity_standerd'] = list(set(mapped_list))
                    data['name']=final_result.get('name', [])  #人名
                    #data['birthday'] = final_result.get('birthday', []) #生日信息
                    data['age'] = final_result.get('age', []) #年龄信息
                    if data['content']!="":
                        # 加入姓名，简介，认证联合判断
                        content=data['content']+data['description']+str(data['name'])+data['verified_reason']
                        three_news = get_kind2(content)
                    else:
                        three_news = {"identity":"","identity2":"","log":""}
                    data['three_new_identity']=three_news['identity']
                    data['community']=three_news['identity2']
                    excel_data=data
                    excel_data['log']=three_news['log']
                    # if data['community']=="网约车司机":
                    #     output_file.write(json.dumps(excel_data, ensure_ascii=False, indent=2))
                    # opinin={}
                    #先不计算观点
                    # if data['content'] != '':
                    #     opinin = get_kind(data['content'])
                    #     if opinin!={"result":""}:
                    #         data['opinin'] = opinin
                    #     else:
                    #         data['opinin'] = {"result":""}
                    # else:
                    #     data['opinin'] = {"result":""}
                    # if opinin == {'','result'}:
                    #     data['opinin'] = {"result":""}
                    # if "opinin" not in data.keys():
                    #     data["opinin"] = {"result":""}

                    #在此处调用更新es函数，将数据推入更新队列
                    try:
                        processed_data = data_process(data)  # 处理成最终字段
                        mylog_hd.info(f"处理数据最终为{processed_data}")
                        # update_user_profile(uid=data['id'],INDEX_SUFFIX=data['sitename'],new_data=processed_data)
                        #更新程序
                        update_single_profile(processed_data)
                    except Exception as e:
                        mylog_hd.error(f"Failed to enqueue ES update for {data['id']}: {traceback.format_exc()}")
                        mylog_hd.error(f"出错数据为{data}")



                    # if "age" in result and data["age"] != [] and data["age"] != "[]":
                    #     if type(data["age"]) == list:
                    #         data["age"] = data["age"][0]
                    #     if data["age"] in self.age_cache:
                    #         age, llog, response_id = self.age_cache[data["age"]]
                    #     else:
                    #         age, llog, response_id = get_age_info(ABOUT_AGE, data["age"], mylog_hd)
                    #         self.age_cache[data["age"]] = [age, llog, response_id]
                    #     data["age"] = age
                    #     data["age_response_id"] = response_id
                    # 去除标记编号再入mq
                    #mq_pd.send2mq(json.dumps(data, ensure_ascii=False), data["sitename"] + "^" + data["id"],config["topic"]["user_graph_drawed_result"])
                    #对应的数据才添加进bloom
                    bloom_value = {}
                    bloom_value["sitename"] = data["sitename"]
                    bloom_value["id"] = data["id"]
                    bloom_value["url"] = data["url"]
                    bloom_value["name"] = data["user_name"]
                    # bloom_value["verified_reason"] = data["verified_reason"]
                    # bloom_value["description"] = data["description"]
                    bloom_value = json.dumps(bloom_value, ensure_ascii=False, sort_keys=True)
                    self.bloom_filter.add_value(bloom_value)
                    mylog_hd.info(f"添加bloom-{bloom_value}")
                else:
                    mylog_hd.error(f"{'未被处理的数据为'}-{info_response_id}-{json.dumps(data, ensure_ascii=False, indent=2)}")
        except Exception as e:
            mylog_hd.exception(f"Error processing line: {traceback.format_exc()}")
            return None

class DrawingWrapper:
    def __init__(self):
        self.drawing = Drawing()
    def async_run(self,datas):
        try:
            # 保持原有处理逻辑不变
            # print(f"DrawingWrapper 接收到数据{len(datas)}")
            return self.drawing.run(datas)
        except Exception as e:
            mylog_hd.exception(f"Worker error: {traceback.format_exc()}")

class MyListener(MessageListenerConcurrently):
    def __init__(self):
        self.redis_cache_identity_bloom = config["redis"]["redis_url_identity_bloom"]
        self.identity_bloom_key = config["redis"]["identity_bloom_key"]
        # 去重redis
        self.redis_quchong = redis.from_url(config["redis"]["redis_quchong"])
        # 设置过期时间
        self.REDIS_EXPIRE_SECONDS = 20 * 60
        print(self.redis_cache_identity_bloom)
        print(self.identity_bloom_key)
        # self.md = Matcher()
        # self.md.load_from_collection(["外卖员","外卖日记","外卖行业","外卖小哥不容易","偷外卖的狗","外卖被偷","外卖小哥","外卖路上","外卖骑手","送外卖"])
        #self.md.load_from_collection(["牛马","共党","共匪","包子","中共","革命","韭菜","民主","国内","LGBT","独裁","习家党","国货","灭共"])
        self.md = Matcher()
        self.md.load_from_collection(["开货车","小货车","货车司机","大货车","跑货车","长途货车","货车救援"])
        # self.md2.load_from_collection(
        #     ["欠薪","自燃","社保","养老","我听说","我一个朋友说","阶级","革命","达赖","pua","就业","失业","腐败","懒政","不作为","上访"])

        # self.md.load_from_file("/app/identitys_table.txt")
        self.bloom_filter = BloomFilter(self.redis_cache_identity_bloom, self.identity_bloom_key)

    def consume_message(self, msgs):
        for msg in msgs:
            try:
                data = json.loads(msg.body.decode('utf-8', 'ignore'))
                if data["index_suffix"].startswith("rank"):
                    continue
                if data["index_suffix"] in ["oversea","youtube","facebook","twitter","titok"]:
                    continue
                data = data["data"]
                user = data.get("user")
                if not user or not user.get("uid"):
                    # print("非UGC")
                    continue
                url = data.get("url", "    ")
                if url[-4:] in ["#ocr", "#asr", "#att"]:
                    # print("ocr-asr-att")
                    continue
                # if data.get("wtype",0) in [2,7]:
                #     # print("转发评论")
                #     continue
                site_name = str(data.get("gather", {}).get("site_name", ""))
                # if site_name in ["新浪微博","抖音"]:
                #     continue
                uid = str(user["uid"])
                content = data.get("content", "")
                user_data = {}
                queue_data={}
                queue_data["id"] = uid
                queue_data["url"] = url
                queue_data["content"] = content
                queue_data["sitename"] = site_name
                queue_data['name']=user.get("name","")
                queue_data["verified_reason"] = user.get("verified_reason","")
                queue_data["description"] = user.get("description", "")
                queue_data['gender']=user.get("gender", "")
                queue_data['ip_region']=user.get("ip_region", [])
                if queue_data["ip_region"]!=[]:
                    queue_data["ip_region"]=queue_data["ip_region"][0]
                queue_data['followers_count']=str(user.get("followers_count",0))
                queue_data['friends_count']=str(user.get("friends_count",0))

                user_data["sitename"] = site_name
                user_data["id"] = uid
                user_data["url"] = url
                user_data["name"] = user.get("name","")

                # user_data["verified_reason"] = user.get("verified_reason","")
                # user_data["description"] = user.get("description","")
                bloom_value = json.dumps(user_data, ensure_ascii=False, sort_keys=True)
                if self.md.findall(''.join(queue_data["content"]))==[]:
                    continue
                if self.bloom_filter.is_double(bloom_value):
                    mylog_hd.error(f"重复bloom-{user_data['sitename']}-{user_data['id']}")
                    continue
                # if self.redis_quchong.set(name=f"{site_name}:{uid}", value="1", nx=True, ex=self.REDIS_EXPIRE_SECONDS) !=True:
                #     # print('redis账号重复')
                #     continue
                # user_data["name"] = user.get("name","")
                user_data["verified_reason"] = user.get("verified_reason","")
                user_data["description"] = user.get("description","")
                dd = {}
                if user_data["name"]:
                    dd["账号名"]= user_data["name"]
                if user_data["verified_reason"]:
                    dd["账号认证原因"]= user_data["verified_reason"]
                if user_data["description"]:
                    dd["账号自我介绍"]= user_data["description"]
                #修改1--空mapping不再输入模型
                if dd=={}:
                    # print("空值数据跳过")
                    continue
                user_data['url'] = data.get('url', '')
                # print("账号不重复~~")
                TASK_QUEUE.put(queue_data, block=True)
            except queue.Full:
                mylog_hd.warning("Task queue full, message dropped")
            except Exception as e:
                mylog_hd.error(f"Message processing error: {traceback.format_exc()}")


if __name__ == "__main__":
    #启动es批量更新
    # flush_thread_ref = start_update_system()

    mq_pd = ProducerMQ(config["mq_url"], config["producer_group"]["user_graph_drawed_result"])
    consumer = DefaultMQPushConsumer(config["consumer_group"]["user_graph_uniq_user_identity"])
    consumer.namesrv_addr = config["mq_url"]
    consumer.consume_thread_num = 1
    consumer.consume_message_batch_max_size = 1
    # consumer.pull_threshold_for_queue = 1
    consumer.registerMessageListener(MyListener())
    consumer.subscribe(config["topic"]["spider_data"], "*")
    consumer.start()
    # 启动队列消费者
    time.sleep(3)

    def worker():
        dw= DrawingWrapper()
        datas = []
        keys = set()
        while True:
            try:
                data = TASK_QUEUE.get(timeout=1)
                double_key = data['url']
                if double_key in keys:
                    continue
                else:
                    keys.add(double_key)
                datas.append(data)
                TASK_QUEUE.task_done()
                if len(datas) >= 20:
                    dw.async_run(datas)
                    datas = []
                    keys = set()
            except queue.Empty:
                continue
    # 启动10个守护线程
    for _ in range(10):
        threading.Thread(target=worker, daemon=True).start()
    print("程序启动完成")


    # 关闭程序时，调用强制刷新队列防止数据丢失
    def signal_handler(signum, frame):
        mylog_hd.info("Received shutdown signal, flushing ES updates...")
        # shutdown_update_system()
        os._exit(0)

    import signal
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        mylog_hd.info("Shutting down...")
        # shutdown_update_system()



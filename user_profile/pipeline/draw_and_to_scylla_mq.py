# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import queue
import redis
from collections import defaultdict
from cassandra.cluster import Cluster
import ujson as json
from utils.prompts import *
from utils.http_llm_factory import *
from utils.about_log import *
from utils.opinin_extract import *
from sport_data_get.config import *
from utils.bloom import BloomFilter
import pandas as pd
from datetime import datetime

from rocketmq import (
    DefaultMQProducer,
    DefaultMQPushConsumer,
    Message,
    MessageListenerConcurrently,
)

# 配置
TASK_QUEUE = queue.Queue(maxsize=1000)
mylog_hd = config_log("draw_graph_scylla", "WARNING")

class ScyllaDBHandler:
    """ScyllaDB处理类 - 支持字段变化追踪"""
    def __init__(self):
        # 从config中获取ScyllaDB配置
        scylla_config = config.get("scylladb", {
            "contact_points": ["192.168.191.9"],
            "port": 9042,
            "keyspace": "user_profile_keyspace",
            "auth_provider": None
        })
        
        self.contact_points = scylla_config["contact_points"]
        self.port = scylla_config["port"]
        self.keyspace = scylla_config["keyspace"]
        self.auth_provider = scylla_config.get("auth_provider")
        self.session = self._connect()
        self._create_keyspace_and_tables()

    def _connect(self):
        """连接ScyllaDB"""
        try:
            if self.auth_provider:
                cluster = Cluster(
                    self.contact_points, 
                    port=self.port,
                    auth_provider=self.auth_provider
                )
            else:
                cluster = Cluster(self.contact_points, port=self.port)
            
            session = cluster.connect()
            mylog_hd.info(f"Connected to ScyllaDB: {self.contact_points}")
            return session
        except Exception as e:
            mylog_hd.error(f"Failed to connect to ScyllaDB: {traceback.format_exc()}")
            raise    de
f _create_keyspace_and_tables(self):
        """创建keyspace和表"""
        try:
            # 创建keyspace
            create_keyspace = f"""
            CREATE KEYSPACE IF NOT EXISTS {self.keyspace}
            WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 3}}
            """
            self.session.execute(create_keyspace)
            self.session.set_keyspace(self.keyspace)
            
            # 创建主数据表 data_cookie
            create_data_cookie_table = """
            CREATE TABLE IF NOT EXISTS data_cookie (
                id text,
                uid text,
                site_name text,
                name text,
                verified_reason text,
                description text,
                content text,
                gender text,
                ip_region text,
                followers_count text,
                friends_count text,
                identity list<text>,
                identity_standerd list<text>,
                age list<text>,
                three_new_identity text,
                community text,
                processed_time timestamp,
                url text,
                PRIMARY KEY (id)
            )
            """
            self.session.execute(create_data_cookie_table)
            
            # 创建各字段历史记录表
            field_history_tables = [
                "name_history", "verified_reason_history", "description_history",
                "content_history", "gender_history", "ip_region_history",
                "followers_count_history", "friends_count_history", "identity_history",
                "identity_standerd_history", "age_history", "three_new_identity_history",
                "community_history"
            ]
            
            for table_name in field_history_tables:
                create_history_table = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id text,
                    field_value text,
                    uptime timestamp,
                    PRIMARY KEY (id, uptime)
                ) WITH CLUSTERING ORDER BY (uptime DESC)
                """
                self.session.execute(create_history_table)
            
            mylog_hd.info("ScyllaDB tables created successfully")
            
        except Exception as e:
            mylog_hd.error(f"Failed to create keyspace/tables: {traceback.format_exc()}")
            raise

    def get_existing_data(self, composite_id):
        """从data_cookie表获取现有数据"""
        try:
            query = "SELECT * FROM data_cookie WHERE id = ?"
            rows = list(self.session.execute(query, (composite_id,)))
            return rows[0] if rows else None
        except Exception as e:
            mylog_hd.error(f"Failed to get existing data: {traceback.format_exc()}")
            return None    def co
mpare_and_update_fields(self, composite_id, new_data, existing_data):
        """对比字段并记录变化"""
        current_time = datetime.now()
        
        # 定义需要对比的字段
        comparable_fields = [
            'name', 'verified_reason', 'description', 'content', 'gender',
            'ip_region', 'followers_count', 'friends_count', 'identity',
            'identity_standerd', 'age', 'three_new_identity', 'community'
        ]
        
        changes_detected = False
        
        for field in comparable_fields:
            # 获取新数据的字段值
            if field == 'name':
                new_value = new_data.get('user_name', '')
            else:
                new_value = new_data.get(field, '')
            
            # 获取现有数据的字段值
            existing_value = getattr(existing_data, field, '') if existing_data else ''
            
            # 处理列表类型字段
            if isinstance(new_value, list):
                new_value = ','.join(str(item) for item in new_value)
            if isinstance(existing_value, list):
                existing_value = ','.join(str(item) for item in existing_value)
            
            # 转换为字符串进行比较
            new_value_str = str(new_value) if new_value is not None else ''
            existing_value_str = str(existing_value) if existing_value is not None else ''
            
            # 如果字段值发生变化
            if new_value_str != existing_value_str:
                changes_detected = True
                mylog_hd.info(f"Field '{field}' changed from '{existing_value_str}' to '{new_value_str}' for {composite_id}")
                
                # 记录到对应的历史表
                self._record_field_change(composite_id, field, new_value_str, current_time)
        
        return changes_detected

    def _record_field_change(self, composite_id, field_name, new_value, uptime):
        """记录字段变化到历史表"""
        try:
            history_table = f"{field_name}_history"
            insert_query = f"""
            INSERT INTO {history_table} (id, field_value, uptime)
            VALUES (?, ?, ?)
            """
            self.session.execute(insert_query, (composite_id, new_value, uptime))
            mylog_hd.info(f"Recorded change in {history_table}: {composite_id} -> {new_value}")
            
        except Exception as e:
            mylog_hd.error(f"Failed to record field change: {traceback.format_exc()}")

    def insert_or_update_data_cookie(self, data):
        """插入或更新data_cookie表中的数据"""
        try:
            # 构建复合ID: uid|sitename
            composite_id = f"{data.get('id', '')}|{data.get('sitename', '')}"
            
            # 获取现有数据
            existing_data = self.get_existing_data(composite_id)
            
            # 对比字段变化
            if existing_data:
                changes_detected = self.compare_and_update_fields(composite_id, data, existing_data)
                if changes_detected:
                    mylog_hd.info(f"Changes detected for {composite_id}, updating data_cookie")
                else:
                    mylog_hd.info(f"No changes detected for {composite_id}")
            else:
                mylog_hd.info(f"New record for {composite_id}, inserting into data_cookie")
            
            # 插入或更新data_cookie表
            insert_query = """
            INSERT INTO data_cookie (
                id, uid, site_name, name, verified_reason, description, content,
                gender, ip_region, followers_count, friends_count,
                identity, identity_standerd, age, three_new_identity,
                community, processed_time, url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # 准备数据
            values = (
                composite_id,
                data.get('id', ''),
                data.get('sitename', ''),
                data.get('user_name', ''),
                data.get('verified_reason', ''),
                data.get('description', ''),
                data.get('content', ''),
                data.get('gender', ''),
                data.get('ip_region', ''),
                data.get('followers_count', ''),
                data.get('friends_count', ''),
                data.get('identity', []),
                data.get('identity_standerd', []),
                data.get('age', []),
                data.get('three_new_identity', ''),
                data.get('community', ''),
                datetime.now(),
                data.get('url', '')
            )
            
            self.session.execute(insert_query, values)
            mylog_hd.info(f"Updated data_cookie for: {composite_id}")
            return True
            
        except Exception as e:
            mylog_hd.error(f"Failed to insert/update data_cookie: {traceback.format_exc()}")
            return False

    def close(self):
        """关闭连接"""
        if self.session:
            self.session.cluster.shutdown()
            mylog_hd.info("ScyllaDB connection closed")cla
ss ProducerMQ:
    """RocketMQ生产者"""
    def __init__(self, host, groupid):
        self.host = host
        self.groupid = groupid
        self.producer = DefaultMQProducer(self.groupid)
        self.producer.namesrv_addr = self.host
        self.producer.send_latency_fault_enable = False
        self.producer.max_message_size = 30000000
        self.producer.start()

    def send2mq(self, info_json, key, topic):
        msg = Message(topic=topic, body=info_json)
        msg.wait_store_msg_ok = True
        msg.keys = key
        error = ""
        for _ in range(3):
            try:
                self.producer.sendOneway(msg=msg)
                return ""
            except Exception as e:
                mylog_hd.error(f"MQ send error: {e}")
                error = str(e)
        return error

    def close(self):
        self.producer.shutdown()

# 读取Excel身份映射
def load_identity_mapping(excel_path="final_stanterd.xlsx"):
    df_excel = pd.read_excel(excel_path, engine='openpyxl')
    identity_map = dict(zip(df_excel["原始身份"], df_excel["最终身份"]))
    return identity_map

identity_map = load_identity_mapping()

class Drawing:
    """数据处理类 - 修改为ScyllaDB处理"""
    def __init__(self):
        self.redis_cache_identity_bloom = config["redis"]["redis_url_identity_bloom"]
        self.identity_bloom_key = config["redis"]["identity_bloom_key"]
        self.age_cache = defaultdict(list)
        self.bloom_filter = BloomFilter(self.redis_cache_identity_bloom, self.identity_bloom_key)
        self.scylla_handler = ScyllaDBHandler()
        # 使用配置中的新MQ topic
        new_topic = config["topic"]["processed_user_data"]
        new_producer_group = config["producer_group"]["processed_user_data"]
        self.mq_producer = ProducerMQ(config["mq_url"], new_producer_group)  
  def run(self, datas):
        """处理数据并存储到ScyllaDB，然后发送到新的MQ"""
        inputs = []
        try:
            for name_index, yaunshi_data in enumerate(datas):
                dd = {}
                yaunshi_data["input_id"] = str(name_index)
                yaunshi_data["user_name"] = yaunshi_data["name"]
                del yaunshi_data["name"]
                
                if yaunshi_data["user_name"]:
                    dd["账号名"] = yaunshi_data["user_name"]
                if yaunshi_data["verified_reason"]:
                    dd["账号认证原因"] = yaunshi_data["verified_reason"]
                if yaunshi_data["description"]:
                    dd["账号自我介绍"] = yaunshi_data["content"] + yaunshi_data["description"]
                
                if dd == {}:
                    continue
                    
                dd['input_id'] = str(name_index)
                inputs.append(json.dumps(dd, ensure_ascii=False))

            mylog_hd.info(json.dumps(inputs, ensure_ascii=False, indent=2))
            results, info_response_id, response_content = get_user_infos(USER_INFOS, json.dumps(inputs, ensure_ascii=False, indent=2), mylog_hd)
            
            if info_response_id == 0:
                mylog_hd.error(f"请求出错-{json.dumps(inputs, ensure_ascii=False, indent=2)}")
                return

            if len(results) != len(inputs):
                mylog_hd.error(f"结果数量不一致-{info_response_id}-{json.dumps(inputs, ensure_ascii=False, indent=2)}--{response_content}")

            # 构建标记编号key
            results_lookup = {}
            mylog_hd.info(f"请求id-{info_response_id}")
            mylog_hd.info(json.dumps(results, ensure_ascii=False, indent=2))
            
            for result in results:
                results_lookup[str(result['input_id'])] = result

            # 处理每条数据
            for data in datas:
                mylog_hd.info(f"input_id-{data}")
                idx = data["input_id"]
                
                if idx in results_lookup:
                    final_result = results_lookup[idx]
                    data["info_response_id"] = info_response_id
                    data["identity"] = final_result.get('identity', [])
                    
                    # 身份标准化处理
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
                    
                    data['name'] = final_result.get('name', [])
                    data['age'] = final_result.get('age', [])
                    
                    # 三元组身份识别
                    if data['content'] != "":
                        three_news = get_kind(data['content'])
                    else:
                        three_news = {"identity": "", "identity2": "", "log": ""}
                    
                    data['three_new_identity'] = three_news['identity']
                    data['community'] = three_news['identity2']
                    
                    # 存储到ScyllaDB并检测变化
                    try:
                        success = self.scylla_handler.insert_or_update_data_cookie(data)
                        if success:
                            mylog_hd.info(f"Successfully processed in ScyllaDB: {data['sitename']}-{data['id']}")
                            
                            # 发送到新的MQ
                            mq_data = {
                                "source": "scylla_processed",
                                "data": data,
                                "processed_time": datetime.now().isoformat()
                            }
                            
                            error = self.mq_producer.send2mq(
                                json.dumps(mq_data, ensure_ascii=False),
                                f"{data['sitename']}^{data['id']}",
                                config["topic"]["processed_user_data"]
                            )
                            
                            if not error:
                                mylog_hd.info(f"Successfully sent to MQ: {data['sitename']}-{data['id']}")
                            else:
                                mylog_hd.error(f"Failed to send to MQ: {error}")
                        else:
                            mylog_hd.error(f"Failed to process in ScyllaDB: {data['sitename']}-{data['id']}")
                            
                    except Exception as e:
                        mylog_hd.error(f"ScyllaDB processing error: {traceback.format_exc()}")
                    
                    # 添加到bloom filter
                    bloom_value = {
                        "sitename": data["sitename"],
                        "id": data["id"],
                        "url": data["url"],
                        "name": data["user_name"]
                    }
                    bloom_value = json.dumps(bloom_value, ensure_ascii=False, sort_keys=True)
                    self.bloom_filter.add_value(bloom_value)
                    mylog_hd.info(f"添加bloom-{bloom_value}")
                    
                else:
                    mylog_hd.error(f"未被处理的数据为-{info_response_id}-{json.dumps(data, ensure_ascii=False, indent=2)}")
                    
        except Exception as e:
            mylog_hd.exception(f"Error processing line: {traceback.format_exc()}")
            return Nonecl
ass DrawingWrapper:
    def __init__(self):
        self.drawing = Drawing()

    def async_run(self, datas):
        try:
            return self.drawing.run(datas)
        except Exception as e:
            mylog_hd.exception(f"Worker error: {traceback.format_exc()}")

class MyListener(MessageListenerConcurrently):
    """MQ消息监听器 - 保持原有逻辑"""
    def __init__(self):
        self.redis_cache_identity_bloom = config["redis"]["redis_url_identity_bloom"]
        self.identity_bloom_key = config["redis"]["identity_bloom_key"]
        self.redis_quchong = redis.from_url(config["redis"]["redis_quchong"])
        self.REDIS_EXPIRE_SECONDS = 20 * 60
        
        self.md = Matcher()
        self.md.load_from_collection([
            "外卖员", "外卖日记", "外卖行业", "外卖小哥不容易", "偷外卖的狗",
            "网约车", "滴滴司机", "货车司机", "开货车的", "外卖被偷"
        ])
        
        self.bloom_filter = BloomFilter(self.redis_cache_identity_bloom, self.identity_bloom_key)

    def consume_message(self, msgs):
        for msg in msgs:
            try:
                data = json.loads(msg.body.decode('utf-8', 'ignore'))
                if data["index_suffix"].startswith("rank"):
                    continue
                if data["index_suffix"] in ["oversea", "youtube", "facebook", "twitter", "titok"]:
                    continue
                    
                data = data["data"]
                user = data.get("user")
                if not user or not user.get("uid"):
                    continue
                    
                url = data.get("url", "    ")
                if url[-4:] in ["#ocr", "#asr", "#att"]:
                    continue
                    
                site_name = str(data.get("gather", {}).get("site_name", ""))
                uid = str(user["uid"])
                content = data.get("content", "")
                
                # 构建队列数据
                queue_data = {
                    "id": uid,
                    "url": url,
                    "content": content,
                    "sitename": site_name,
                    'name': user.get("name", ""),
                    "verified_reason": user.get("verified_reason", ""),
                    "description": user.get("description", ""),
                    'gender': user.get("gender", ""),
                    'ip_region': user.get("ip_region", []),
                    'followers_count': str(user.get("followers_count", 0)),
                    'friends_count': str(user.get("friends_count", 0))
                }
                
                if queue_data["ip_region"] != []:
                    queue_data["ip_region"] = queue_data["ip_region"][0]
                
                # 检查内容匹配
                if self.md.findall(''.join(queue_data["content"])) == []:
                    continue
                
                # 检查bloom filter
                user_data = {
                    "sitename": site_name,
                    "id": uid,
                    "url": url,
                    "name": user.get("name", "")
                }
                bloom_value = json.dumps(user_data, ensure_ascii=False, sort_keys=True)
                
                if self.bloom_filter.is_double(bloom_value):
                    mylog_hd.error(f"重复bloom-{user_data['sitename']}-{user_data['id']}")
                    continue
                
                # 检查必要字段
                dd = {}
                if user_data["name"]:
                    dd["账号名"] = user_data["name"]
                if queue_data["verified_reason"]:
                    dd["账号认证原因"] = queue_data["verified_reason"]
                if queue_data["description"]:
                    dd["账号自我介绍"] = queue_data["description"]
                
                if dd == {}:
                    continue
                
                queue_data['url'] = data.get('url', '')
                TASK_QUEUE.put(queue_data, block=True)
                
            except queue.Full:
                mylog_hd.warning("Task queue full, message dropped")
            except Exception as e:
                mylog_hd.error(f"Message processing error: {traceback.format_exc()}")if __na
me__ == "__main__":
    # 初始化ScyllaDB和MQ生产者
    mylog_hd.info("Starting ScyllaDB processing service...")
    
    # 创建MQ消费者
    consumer = DefaultMQPushConsumer(config["consumer_group"]["user_graph_uniq_user"])
    consumer.namesrv_addr = config["mq_url"]
    consumer.consume_thread_num = 1
    consumer.consume_message_batch_max_size = 1
    consumer.registerMessageListener(MyListener())
    consumer.subscribe(config["topic"]["spider_data"], "*")
    consumer.start()
    
    time.sleep(3)
    mylog_hd.info("MQ Consumer started successfully")

    def worker():
        """工作线程 - 处理队列中的数据"""
        dw = DrawingWrapper()
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
                
                # 批量处理
                if len(datas) >= 20:
                    mylog_hd.info(f"Processing batch of {len(datas)} items")
                    dw.async_run(datas)
                    datas = []
                    keys = set()
                    
            except queue.Empty:
                # 处理剩余数据
                if datas:
                    mylog_hd.info(f"Processing remaining {len(datas)} items")
                    dw.async_run(datas)
                    datas = []
                    keys = set()
                continue
            except Exception as e:
                mylog_hd.error(f"Worker thread error: {traceback.format_exc()}")

    # 启动工作线程
    for i in range(20):
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        mylog_hd.info(f"Started worker thread {i+1}")

    mylog_hd.info("All worker threads started successfully")
    print("ScyllaDB processing service started successfully!")

    # 信号处理
    def signal_handler(signum, frame):
        mylog_hd.info("Received shutdown signal, cleaning up...")
        try:
            # 关闭ScyllaDB连接和MQ生产者
            if 'dw' in locals():
                dw.drawing.scylla_handler.close()
                dw.drawing.mq_producer.close()
        except:
            pass
        import os
        os._exit(0)

    import signal
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        mylog_hd.info("Shutting down...")
        signal_handler(None, None)
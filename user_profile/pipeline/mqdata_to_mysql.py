import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
import json
import pandas as pd
import mysql.connector
from datetime import datetime
from mysql.connector import Error, InterfaceError, DatabaseError, connect
from mysql.connector import errorcode
from utils.about_log import config_log
from rocketmq import (
    DefaultMQProducer,
    DefaultMQPushConsumer,
    Message,
    DefaultMQPushConsumer,
    MessageListenerConcurrently,
)

sql_config={
        "host": "192.168.19.65",
        "user": "buser",
        "password": "p3jnmja3",
        "database": "user_profile",
        "table_name":"profile_table1"
}


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

count=0
def send_data_task(source_data):
    global count
    """
    转存数据
    :param source_data:
    :return:
    """
    mq_pd.send2mq(json.dumps(source_data,ensure_ascii=False),source_data["id"],"identity_topic")
    count+=1
    my_log_hd.info("写入mq数据量目前为{}".format(count))


my_log_hd = config_log("mqdata_to_mysql","INFO")
inserted_count = 0
updated_count = 0
count3=0


# 读取Excel身份映射
def load_identity_mapping(excel_path="final_stanterd.xlsx"):
    df_excel = pd.read_excel(excel_path,engine='openpyxl')
    identity_map = dict(zip(df_excel["原始身份"], df_excel["最终身份"]))
    return identity_map


def count_unique_id_site(data_list):
    unique_set = set()

    for item in data_list:
        id_val = item.get("id")
        site_name = item.get("sitename")

        if id_val is not None and site_name is not None:
            combined = f"{id_val}_{site_name}"
            unique_set.add(combined)

    return len(unique_set)


def clean_json_data(data):
    """
    清洗 JSON 数据：
    - 去除字段名前后空格
    - 处理重复字段：如果字段重复，保留 value 不是 [] 或 '' 的那个
    """
    cleaned = {}

    for key, value in data.items():
        clean_key = key.strip()
        if not clean_key:
            continue  # 跳过空字段名

        # 判断是否已有该字段
        existing_value = cleaned.get(clean_key)

        if existing_value is None:
            # 当前字段是第一次出现，直接放入
            cleaned[clean_key] = value
        else:
            # 已存在，判断当前 value 是否“有效”
            if not isinstance(value, (list, str)):
                cleaned[clean_key] = value
            elif isinstance(value, list) and len(value) > 0:
                cleaned[clean_key] = value
            elif isinstance(value, str) and value.strip() != '':
                cleaned[clean_key] = value
            # 否则保留原来的值（当前值无效）

    return cleaned

identity_map = load_identity_mapping()
# class AddData():
#     def __init__(self, sql_config):
#         try:
#             self.connection = mysql.connector.connect(
#                 host=sql_config['host'],
#                 user=sql_config['user'],
#                 password=sql_config['password'],
#                 database=sql_config['database']
#             )
#             if self.connection.is_connected():
#                 print("成功连接到 MySQL 数据库")
#         except Error as err:
#             if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
#                 print("认证失败：用户名或密码错误")
#             elif err.errno == errorcode.ER_BAD_DB_ERROR:
#                 print("数据库不存在")
#             else:
#                 print(err)
#
#     import json
#
#     def deal(self, source_data):
#         global count,count2,count3
#         #加载映射表
#         identity_map = load_identity_mapping()
#         retry_times = 3  # 最多重试3次
#         delay = 2  # 每次重试间隔2秒
#         for attempt in range(retry_times + 1):
#             cursor = None
#             try:
#                 if not self.connection or not self.connection.is_connected():
#                     my_log_hd.info("连接断开，正在重连...")
#                     self._connect()
#                     if not self.connection:
#                         raise Exception("重连失败")
#
#                 cursor = self.connection.cursor()
#
#                 # ✅ 1. 清洗数据：所有 None → "", 空 list → ""
#                 processed_data = {}
#                 for key, value in source_data.items():
#                     # ✅ 修复1：用 = 而不是 ==
#                     if value is None:
#                         processed_data[key] = ""
#                     elif isinstance(value, list):
#                         if key == 'age':
#                             if len(value) >= 2:
#                                 processed_data['age_start'] = value[0]
#                                 processed_data['age_end'] = value[1]
#                             processed_data[key] = ", ".join(str(v) for v in value) if value else ""
#                         else:
#                             # ✅ 修复2：空列表也转为 ""，不要 None
#                             processed_data[key] = ",".join(map(str, value)) if value else ""
#                     elif isinstance(value, (dict, set, tuple)):
#                         processed_data[key] = json.dumps(value, ensure_ascii=False)
#                     else:
#                         processed_data[key] = value if value is not None else ""
#
#                 # ✅ 2. 构建 insert_data，统一用 get 并处理 None
#                 insert_data = {}
#                 keys_to_get = [
#                     "id", "sitename", "name", "verified_reason", "description",
#                     "user_name", "org", "industry", "contact", "birthday",
#                     "age_start", "age_end", "log", "log1", "log2", "age"
#                 ]
#                 for k in keys_to_get:
#                     val = processed_data.get(k)
#                     insert_data[k] = val if val is not None else ""
#
#                 # ✅ 3. 特殊处理 identity
#                 identity_raw = processed_data.get("identity", "")
#                 # 确保 identity_raw 是字符串
#                 identity_str = str(identity_raw) if identity_raw is not None else ""
#
#                 if not identity_str.strip():
#                     insert_data['identity_standerd'] = ""
#                 elif ',' not in identity_str:
#                     mapped = identity_map.get(identity_str.strip(), "其他")
#                     insert_data['identity_standerd'] = [mapped]
#                 else:
#                     items = [x.strip() for x in identity_str.split(',') if x.strip()]
#                     mapped_list = [identity_map.get(item, "其他") for item in items]
#                     insert_data['identity_standerd'] = list(set(mapped_list))
#
#                 insert_data["identity"] = identity_str  # 保存原始值
#
#                 # ✅ 4. 发送到 MQ（只在有归一身份时）
#                 final_identity = insert_data['identity_standerd']
#                 if final_identity and final_identity != "":
#                     # ✅ 注意：MQ 可以传 list，但入库要转字符串
#                     send_data_task({
#                         "id": insert_data['id'],
#                         "sitename": insert_data['sitename'],
#                         "user_name": insert_data['user_name'],
#                         "final_identity": final_identity
#                     })
#
#                 # ✅ 5. 准备入库：将 list/dict 转为 JSON 字符串
#                 db_values = []
#                 for v in insert_data.values():
#                     if isinstance(v, (list, dict)):
#                         db_values.append(json.dumps(v, ensure_ascii=False))
#                     else:
#                         db_values.append(v)
#
#                 # ✅ 6. 执行插入
#                 columns = ', '.join(insert_data.keys())
#                 placeholders = ', '.join(['%s'] * len(db_values))
#                 sql = f"INSERT IGNORE INTO {sql_config['table_name']} ({columns}) VALUES ({placeholders})"
#                 cursor.execute(sql, db_values)
#                 self.connection.commit()
#
#                 count += 1
#                 my_log_hd.info("成功添加数据一条，当前数据量{}".format(count))
#                 break  # 成功跳出重试
#
#             except Error as e:
#                 message_e=str(e)
#                 try:
#                     if 'specified twice' in message_e:
#                         my_log_hd.info("因字段重复，处理后重新入库")
#                         processdata=clean_json_data(processed_data)
#                         columns = ', '.join(processdata.keys())
#                         placeholders = ', '.join(['%s'] * len(processdata))
#                         sql = f"INSERT IGNORE INTO {sql_config['table_name']} ({columns}) VALUES ({placeholders})"
#                         cursor.execute(sql, list(processdata.values()))
#                         count += 1
#                         my_log_hd.info("成功添加数据一条，当前数据量{}".format(count))
#                         self.connection.commit()
#                         break
#                     else:
#                         count2 += 1
#                         my_log_hd.info("失败一条数据，失败数据量{}".format(count2))
#                         my_log_hd.info("失败数据为{}".format(source_data))
#                         my_log_hd.info("失败原因{}".format(e))
#                 except Exception as e:
#                     my_log_hd.info("失败原因{}".format(e))
#
#             except InterfaceError as e:
#
#                 # 连接异常，比如 "MySQL Connection not available"
#
#                 my_log_hd.error(f"接口错误: {e}，第 {attempt + 1} 次重试...")
#
#                 time.sleep(delay)
#
#                 continue
#
#
#             except DatabaseError as e:
#
#                 # 数据库相关错误（如死锁、超时等）
#
#                 my_log_hd.error(f"数据库错误: {e}")
#
#                 self.connection.rollback()
#
#                 count2 += 1
#
#                 my_log_hd.info("失败一条数据，失败数据量{}".format(count2))
#
#                 my_log_hd.info("失败原因{}".format(e))
#
#                 return False
#
#
#             except Error as e:
#
#                 # 其他 mysql-connector 错误
#
#                 my_log_hd.error(f"数据库操作错误: {e}")
#
#                 self.connection.rollback()
#
#                 count2 += 1
#
#                 my_log_hd.info("失败一条数据，失败数据量{}".format(count2))
#
#                 my_log_hd.info("失败原因{}".format(e))
#                 return False
#
#             except Exception as e:
#                 my_log_hd.error(f"未知错误: {e}")
#                 self.connection.rollback()
#                 count2 += 1
#                 my_log_hd.info("失败一条数据，失败数据量{}".format(count2))
#                 my_log_hd.info('失败数据为{}'.format(processed_data))
#                 my_log_hd.info("失败原因{}".format(e))
#                 return False

class AddData():
    def __init__(self, sql_config, batch_size=1000):
        self.sql_config = sql_config
        self.batch_size = batch_size
        self.connection = None
        self.buffer = []  # 缓存待插入的数据
        self._connect()

    def _connect(self):
        """建立数据库连接"""
        try:
            self.connection = mysql.connector.connect(
                host=self.sql_config['host'],
                user=self.sql_config['user'],
                password=self.sql_config['password'],
                database=self.sql_config['database']
            )
            if self.connection.is_connected():
                my_log_hd.info("成功连接到 MySQL 数据库")
        except Error as err:
            my_log_hd.error(f"数据库连接失败: {err}")
            self.connection = None

    def _reconnect(self):
        """重连机制"""
        try:
            if self.connection:
                self.connection.close()
        except:
            pass
        time.sleep(2)
        self._connect()

    def deal(self, source_data):
        global count3
        count3 += 1
        if count3 % 100 == 0:
            my_log_hd.info("当前获取数据量: {}".format(count3))

        # 1. 清洗并构建单条数据
        cleaned_row = self._process_single_data(source_data)
        if cleaned_row:
            self.buffer.append(cleaned_row)

        # 2. 判断是否达到批量阈值
        if len(self.buffer) >= self.batch_size:
            self.flush()  # 执行批量写入

    def _process_single_data(self, source_data):
        """处理单条数据，返回可用于入库的字典"""
        try:
            #identity_map = load_identity_mapping()
            processed_data = {}

            for key, value in source_data.items():
                if value is None:
                    processed_data[key] = ""
                elif isinstance(value, list):
                    if key == 'age':
                        if len(value) >= 2:
                            processed_data['age_start'] = value[0]
                            processed_data['age_end'] = value[1]
                        processed_data[key] = ", ".join(str(v) for v in value) if value else ""
                    else:
                        processed_data[key] = ",".join(map(str, value)) if value else ""
                elif isinstance(value, (dict, set, tuple)):
                    processed_data[key] = json.dumps(value, ensure_ascii=False)
                else:
                    processed_data[key] = str(value) if value is not None else ""

            # 构建 insert_data
            insert_data = {}
            keys_to_get = [
                "id", "sitename", "name", "verified_reason", "description",
                "user_name", "org", "industry", "contact", "birthday",
                "age_start", "age_end", "log", "log1", "log2", "age"
            ]
            for k in keys_to_get:
                val = processed_data.get(k)
                insert_data[k] = val if val is not None else ""

            # 处理 identity
            identity_raw = processed_data.get("identity", "")
            identity_str = str(identity_raw) if identity_raw is not None else ""

            if not identity_str.strip():
                insert_data['identity_standerd'] = ""
            elif identity_str=="":
                insert_data['identity_standerd'] = ""
            elif ',' not in identity_str:
                mapped = identity_map.get(identity_str.strip(), "其他")
                insert_data['identity_standerd'] = [mapped]
            else:
                items = [x.strip() for x in identity_str.split(',') if x.strip()]
                mapped_list = [identity_map.get(item, "其他") for item in items]
                insert_data['identity_standerd'] = list(set(mapped_list))

            insert_data["identity"] = identity_str

            # ✅ 发送到 MQ（可选）
            final_identity = insert_data['identity_standerd']
            if final_identity and final_identity != "":
                send_data_task({
                    "id": insert_data['id'],
                    "sitename": insert_data['sitename'],
                    "user_name": insert_data['user_name'],
                    "final_identity": final_identity
                })

            return insert_data

        except Exception as e:
            my_log_hd.error(f"单条数据处理失败: {e}")
            return None

    def flush(self):
        """将 buffer 中的数据批量写入数据库"""
        if not self.buffer:
            return

        global inserted_count, updated_count

        retry_times = 3
        for attempt in range(retry_times + 1):
            cursor = None
            try:
                if not self.connection or not self.connection.is_connected():
                    my_log_hd.info("连接断开，正在重连...")
                    self._reconnect()
                    if not self.connection:
                        raise Exception("重连失败")

                cursor = self.connection.cursor()

                # 准备批量数据
                rows_to_insert = []
                for data in self.buffer:
                    row = []
                    for v in data.values():
                        if isinstance(v, (list, dict)):
                            row.append(json.dumps(v, ensure_ascii=False))
                        else:
                            row.append(v)
                    rows_to_insert.append(row)

                # # 构建 SQL
                sample_data = self.buffer[0]
                columns = ', '.join(sample_data.keys())
                placeholders = ', '.join(['%s'] * len(sample_data))
                # sql = f"INSERT IGNORE INTO {sql_config['table_name']} ({columns}) VALUES ({placeholders})"
                #
                # # 执行批量插入
                # cursor.executemany(sql, rows_to_insert)
                # self.connection.commit()
                #
                # count += len(self.buffer)
                # my_log_hd.info(f"批量写入成功，本次写入 {len(self.buffer)} 条，累计成功 {count} 条")
                #
                # # 清空 buffer
                # self.buffer.clear()

                # 单条入库
                # 构建 SELECT 语句用于检查是否存在（假设表有主键或唯一索引字段，例如 'id' 或 'name' 等）
                # 注意：你需要根据实际表结构定义哪些字段用于判断“重复”
                duplicate_keys = ["sitename","id"]  # 替换为你的唯一键字段，如 ['id'] 或 ['name', 'email'] 等
                # 示例：duplicate_keys = ['id']
                #       WHERE id = %s

                # 构建 SELECT 检查语句
                where_conditions = ' AND '.join([f"{key} = %s" for key in duplicate_keys])
                select_sql = f"SELECT 1 FROM {sql_config['table_name']} WHERE {where_conditions}"

                # 构建 INSERT 语句
                insert_sql = f"INSERT INTO {sql_config['table_name']} ({columns}) VALUES ({placeholders})"

                # 构建 UPDATE 语句（更新除唯一键外的所有字段，或全部更新）
                # 如果你想更新所有字段：
                set_updates = ', '.join([f"{key} = %s" for key in sample_data.keys()])
                update_sql = f"UPDATE {sql_config['table_name']} SET {set_updates} WHERE {where_conditions}"


                for i, row_data in enumerate(rows_to_insert):
                    data_dict = self.buffer[i]
                    #data_dict['identity_standerd']=json.dumps(data_dict['identity_standerd'],ensure_ascii=False)
                    data_dict['identity_standerd']=','.join(data_dict['identity_standerd'])
                    try:
                        # 提取唯一键值
                        key_values = [data_dict[key] for key in duplicate_keys]

                        # 检查是否存在
                        cursor.execute(select_sql, key_values)
                        exists = cursor.fetchone()

                        if exists:
                            # 执行更新：所有字段都更新（包括唯一键也可以，但一般不建议改唯一键）
                            update_values = list(data_dict.values()) + key_values  # SET 值 + WHERE 条件值
                            cursor.execute(update_sql, update_values)
                            updated_count += 1
                            my_log_hd.info(
                                f"数据已更新: {dict(zip(sample_data.keys(), row_data))} "
                                f"-> 基于 {dict(zip(duplicate_keys, key_values))}"
                            )
                        else:
                            # 执行插入
                            cursor.execute(insert_sql, row_data)
                            inserted_count += 1
                            my_log_hd.debug(f"数据已插入: {dict(zip(sample_data.keys(), row_data))}")

                        # 提交事务
                        self.connection.commit()

                    except Exception as e:
                        my_log_hd.error(f"数据处理失败: {dict(zip(sample_data.keys(), row_data))} -> 原因: {str(e)}")
                        self.connection.rollback()

                my_log_hd.info(f"逐条写入完成，累计更新 {updated_count} 条，累计插入{inserted_count}条")
                self.buffer.clear()
                break

            except InterfaceError as e:
                my_log_hd.error(f"连接异常，第 {attempt + 1} 次重试: {e}")
                time.sleep(2)
                continue

            except Error as e:
                my_log_hd.error(f"MySQL 错误: {e}")
                my_log_hd.error(f"批量写入失败，共 {len(self.buffer)} 条数据丢失")
                self.buffer.clear()
                break

            # finally:
            #     if cursor:
            #         cursor.close()

    def close(self):
        """关闭连接前确保所有数据都写入"""
        self.flush()  # 写入剩余数据
        if self.connection and self.connection.is_connected():
            self.connection.close()
        my_log_hd.info("数据库连接已关闭")


    def run(self, source_data):
        # count_result=count_unique_id_site(source_data)
        # my_log_hd.info("当前使用id+sitename去重后的总数据量{}".format(count_result))
        self.deal(source_data)



class MyListener(MessageListenerConcurrently):
    def __init__(self):
        self.add_event = AddData(sql_config)

    def consume_message(self, msgs):
        for msg in msgs:
            data = json.loads(msg.body.decode('utf-8', 'ignore'))
            self.add_event.run(data)
        # data_list=[]
        # for msg in msgs:
        #     data = json.loads(msg.body.decode('utf-8', 'ignore'))
        #     my_log_hd.info(data['id'])
        #     data_list.append(data)
        #     if len(data_list)%1000==0:
        #         self.add_event.run(data_list)
        #         my_log_hd.info("当前数据未去重总量".format(len(data_list)))
        #     else:
        #         continue


if __name__ == '__main__':
    mq_pd = ProducerMQ("yqms-rocketmq-broker1-master.istarshine.net.cn:9876;yqms-rocketmq-broker2-master.istarshine.net.cn:9876",
                       "liuruixi_indert_data")
    consumer = DefaultMQPushConsumer("lrx_group_mysql")
    consumer.namesrv_addr = "yqms-rocketmq-broker1-master.istarshine.net.cn:9876;yqms-rocketmq-broker2-master.istarshine.net.cn:9876"
    consumer.consume_thread_num = 1
    consumer.registerMessageListener(MyListener())
    consumer.subscribe( "user_graph_drawed_result_topic", "*")
    consumer.start()
    print("程序启动完成")
    while True:
        time.sleep(3600)
import pymysql
import json
from typing import Dict, Optional, Tuple, Any
from utils.config import *
from opensearchpy import OpenSearch
from datetime import datetime


class ScenarioManager:
    """
    用于管理 Scenario_table 表的插入和查询操作。
    """

    def __init__(self):

        self.config = sql_config
        self.conn = pymysql.connect(**self.config)
        self.es_client=OpenSearch(**opensearch_config)

    def insert_scenario(
        self,
        type_val: str,
        scenario: str,
        direct_query: Dict[Any, Any],
        single_query: Optional[Dict[Any, Any]] = None,
        new_feature: Optional[str] = None
    ) -> Optional[int]:

        try:

            cursor = self.conn.cursor()

            # SQL 插入语句 (id 为 AUTO_INCREMENT，create_time 有 DEFAULT)
            insert_sql = """
            INSERT INTO Scenario_table 
            (`type`, `scenario`, `direct_query`, `single_query`, `new_feature`)
            VALUES (%s, %s, %s, %s, %s)
            """

            cursor.execute(insert_sql, (
                type_val,
                scenario,
                json.dumps(direct_query,ensure_ascii=False),     # pymysql 自动处理 dict -> JSON
                json.dumps(single_query,ensure_ascii=False),     # 可以为 dict 或 None
                new_feature       # 可以为 str 或 None
            ))

            new_id = cursor.lastrowid
            self.conn.commit()
            print(f"✅ 数据插入成功！ID: {new_id}")
            return new_id

        except pymysql.Error as e:
            if self.conn:
                self.conn.rollback()
            print(f"❌ 插入数据时发生数据库错误: {e}")
            return None
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"❌ 插入数据时发生其他错误: {e}")
            return None
        finally:
            if self.conn and self.conn.open:
                cursor.close()
                self.conn.close()

    def query_queries_by_id(self, record_id: int) -> Optional[Tuple[Dict[Any, Any], Optional[Dict[Any, Any]]]]:
        """
        根据记录 ID 查询 direct_query 和 single_query 字段。

        Args:
            record_id (int): 记录的主键 ID

        Returns:
            tuple or None: 成功时返回 (direct_query_dict, single_query_dict_or_None) 的元组，
                         如果记录不存在或出错，则返回 None。
        """
        try:
            connection = self.conn
            cursor = connection.cursor()

            # SQL 查询语句
            select_sql = """
            SELECT direct_query, single_query,search_state 
            FROM Scenario_table 
            WHERE id = %s
            """

            cursor.execute(select_sql, (record_id,))
            result = cursor.fetchone()

            if result is None:
                print(f"⚠️  未找到 ID 为 {record_id} 的记录。")
                return None

            # 结果是元组 (direct_query_json, single_query_json)
            # pymysql 会自动将 JSON 字符串反序列化为 Python dict/list
            direct_query_data = result[0]  # 已经是 dict
            single_query_data = result[1]  # 可能是 dict 或 None
            search_state = result[2]

            print(f"✅ 成功查询到 ID {record_id} 的数据。")
            return direct_query_data, single_query_data, search_state

        except pymysql.Error as e:
            print(f"❌ 查询数据时发生数据库错误: {e}")
            return None
        except Exception as e:
            print(f"❌ 查询数据时发生其他错误: {e}")
            return None
        finally:
            if connection and connection.open:
                cursor.close()
                connection.close()


    def query_from_opensearch_by_direct_query(self, record_id: int, index) -> Optional[Dict]:

        # 1. 从 MySQL 获取 direct_query 配置
        query_data = self.query_queries_by_id(record_id)
        if not query_data:
            print(f"❌ 无法获取 ID {record_id} 的查询配置，无法执行 OpenSearch 查询。")
            return None

        direct_query_dict, _,state = query_data

        # 2. 提取真正的查询体
        if "query" not in direct_query_dict:
            print(f"❌ direct_query 配置中缺少 'query' 键，无法执行查询。")
            return None

        os_query_body = json.loads(direct_query_dict)['query_dsl']  # 这个字典将被发送给 OpenSearch
        print(os_query_body)
        try:
            os_client = self.es_client

            # 👉 执行搜索
            response = os_client.search(
                index=index,  # 使用传入的索引模式
                body=os_query_body  # 使用提取出的查询体
            )
            if state=='历史':
                history_result=self.parse_identity_changes(response)
                for item in history_result:
                    print(f"{item['uid']} 在 {item['updated_at']} 历史信息为: {item['value']}")
                return response
            else:
                total_hits = response['hits']['total']['value']
                print(f"✅ 成功从 OpenSearch 查询数据！索引: {index}, 总命中数: {total_hits}")
                if total_hits!=0:
                    for i, hit in enumerate(response['hits']['hits'], 1):
                        print(f"\n{i}. 文档信息")
                        print("-" * 40)
                        print(f"  索引: {hit['_index']}")
                        print(f"  ID:   {hit['_id']}")
                        print(f"  分数: {hit['_score']:.4f}")

                        # 打印 _source 中的所有字段
                        source = hit['_source']
                        print("  数据:")
                        # 使用 json.dumps 格式化输出，保证可读性
                        print(json.dumps(source, ensure_ascii=False, indent=4))
                return response

        except Exception as e:
            error_info = f"Status: {e.status_code}, Error: {e.error}"
            print(f"❌ OpenSearch 查询执行失败: {error_info}")
            return None
        finally:
            if os_client:
                # OpenSearch 客户端通常不需要显式 close，但可以调用
                # os_client.close() # 可选
                pass


    def parse_identity_changes(self, response):
        """
        解析查询结果，返回每个账号在指定时间内最后一次 identity 变更
        """
        # 临时存储：key=uid, value=最新的记录
        latest_per_uid = {}

        for hit in response["hits"]["hits"]:
            uid = hit["_source"]["uid"]

            if "inner_hits" not in hit:
                continue

            nested_hits = hit["inner_hits"]["identity_history"]["hits"]["hits"]

            for nh in nested_hits:
                source = nh["_source"]
                value = source.get("value")
                updated_at_str = source.get("updated_at")

                # 跳过空数据
                if not value or not updated_at_str:
                    continue

                # 解析时间
                try:
                    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                except Exception as e:
                    print(f"⚠️ 时间解析失败 {updated_at_str}: {e}")
                    continue

                # 判断是否为当前 uid 的最新记录
                if uid not in latest_per_uid:
                    latest_per_uid[uid] = {
                        "uid": uid,
                        "value": value,
                        "updated_at": updated_at_str
                    }
                else:
                    # 比较时间，保留更晚的
                    existing_time = datetime.fromisoformat(
                        latest_per_uid[uid]["updated_at"].replace("Z", "+00:00")
                    )
                    if updated_at > existing_time:
                        latest_per_uid[uid] = {
                            "uid": uid,
                            "value": value,
                            "updated_at": updated_at_str
                        }

        # 转换为列表返回
        results = list(latest_per_uid.values())
        print(f"✅ 共找到 {len(results)} 个账号的最后一次 identity 变更")
        return results



# --- 使用示例 ---
if __name__ == "__main__":
    # 1. 创建 ScenarioManager 实例
    manager = ScenarioManager()
    # 2. 准备要插入的数据
    insert_data = {
    "type_val":"政务",
    "scenario":"查找历史数据相关的账号",
    "direct_query": {
        "历史身份变化": "three_new_identity",

        "query_dsl":
            {
                "size": 500,
                "query": {
                    "nested": {
                        "path": "identity_history",
                        "query": {
                            "range": {
                                "identity_history.updated_at": {
                                    "gte": "2025-09-21T00:00:00",
                                    "lte": "2025-09-30T00:00:00"
                                }
                            }
                        },
                        "inner_hits": {
                            "size": 10,
                            "_source": ["identity_history.value", "identity_history.updated_at"]
                        }
                    }
                },
                "_source": ["uid"]
            }
    },
    "single_query":{},
    "new_feature":"无"
    }

    # 3. 执行插入
    # new_id = manager.insert_scenario(**insert_data)
    # if new_id is not None:
    #     print(f"新记录的 ID 是: {new_id}")

    # 4. 执行查询 (使用刚得到的 ID)
    # queries = manager.query_queries_by_id(1)
    # if queries:
    #     direct_q, single_q = queries
    #     print("direct_query 内容:")
    #     print(json.loads(direct_q))
    #     print("single_query 内容:")
    #     print(single_q if single_q else "None")

    manager.query_from_opensearch_by_direct_query(4, index="history_user_profile")
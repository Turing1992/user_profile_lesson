
from opensearchpy import OpenSearch
from datetime import datetime

# OpenSearch 配置
opensearch_config = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": '/Users/liuruixi/Desktop/服务器传送阵/ca.cer',
    "timeout": 30
}

client = OpenSearch(**opensearch_config)

index_name = "user_profile_testindex"

index_settings = {
    "settings": {
        "number_of_shards": 1,  # 简化示例
        "number_of_replicas": 1,
        "refresh_interval": "30s"
    },
    "mappings": {
        "dynamic": "strict",  # 只允许预定义字段

        "properties": {
            "uid": {
                "type": "keyword" ,
                "doc_values": True
            },
            "index_suffix": { "type": "keyword" },

            # === 可追踪字段及其历史（最多10条）===
            "org": {
                "type": "keyword",
                "doc_values": True
            },
            "org_history": {
                "type": "nested",
                "properties": {
                    "value": { "type": "keyword" },
                    "updated_at": { "type": "date" }
                }
            },

            "contact": {
                "type": "keyword",
                "doc_values": True
            },
            "contact_history": {
                "type": "nested",
                "properties": {
                    "value": { "type": "keyword" },
                    "updated_at": { "type": "date" }
                }
            },

            "age": {
                "type": "keyword",
                "doc_values": True
            },
            "age_history": {
                "type": "nested",
                "properties": {
                    "value": { "type": "keyword" },
                    "updated_at": { "type": "date" }
                }
            },

            "industry": {
                "type": "keyword",
                "doc_values": True
            },
            "industry_history": {
                "type": "nested",
                "properties": {
                    "value": { "type": "keyword" },
                    "updated_at": { "type": "date" }
                }
            },
            "opinions": {
                    "type": "text",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256
                        }
                    }
                },
                "opinions_history": {
                    "type": "nested",
                    "properties": {
                        "value": {
                            "type": "text",
                            "fields": {
                                "keyword": {
                                    "type": "keyword",
                                    "ignore_above": 256
                                }
                            }
                        },
                        "updated_at": {"type": "date"}
                    }
                },

            # === 时间戳 ===
            "create_time": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis||yyyy-MM-dd'T'HH:mm:ss"
            },
            "last_updated_time": {
                "type": "date"
            }
        }
    }
}

# 创建索引
# client.indices.create(index=index_name, body=index_settings)


def update_user_profile_with_history(uid, index_suffix, new_data):
    """
    更新用户画像，自动记录变更，历史最多保留10条
    """
    doc_id = f"{uid}_{index_suffix}"
    update_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    script_source = """
        boolean has_changes = false;

        // 遍历新数据中的每个字段
        for (entry in params.new_data.entrySet()) {
            String field = entry.getKey();
            Object new_value = entry.getValue();

            // 检查当前值是否存在
            if (ctx._source.containsKey(field)) {
                Object current_value = ctx._source[field];

                // 判断值是否变化（注意：null 比较）
                if (current_value == null ? new_value != null : !current_value.equals(new_value)) {
                    // 创建历史记录
                    Map history_entry = new HashMap();
                    history_entry.put('value', current_value);
                    history_entry.put('updated_at', ctx._source.last_updated_time); // 上次更新时间

                    // 历史字段名
                    String history_field = field + '_history';
                    if (!ctx._source.containsKey(history_field)) {
                        ctx._source[history_field] = new ArrayList();
                    }

                    // 添加新历史
                    ctx._source[history_field].add(history_entry);

                    // 保留最多 10 条，删除最老的
                    if (ctx._source[history_field].size() > 10) {
                        // 方法：保留最新的 10 条（从倒数第10个开始）
                        ctx._source[history_field] = new ArrayList(ctx._source[history_field].subList(
                            ctx._source[history_field].size() - 10,
                            ctx._source[history_field].size()
                        ));
                    }

                    has_changes = true;
                }
            } else {
                // 字段不存在，视为新增（也算变化）
                has_changes = true;
            }

            // 更新当前值（无论是否变化）
            ctx._source[field] = new_value;
        }

        // 更新最后更新时间
        ctx._source.last_updated_time = params.update_time;

        // 可选：如果没有变化，可以跳过更新（节省写入）
        // if (!has_changes) {
        //     ctx.op = 'none';
        // }
    """

    try:
        response = client.update(
            index=index_name,
            id=doc_id,
            body={
                "script": {
                    "source": script_source,
                    "lang": "painless",
                    "params": {
                        "new_data": new_data,
                        "update_time": update_time
                    }
                },
                "upsert": {
                    "uid": uid,
                    "index_suffix": index_suffix,
                    "create_time": update_time,
                    "last_updated_time": update_time,
                    **new_data
                }
            }
        )
        return response
    except Exception as e:
        print(f"Update failed: {e}")
        raise

if __name__ == '__main__':


    # update_user_profile_with_history(
    #     uid="1001",
    #     index_suffix="insvideo",
    #     new_data={
    #         "org": "智慧星光",
    #         "contact": "user1@companya.com",
    #         "age": "25",
    #         "industry": "退役军人",
    #         "opinions":"认为国内政策不怎么好"
    #     }
    # )

    # update_user_profile_with_history(
    #     uid="1001",
    #     index_suffix="insvideo",
    #     new_data={
    #         "org": "智慧星光信息技术有限公司",
    #         "contact": "user1@companyb.com",
    #         "age": "25",  # 未变
    #         "industry": "算法工程师",
    #         "opinions": "美联储降息靴子落地"
    #     }
    # )

    update_user_profile_with_history(
        uid="1001",
        index_suffix="insvideo",
        new_data={
            "org": "智慧星光信息技术有限公司",
            "contact": "user1@companyb.com",
            "age": "26",
            "industry": "算法工程师",
            "opinions": "认为女拳就应该彻底消失"
        }
    )

    # 第4次：数据变化
    # update_user_profile_with_history(
    #     uid="1003",
    #     index_suffix="insvideo",
    #     new_data={
    #         "org": "智慧星光信息技术股份有限公司",
    #         "contact": "ruixi@istarshine.com",
    #         "age": "27",
    #         "industry": "退役军人"
    #     }
    # )

    #测试列存储查询
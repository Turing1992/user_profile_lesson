from opensearchpy import OpenSearch
import json

# 配置
host = 'opensearch-o-00o160its7w7.escloud.ivolces.com'
port = 9200
auth = ('admin', 'Zhxg09z11@')
ca_certs_path = r'/Users/liuruixi/Desktop/服务器传送阵/ca.cer'
index_pattern = 'user_profile_*'  # 匹配所有以 user_profile_ 开头的索引

# 新增字段定义
new_mapping = {
    "properties": {

        "community": {
              "type": "text",
            },
    }
}

# 创建客户端
client = OpenSearch(
    hosts=[{'host': host, 'port': port}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    ca_certs=ca_certs_path,
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)

# 执行批量更新 mapping
try:
    # 👉 更新 mapping（支持通配符）
    response = client.indices.put_mapping(
        index=index_pattern,
        body=new_mapping
    )
    print("✅ 成功更新以下索引的 mapping:")

    # 👉 使用 get() 获取匹配的索引列表（正确方式）
    indices = client.indices.get(index=index_pattern)  # 返回 dict，key 是索引名
    index_list = list(indices.keys())

    # 排序并打印前10个
    index_list.sort()
    for idx in index_list[:10]:
        print(f"  - {idx}")
    if len(index_list) > 10:
        print(f"  ... 共 {len(index_list)} 个索引")
    else:
        print(f"  共 {len(index_list)} 个索引")

    print("\n响应:", json.dumps(response, indent=2, default=str))

except Exception as e:
    print("❌ 更新失败:", str(e))
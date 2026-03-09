from opensearchpy import OpenSearch, RequestsHttpConnection
import pandas as pd


# OpenSearch 配置
opensearch_config = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": 'ca.cer',
    "timeout": 30
}
index_pattern = 'user_profile_*'  # 匹配索引模式
output_file = 'user_level.xlsx'
# ==================== DSL 查询：两个字段都存在 ====================
query = {
    "query": {
        "bool": {
            "must": [
                { "exists": { "field": "user_level" } }
            ],
            "filter": [
                { "terms": { "user_level": ["头部", "腰部", "肩部"] } }
            ]
        }
    }
}
#链接es
client = OpenSearch(**opensearch_config)

# ==================== 滚动查询获取所有匹配数据 ====================
def fetch_all_documents(client, index_pattern, query):
    try:
        response = client.search(
            index=index_pattern,
            body=query,
            scroll='5m',
            size=1000  # 根据性能可调小
        )
    except Exception as e:
        print(f"搜索请求失败: {e}")
        return []

    hits = response['hits']['hits']
    scroll_id = response['_scroll_id']
    all_docs = hits

    # 滚动遍历
    while len(hits) > 0:
        try:
            response = client.scroll(scroll_id=scroll_id, scroll='5m')
            hits = response['hits']['hits']
            all_docs.extend(hits)
            scroll_id = response['_scroll_id']
        except Exception as e:
            print(f"滚动过程中出错: {e}")
            break

    # 清理 scroll
    try:
        client.clear_scroll(scroll_id=scroll_id)
    except:
        pass

    # 提取完整 _source（即原始文档）
    records = []
    for hit in all_docs:
        doc = hit['_source'].copy()  # 完整字段
        doc['@timestamp'] = hit.get('@timestamp')  # 可选：补充元字段
        doc['_id'] = hit['_id']  # 保留文档 ID
        doc['_index'] = hit['_index']  # 来自哪个索引
        records.append(doc)

    return records


# ==================== 主程序 ====================
if __name__ == "__main__":
    print("正在从 OpenSearch 获取包含 three_new_identity 和 community 字段的所有文档...")
    data = fetch_all_documents(client, index_pattern, query)

    if not data:
        print("未找到符合条件的数据。")
    else:
        print(f"共获取到 {len(data)} 条记录，正在准备导出...")

        # 转为 DataFrame
        df = pd.json_normalize(data)  # 自动展平嵌套结构（如 address.city 等）

        # 保存为 Excel
        try:
            df.to_excel(output_file, index=False)
            print(f"✅ 数据已成功保存至: {output_file}")
        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
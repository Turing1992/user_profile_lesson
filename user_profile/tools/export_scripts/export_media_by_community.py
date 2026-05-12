# -*- coding: utf-8 -*-
"""
临时脚本：从ES media_* 索引导出 ip_region=嘉兴市，community 为指定值的全部数据，输出到 Excel
"""
from opensearchpy import OpenSearch
import pandas as pd
from datetime import datetime

# OpenSearch 配置（复用项目已有配置）
opensearch_config = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": 'ca.cer',
    "timeout": 30
}

client = OpenSearch(**opensearch_config)

# 查询条件
COMMUNITIES = ["外卖员", "网约车司机", "快递员", "货车司机"]
IP_REGION = "嘉兴市"
INDEX_PATTERN = "media_*"
SCROLL_TIME = "5m"
BATCH_SIZE = 2000

query_body = {
    "query": {
        "bool": {
            "must": [
                {"match_phrase": {"cpt_location": IP_REGION}},
                {"terms": {"community.keyword": COMMUNITIES}}
            ]
        }
    },
    "size": BATCH_SIZE
}


def fetch_all():
    """scroll 方式拉取全部数据"""
    import json as _json
    print("\n========== Kibana 查询语句 ==========")
    print(f"索引: {INDEX_PATTERN}")
    print(_json.dumps(query_body, ensure_ascii=False, indent=2))
    print("=====================================\n")

    all_docs = []
    resp = client.search(index=INDEX_PATTERN, body=query_body, scroll=SCROLL_TIME, request_timeout=60)
    scroll_id = resp.get('_scroll_id')
    hits = resp['hits']['hits']
    total = resp['hits']['total']['value'] if isinstance(resp['hits']['total'], dict) else resp['hits']['total']
    print(f"共命中 {total} 条记录，开始拉取...")

    batch_num = 0
    while hits:
        batch_num += 1
        for h in hits:
            doc = h['_source']
            doc['_index'] = h['_index']
            all_docs.append(doc)
        pct = min(len(all_docs) / total * 100, 100) if total > 0 else 100
        print(f"\r[第{batch_num}批] 已拉取 {len(all_docs)}/{total} 条 ({pct:.1f}%)", end="", flush=True)
        resp = client.scroll(scroll_id=scroll_id, scroll=SCROLL_TIME)
        scroll_id = resp.get('_scroll_id')
        hits = resp['hits']['hits']
    print()  # 换行

    if scroll_id:
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

    return all_docs


if __name__ == "__main__":
    docs = fetch_all()
    if not docs:
        print("未查询到数据")
    else:
        df = pd.DataFrame(docs)
        filename = f"嘉兴市_社区人群导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(filename, index=False, engine='openpyxl')
        print(f"导出完成: {filename}，共 {len(df)} 条")

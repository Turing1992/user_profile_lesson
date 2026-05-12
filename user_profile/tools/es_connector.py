"""
OpenSearch 连接工具脚本
用法：直接运行可测试连接，也可作为模块导入使用
"""
from opensearchpy import OpenSearch

opensearch_config = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": r'/Users/liuruixi/Desktop/minimind/user_profile_lesson/utils/ca.cer',
    "timeout": 30
}


def get_client():
    """获取 OpenSearch 客户端实例"""
    return OpenSearch(**opensearch_config)


def test_connection():
    """测试连接并打印集群信息"""
    client = get_client()
    try:
        info = client.info()
        print(f"✅ 连接成功")
        print(f"   集群名称: {info['cluster_name']}")
        print(f"   版本: {info['version']['number']}")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False

    indices = client.cat.indices(format="json")
    print(f"   索引数量: {len(indices)}")
    for idx in sorted(indices, key=lambda x: x['index'])[:10]:
        print(f"   - {idx['index']}  docs: {idx.get('docs.count', '?')}  size: {idx.get('store.size', '?')}")
    if len(indices) > 10:
        print(f"   ... 还有 {len(indices) - 10} 个索引")

    return True


if __name__ == '__main__':
    test_connection()

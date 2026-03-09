config = {
    "mq_url2": "alpha-rocketmq-1.istarshine.net.cn:9876;alpha-rocketmq-2.istarshine.net.cn:9876",
    "mq_url":"yqms-rocketmq-broker1-master.istarshine.net.cn:9876;yqms-rocketmq-broker2-master.istarshine.net.cn:9876",
    "redis":{
        "redis_url_verified":"redis://192.168.187.3/2",
        "redis_url_identity_bloom":"redis://192.168.187.3/5",
        "redis_quchong":"redis://192.168.19.5/1",
        "identity_bloom_key":"liuruixiDataBloomFilter",
        "identity_bloom_key_ems":"liuruixiDataBloomFilter2",
        "verified_status":"verified_status",
        "user_fre":"user_fre",
        "website_fre":"website_fre"
    },#词同步redis地址几及存放信息

    # OpenSearch 配置
    "ESsearch": {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": '/Users/liuruixi/Desktop/minimind/user_profile_lesson/utils/ca.cer',
    "timeout": 30
    },
    "topic":{
        "spider_data":"spider_data",           #数据源头
        "prod_live_common_data":"prod_live_common_data",
        "user_graph_mybe_have_identity":"user_graph_mybe_have_identity_topic",
        "user_graph_drawed_result":"user_graph_drawed_result_topic",
        "processed_user_data":"processed_user_data_topic",  #新增：ScyllaDB处理后的数据
    },
    "beta_topic":{
        "live_common_topic":"beta_event_sphere_live_common_topic"
    },
    "beta_group":{
        "live_common_group":"beta_indentity_group"
    },
    "producer_group":{
        "user_graph_mybe_have_identity": "user_graph_mybe_have_identity_producer",
        "user_graph_drawed_result":"user_graph_drawed_result_producer",
        "processed_user_data":"processed_user_data_producer",  #新增：ScyllaDB处理后数据的生产者
    },
    # ScyllaDB配置
    "scylladb":{
        "contact_points": ["192.168.191.9"],
        "port": 9042,
        "keyspace": "user_profile_keyspace",
        "auth_provider": None  # 如需认证，配置PlainTextAuthProvider
    },
    "consumer_group":{
        "user_graph_uniq_user_identity": "user_graph_draw_identity_consumer",
        "user_graph_uniq_user_identity2": "user_graph_draw_identity_consumer2",
        "user_graph_uniq_user": "user_graph_uniq_user_consumer",
        "user_graph_check_user": "user_graph_check_user_consumer",
    }
}


# -*- coding: utf-8 -*-
"""
统一配置管理模块。

整合 ``sport_data_get/config.py`` 和 ``utils/config.py`` 中分散的配置，
提供集中式配置管理，支持环境变量覆盖和点号分隔的嵌套 key 访问。

使用示例::

    from config.settings import config

    # 点号分隔访问
    mq_url = config.get("mq_url")
    redis_url = config.get("redis.redis_url_identity_bloom")

    # 字典风格访问（向后兼容）
    redis_url = config["redis"]["redis_url_identity_bloom"]

    # 带默认值
    timeout = config.get("opensearch.timeout", 60)
"""

import os

from utils.path_resolver import get_path_no_check


class ConfigurationError(Exception):
    """配置错误异常。当必要配置缺失或格式不正确时抛出。"""
    pass


class ConfigManager(object):
    """
    统一配置管理器。

    整合项目中所有配置到单一入口，支持：
    - 点号分隔的嵌套 key 访问（``config.get("redis.redis_quchong")``）
    - 字典风格访问（``config["redis"]["redis_quchong"]``），向后兼容
    - 环境变量覆盖基础配置
    - 配置验证

    Attributes:
        _config: 内部配置字典，存储所有配置项。
    """

    def __init__(self):
        # type: () -> None
        """初始化配置管理器，加载基础配置并应用环境变量覆盖。"""
        self._config = {}  # type: dict
        self._load_base_config()
        self._apply_env_overrides()

    def get(self, key, default=None):
        # type: (str, object) -> object
        """
        通过点号分隔的 key 路径访问配置值。

        支持嵌套访问，例如 ``config.get("redis.redis_quchong")``
        等价于 ``config._config["redis"]["redis_quchong"]``。

        Args:
            key: 点号分隔的配置键路径，如 ``"redis.redis_url_identity_bloom"``。
            default: 当 key 路径不存在时返回的默认值，默认为 None。

        Returns:
            配置值，或 key 路径不存在时返回 default。
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def __getitem__(self, key):
        # type: (str) -> object
        """
        支持字典风格的配置访问，向后兼容旧代码。

        例如 ``config["redis"]`` 返回 redis 配置子字典，
        可继续链式访问 ``config["redis"]["redis_quchong"]``。

        Args:
            key: 顶层配置键名。

        Returns:
            对应的配置值。

        Raises:
            KeyError: 当 key 不存在时抛出。
        """
        return self._config[key]

    def __contains__(self, key):
        # type: (str) -> bool
        """
        支持 ``in`` 操作符检查配置键是否存在。

        Args:
            key: 顶层配置键名。

        Returns:
            True 如果 key 存在于配置中，否则 False。
        """
        return key in self._config

    def validate(self):
        # type: () -> None
        """
        验证必要配置项是否存在。

        委托给 ``config.validator`` 模块执行实际验证逻辑，
        检查 ``mq_url``、``redis``、``opensearch``、``mysql`` 等必要配置键。
        缺失时抛出 ``ConfigurationError`` 并列出所有缺失项。

        Raises:
            ConfigurationError: 当一个或多个必要配置键缺失时抛出。
        """
        from config.validator import validate_config
        validate_config(self)

    def keys(self):
        # type: () -> list
        """
        返回所有顶层配置键名列表。

        Returns:
            顶层配置键名列表。
        """
        return list(self._config.keys())

    def _set_nested(self, key, value):
        # type: (str, object) -> None
        """
        通过点号分隔的 key 路径设置配置值。

        如果中间层级不存在，会自动创建空字典。

        Args:
            key: 点号分隔的配置键路径。
            value: 要设置的值。
        """
        keys = key.split(".")
        d = self._config
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

    def _load_base_config(self):
        # type: () -> None
        """
        加载基础配置。

        合并原 ``sport_data_get/config.py`` 和 ``utils/config.py`` 中的所有配置项，
        使用 ``path_resolver.get_path_no_check()`` 解析 ca.cer 证书路径。
        """
        ca_cert_path = get_path_no_check("ca.cer")

        self._config = {
            # === RocketMQ 配置 ===
            "mq_url": (
                "yqms-rocketmq-broker1-master.istarshine.net.cn:9876;"
                "yqms-rocketmq-broker2-master.istarshine.net.cn:9876"
            ),
            "mq_url2": (
                "alpha-rocketmq-1.istarshine.net.cn:9876;"
                "alpha-rocketmq-2.istarshine.net.cn:9876"
            ),

            # === Redis 配置 ===
            "redis": {
                "redis_url_verified": "redis://192.168.187.3/2",
                "redis_url_identity_bloom": "redis://192.168.187.3/5",
                "redis_quchong": "redis://192.168.19.5/1",
                "identity_bloom_key": "liuruixiDataBloomFilter",
                "identity_bloom_key_ems": "liuruixiDataBloomFilter2",
                "verified_status": "verified_status",
                "user_fre": "user_fre",
                "website_fre": "website_fre",
            },

            # === OpenSearch 配置（合并 ESsearch 和 opensearch_config） ===
            "ESsearch": {
                "hosts": [
                    "https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200"
                ],
                "http_auth": ("admin", "Zhxg09z11@"),
                "use_ssl": True,
                "verify_certs": True,
                "ca_certs": ca_cert_path,
                "timeout": 30,
            },
            "opensearch": {
                "hosts": [
                    "https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200"
                ],
                "http_auth": ("admin", "Zhxg09z11@"),
                "use_ssl": True,
                "verify_certs": True,
                "ca_certs": ca_cert_path,
                "timeout": 30,
            },

            # === MySQL 配置（原 utils/config.py 的 sql_config） ===
            "mysql": {
                "host": "192.168.19.65",
                "user": "buser",
                "password": "p3jnmja3",
                "database": "user_profile",
            },

            # === Topic 配置 ===
            "topic": {
                "spider_data": "spider_data",
                "prod_live_common_data": "prod_live_common_data",
                "user_graph_mybe_have_identity": "user_graph_mybe_have_identity_topic",
                "user_graph_drawed_result": "user_graph_drawed_result_topic",
                "processed_user_data": "processed_user_data_topic",
            },
            "beta_topic": {
                "live_common_topic": "beta_event_sphere_live_common_topic",
            },
            "beta_group": {
                "live_common_group": "beta_indentity_group",
            },

            # === 生产者/消费者组 ===
            "producer_group": {
                "user_graph_mybe_have_identity": "user_graph_mybe_have_identity_producer",
                "user_graph_drawed_result": "user_graph_drawed_result_producer",
                "processed_user_data": "processed_user_data_producer",
            },
            "consumer_group": {
                "user_graph_uniq_user_identity": "user_graph_draw_identity_consumer",
                "user_graph_uniq_user_identity2": "user_graph_draw_identity_consumer2",
                "user_graph_uniq_user": "user_graph_uniq_user_consumer",
                "user_graph_check_user": "user_graph_check_user_consumer",
        "user_graph_uniq_user_wangyueche": "user_graph_uniq_user_wangyueche_consumer",
            },

            # === ScyllaDB 配置 ===
            "scylladb": {
                "contact_points": ["192.168.191.9"],
                "port": 9042,
                "keyspace": "user_profile_keyspace",
                "auth_provider": None,
            },
        }

    def _apply_env_overrides(self):
        # type: () -> None
        """
        从环境变量覆盖配置项。

        支持的环境变量映射：
        - ``MQ_URL`` → ``mq_url``
        - ``MQ_URL2`` → ``mq_url2``
        - ``REDIS_URL_BLOOM`` → ``redis.redis_url_identity_bloom``
        - ``REDIS_URL_VERIFIED`` → ``redis.redis_url_verified``
        - ``REDIS_URL_QUCHONG`` → ``redis.redis_quchong``
        - ``OPENSEARCH_HOSTS`` → ``opensearch.hosts``（同时更新 ESsearch.hosts）
        - ``MYSQL_HOST`` → ``mysql.host``
        - ``MYSQL_USER`` → ``mysql.user``
        - ``MYSQL_PASSWORD`` → ``mysql.password``
        - ``MYSQL_DATABASE`` → ``mysql.database``
        - ``LOG_LEVEL`` → ``log_level``
        """
        env_mapping = {
            "MQ_URL": "mq_url",
            "MQ_URL2": "mq_url2",
            "REDIS_URL_BLOOM": "redis.redis_url_identity_bloom",
            "REDIS_URL_VERIFIED": "redis.redis_url_verified",
            "REDIS_URL_QUCHONG": "redis.redis_quchong",
            "OPENSEARCH_HOSTS": "opensearch.hosts",
            "MYSQL_HOST": "mysql.host",
            "MYSQL_USER": "mysql.user",
            "MYSQL_PASSWORD": "mysql.password",
            "MYSQL_DATABASE": "mysql.database",
            "LOG_LEVEL": "log_level",
        }
        for env_key, config_key in env_mapping.items():
            value = os.environ.get(env_key)
            if value is not None:
                self._set_nested(config_key, value)
                # 同步 ESsearch 和 opensearch 的 hosts
                if env_key == "OPENSEARCH_HOSTS":
                    self._set_nested("ESsearch.hosts", value)


# ---- 向后兼容的导出 ----

# 全局单例
config = ConfigManager()

# 兼容 utils/config.py 的 sql_config
sql_config = config.get("mysql")  # type: dict

# 兼容 utils/config.py 的 opensearch_config
opensearch_config = config.get("opensearch")  # type: dict

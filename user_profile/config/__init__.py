# -*- coding: utf-8 -*-
"""
统一配置包。

提供集中式配置管理，整合原 ``sport_data_get/config.py`` 和 ``utils/config.py``
中分散的配置项。

快速使用::

    from config import config

    # 点号分隔访问
    mq_url = config.get("mq_url")
    redis_url = config.get("redis.redis_url_identity_bloom")

    # 字典风格访问（向后兼容）
    redis_cfg = config["redis"]

    # 兼容旧代码的直接导入
    from config.settings import sql_config, opensearch_config
"""

from config.settings import config
from config.settings import ConfigManager
from config.settings import ConfigurationError
from config.settings import sql_config
from config.settings import opensearch_config
from config.validator import validate_config

__all__ = [
    "config",
    "ConfigManager",
    "ConfigurationError",
    "validate_config",
    "sql_config",
    "opensearch_config",
]

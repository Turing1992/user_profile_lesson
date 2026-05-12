# -*- coding: utf-8 -*-
"""
配置验证模块。

提供配置完整性校验功能，在系统启动时检查必要配置项是否存在，
缺失时抛出 ``ConfigurationError`` 并列出所有缺失的配置键。

使用示例::

    from config.validator import validate_config
    from config.settings import config

    # 验证全局配置单例
    validate_config(config)

    # 或者直接使用 validate 函数验证字典
    from config.validator import validate
    validate({"mq_url": "...", "redis": {...}, "opensearch": {...}, "mysql": {...}})
"""

from config.settings import ConfigurationError

# 系统启动时必须存在的顶层配置键
REQUIRED_KEYS = ["mq_url", "redis", "opensearch", "mysql"]


def validate(config_dict):
    # type: (dict) -> None
    """
    验证配置字典中是否包含所有必要的顶层配置键。

    遍历 ``REQUIRED_KEYS`` 列表，收集所有缺失的键名，
    如果存在缺失项则抛出 ``ConfigurationError``，错误信息中包含全部缺失键名。

    Args:
        config_dict: 待验证的配置字典，通常为 ``ConfigManager._config``。

    Raises:
        ConfigurationError: 当一个或多个必要配置键缺失时抛出，
            错误信息格式为 ``"缺少必要配置: key1, key2"``。
    """
    missing = [k for k in REQUIRED_KEYS if k not in config_dict]
    if missing:
        raise ConfigurationError(
            "缺少必要配置: {}".format(", ".join(missing))
        )


def validate_config(config_manager):
    # type: (object) -> None
    """
    验证 ConfigManager 实例中是否包含所有必要的配置项。

    从 ``config_manager`` 中获取顶层键列表，检查 ``REQUIRED_KEYS``
    中的每个键是否存在。缺失时抛出 ``ConfigurationError``。

    这是推荐的验证入口，接受 ConfigManager 实例而非裸字典，
    便于在应用启动阶段调用。

    Args:
        config_manager: ``ConfigManager`` 实例，需支持 ``keys()`` 方法
            返回顶层配置键列表。

    Raises:
        ConfigurationError: 当一个或多个必要配置键缺失时抛出。
    """
    existing_keys = config_manager.keys()
    missing = [k for k in REQUIRED_KEYS if k not in existing_keys]
    if missing:
        raise ConfigurationError(
            "缺少必要配置: {}".format(", ".join(missing))
        )

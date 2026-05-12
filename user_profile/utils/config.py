# -*- coding: utf-8 -*-
"""
【已废弃】此配置文件已迁移至 config/settings.py。

本文件仅保留用于向后兼容，所有新代码请直接使用::

    from config.settings import config, sql_config, opensearch_config

本文件将在后续版本中移除。
"""

# 从统一配置模块导入，保持向后兼容
from config.settings import sql_config, opensearch_config  # noqa: F401

__all__ = ["sql_config", "opensearch_config"]

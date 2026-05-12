# -*- coding: utf-8 -*-
"""
配置验证模块单元测试。

测试 config.validator 模块的 validate() 和 validate_config() 函数，
验证必要配置键缺失时正确抛出 ConfigurationError。
"""

import pytest

from config.settings import ConfigurationError, ConfigManager
from config.validator import validate, validate_config, REQUIRED_KEYS


class TestValidateFunction(object):
    """测试 validate() 函数（接受字典参数）。"""

    def test_valid_config_passes(self):
        """包含所有必要键的配置字典应通过验证。"""
        config_dict = {
            "mq_url": "some_url",
            "redis": {"key": "value"},
            "opensearch": {"hosts": []},
            "mysql": {"host": "localhost"},
            "extra_key": "extra_value",
        }
        # 不应抛出异常
        validate(config_dict)

    def test_missing_single_key_raises(self):
        """缺少单个必要键时应抛出 ConfigurationError。"""
        config_dict = {
            "redis": {},
            "opensearch": {},
            "mysql": {},
        }
        with pytest.raises(ConfigurationError) as exc_info:
            validate(config_dict)
        assert "mq_url" in str(exc_info.value)

    def test_missing_multiple_keys_lists_all(self):
        """缺少多个必要键时，错误信息应包含所有缺失键名。"""
        config_dict = {"mq_url": "url"}
        with pytest.raises(ConfigurationError) as exc_info:
            validate(config_dict)
        error_msg = str(exc_info.value)
        assert "redis" in error_msg
        assert "opensearch" in error_msg
        assert "mysql" in error_msg

    def test_empty_dict_raises_all_keys(self):
        """空字典应报告所有必要键缺失。"""
        with pytest.raises(ConfigurationError) as exc_info:
            validate({})
        error_msg = str(exc_info.value)
        for key in REQUIRED_KEYS:
            assert key in error_msg

    def test_extra_keys_do_not_interfere(self):
        """额外的配置键不应影响验证结果。"""
        config_dict = {
            "mq_url": "url",
            "redis": {},
            "opensearch": {},
            "mysql": {},
            "scylladb": {},
            "topic": {},
        }
        validate(config_dict)


class TestValidateConfigFunction(object):
    """测试 validate_config() 函数（接受 ConfigManager 实例）。"""

    def test_default_config_manager_passes(self):
        """默认 ConfigManager 包含所有必要键，应通过验证。"""
        cm = ConfigManager()
        # 不应抛出异常
        validate_config(cm)

    def test_config_manager_validate_method_delegates(self):
        """ConfigManager.validate() 方法应委托给 validator 模块。"""
        cm = ConfigManager()
        # 不应抛出异常
        cm.validate()

    def test_config_manager_with_removed_key_raises(self):
        """从 ConfigManager 中删除必要键后，验证应失败。"""
        cm = ConfigManager()
        del cm._config["mysql"]
        with pytest.raises(ConfigurationError) as exc_info:
            validate_config(cm)
        assert "mysql" in str(exc_info.value)

    def test_config_manager_validate_method_with_removed_key_raises(self):
        """通过 ConfigManager.validate() 方法验证删除键后的配置。"""
        cm = ConfigManager()
        del cm._config["redis"]
        del cm._config["opensearch"]
        with pytest.raises(ConfigurationError) as exc_info:
            cm.validate()
        error_msg = str(exc_info.value)
        assert "redis" in error_msg
        assert "opensearch" in error_msg

# -*- coding: utf-8 -*-
"""
测试公共 fixtures 模块。

提供测试中常用的 fixtures，包括：
- 临时目录作为模拟项目根目录
- USER_PROFILE_ROOT 环境变量的设置与恢复
- path_resolver 模块的缓存重置，确保测试隔离
"""

import os
import pytest

from utils.path_resolver import _reset_project_root


@pytest.fixture
def tmp_project_root(tmp_path):
    # type: (...) -> str
    """
    创建一个临时目录作为模拟的项目根目录。

    在临时目录中预创建常用的子目录和文件，
    以便测试路径解析等功能。

    Returns:
        临时项目根目录的绝对路径字符串。
    """
    # 创建常用子目录
    os.makedirs(str(tmp_path / "utils"), exist_ok=True)
    os.makedirs(str(tmp_path / "logs"), exist_ok=True)
    os.makedirs(str(tmp_path / "config"), exist_ok=True)

    # 创建模拟文件，用于路径存在性校验测试
    ca_cer = tmp_path / "ca.cer"
    ca_cer.write_text("mock ca cert")

    return str(tmp_path)


@pytest.fixture
def env_project_root(tmp_project_root, monkeypatch):
    # type: (...) -> str
    """
    设置 USER_PROFILE_ROOT 环境变量指向临时项目根目录。

    测试结束后自动恢复原始环境变量状态（由 monkeypatch 保证）。

    Returns:
        临时项目根目录的绝对路径字符串。
    """
    monkeypatch.setenv("USER_PROFILE_ROOT", tmp_project_root)
    return tmp_project_root


@pytest.fixture(autouse=True)
def reset_path_resolver():
    # type: () -> None
    """
    每个测试前后重置 path_resolver 的项目根目录缓存。

    确保测试之间互不影响，避免全局状态泄漏。
    使用 autouse=True 自动应用于所有测试。
    """
    _reset_project_root()
    yield
    _reset_project_root()

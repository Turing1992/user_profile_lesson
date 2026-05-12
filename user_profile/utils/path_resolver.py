# -*- coding: utf-8 -*-
"""
路径解析模块。

负责将相对路径转换为基于项目根目录的绝对路径，替代所有硬编码路径。
支持通过环境变量 USER_PROFILE_ROOT 覆盖默认的项目根目录。

使用示例::

    from utils.path_resolver import get_project_root, get_path, get_path_no_check

    # 获取项目根目录
    root = get_project_root()

    # 获取文件绝对路径（校验存在性）
    ca_path = get_path("ca.cer")

    # 获取目录绝对路径（不校验存在性，适用于日志目录等）
    log_dir = get_path_no_check("logs")
"""

import os

_PROJECT_ROOT = None  # type: str


def _reset_project_root():
    # type: () -> None
    """重置项目根目录缓存。仅用于测试场景。"""
    global _PROJECT_ROOT
    _PROJECT_ROOT = None


def get_project_root():
    # type: () -> str
    """
    获取项目根目录。

    优先使用环境变量 ``USER_PROFILE_ROOT``，否则自动检测。
    自动检测逻辑：从当前文件所在目录（utils/）向上一级即为项目根目录。

    Returns:
        项目根目录的绝对路径字符串。
    """
    global _PROJECT_ROOT
    if _PROJECT_ROOT is not None:
        return _PROJECT_ROOT

    env_root = os.environ.get("USER_PROFILE_ROOT")
    if env_root:
        _PROJECT_ROOT = os.path.abspath(env_root)
    else:
        # 自动检测：当前文件位于 utils/ 目录下，上一级即为项目根目录
        current = os.path.dirname(os.path.abspath(__file__))
        _PROJECT_ROOT = os.path.dirname(current)  # utils/ 的上级
    return _PROJECT_ROOT


def get_path(relative_path):
    # type: (str) -> str
    """
    返回基于项目根目录的绝对路径，并校验文件或目录是否存在。

    Args:
        relative_path: 相对于项目根目录的路径字符串。

    Returns:
        文件或目录的绝对路径字符串。

    Raises:
        FileNotFoundError: 当指定的文件或目录不存在时抛出，
            错误信息包含完整路径和项目根目录。
    """
    root = get_project_root()
    full_path = os.path.join(root, relative_path)
    if not os.path.exists(full_path):
        raise FileNotFoundError(
            "文件不存在: {} (项目根目录: {})".format(full_path, root)
        )
    return full_path


def get_path_no_check(relative_path):
    # type: (str) -> str
    """
    返回基于项目根目录的绝对路径，不检查文件是否存在。

    适用于日志目录等可能尚未创建的路径。

    Args:
        relative_path: 相对于项目根目录的路径字符串。

    Returns:
        基于项目根目录的绝对路径字符串。
    """
    return os.path.join(get_project_root(), relative_path)

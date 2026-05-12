# -*- coding: utf-8 -*-
"""
统一日志工厂模块。

提供统一的日志配置入口，所有模块应通过 ``get_logger`` 获取 logger 实例，
确保日志格式、存储路径、轮转策略一致。

支持通过环境变量 ``LOG_LEVEL`` 配置全局日志级别，默认为 ``INFO``。

使用示例::

    from utils.about_log import get_logger

    logger = get_logger("my_module")
    logger.info("启动成功")

    # 也可以显式指定日志级别
    logger = get_logger("my_module", level="DEBUG")

向后兼容::

    from utils.about_log import config_log

    # config_log 是 get_logger 的别名，用法完全相同
    logger = config_log("my_module", "WARNING")
"""

import os
import sys

from loguru import logger

from utils.path_resolver import get_path_no_check

# 统一日志格式
_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{message}"
)

# 控制台日志格式（带颜色标签，供 loguru colorize 使用）
_CONSOLE_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "{message}"
)


def get_logger(name, level=None):
    # type: (str, str) -> logger
    """
    获取统一配置的 logger 实例。

    日志文件存储在 ``logs/{name}.log``，使用统一格式，支持按大小轮转和按时间保留。

    Args:
        name: 日志名称，用于日志文件命名（如 ``"draw_graph"``）。
        level: 控制台日志级别。为 ``None`` 时从环境变量 ``LOG_LEVEL`` 读取，
               若环境变量未设置则默认为 ``"INFO"``。

    Returns:
        配置好的 loguru logger 实例。
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    # 统一转为大写，兼容调用方传入小写级别（如 "debug"）
    level = level.upper()

    # 使用 path_resolver 解析日志目录
    log_dir = get_path_no_check("logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "{name}.log".format(name=name))

    # 移除默认处理器，避免重复输出
    logger.remove()

    # 文件日志：记录 DEBUG 及以上所有级别，便于排查问题
    logger.add(
        log_file,
        format=_LOG_FORMAT,
        rotation="100 MB",
        retention="10 days",
        compression="zip",
        level="DEBUG",
        enqueue=True,
        diagnose=True,
        backtrace=True,
    )

    # 控制台日志：按指定级别输出，带颜色
    logger.add(
        sys.stdout,
        format=_CONSOLE_LOG_FORMAT,
        colorize=True,
        level=level,
    )

    return logger


# 向后兼容：保留原函数名作为别名
config_log = get_logger


# 示例用法
if __name__ == "__main__":
    my_logger = get_logger("my_app", level="DEBUG")
    extra_info = {"request_id": "12345", "user_id": "67890"}
    try:
        1 / 0
    except Exception as e:
        my_logger.exception("发生错误:", extra=extra_info)

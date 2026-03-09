import os
import sys
from loguru import logger


def config_log(name,level):
    root_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    log_file_path = os.path.join(root_path, "logs/")
    # 确保日志目录存在
    os.makedirs(log_file_path, exist_ok=True)

    # 定义日志文件名格式，包含日期部分
    log_file_name = os.path.join(log_file_path, name + ".log")

    # 自定义日志格式
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<blue>{thread.id}</blue> - "
        "{extra} - "
        "{message}"
    )
    console_log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<blue>{thread.id}</blue> - "
        "{extra} - "
        "\x1b[38;5;206m{message}\x1b[0m"
    )
    logger.remove()  # 移除默认的日志处理器
    logger.add(
        log_file_name,
        format=log_format,
        rotation="100 MB",  # 每5MB分割一次
        retention="10 days",  # 修正为合理的保留时间，例如10天
        compression="zip",  # 压缩旧日志文件
        level="DEBUG",
        enqueue=True,  # 异步记录日志
        diagnose=True,
        backtrace=True  # 在错误级别启用回溯
    )

    logger.add(
        sys.stdout,
        format=console_log_format,
        colorize=True,  # 控制台日志带有颜色
        level=level
    )
    return logger

# my_log_hd = config_log("bule_space","debug")


# 示例用法
if __name__ == "__main__":
    # my_logger = config_log("my_app")
    my_logger = config_log("my_app")
    extra_info = {"request_id": "12345", "user_id": "67890"}
    try:
        1/0
    except Exception as e:
        my_logger.exception("An error occurred:", extra=extra_info)
    # my_logger.exception()


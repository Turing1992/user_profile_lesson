# -*- coding: utf-8 -*-
"""
Oasis系统配置文件
"""

# LLM API配置
LLM_CONFIG = {
    "url": "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
    "api_key": "sk-EzfEPX79KDf9nZOS4QkhmZhrJZteVyfXrMAOvgHai26WVSNv",
    "model": "hunyuan-turbos-latest",
    "temperature": 0.01,
    "top_p": 0.01
}

# Redis配置
REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "password": None,
    "decode_responses": True
}

# MySQL配置
MYSQL_CONFIG = {
    "host": "192.168.19.64",
    "port": 3306,
    "user": "buser",
    "password": "p3jnmja3",
    "database": "oasis_system",
    "charset": "utf8mb4"
}

# 日志配置
LOG_CONFIG = {
    "log_dir": "logs",
    "log_file": "oasis_system.log",
    "log_level": "INFO"
}

# 推演维度配置
INFERENCE_DIMENSIONS = [
    "basic_info",           # 基础信息
    "identity_analysis",    # 身份分析
    "behavior_prediction",  # 行为预测
    "social_inference",     # 社交推断
    "content_preference",   # 内容偏好
    "risk_assessment"       # 风险评估
]

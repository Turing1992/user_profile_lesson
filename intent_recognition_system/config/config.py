"""
配置文件 - 意图识别系统
"""
import os

# MCP配置
MCP_CONFIG = {
    "server_name": "intent-recognition-server",
    "version": "1.0.0",
    "description": "Intent Recognition System using MCP",
    "port": 8080
}

# 数据库配置 - 使用环境变量或默认值
DATABASE_CONFIG = {
    "opensearch": {
        "hosts": [{"host": os.getenv("OPENSEARCH_HOST", "localhost"), "port": int(os.getenv("OPENSEARCH_PORT", "9200"))}],
        "use_ssl": os.getenv("OPENSEARCH_SSL", "false").lower() == "true",
        "verify_certs": False,
        "index_prefix": "user_profile"
    },
    "redis": {
        "host": os.getenv("REDIS_HOST", "localhost"),
        "port": int(os.getenv("REDIS_PORT", "6379")),
        "db": int(os.getenv("REDIS_DB", "0")),
        "decode_responses": True
    },
    "mysql": {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", "password"),
        "database": os.getenv("MYSQL_DATABASE", "intent_system")
    }
}

# LLM配置
LLM_CONFIG = {
    "openai": {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "1000"))
    }
}

# 三元组提取配置
TRIPLET_CONFIG = {
    "max_triplets": int(os.getenv("MAX_TRIPLETS", "10")),
    "min_confidence": float(os.getenv("MIN_CONFIDENCE", "0.7")),
    "keywords_per_triplet": int(os.getenv("KEYWORDS_PER_TRIPLET", "5"))
}

# 检索配置
SEARCH_CONFIG = {
    "max_results": int(os.getenv("MAX_SEARCH_RESULTS", "1000")),
    "similarity_threshold": float(os.getenv("SIMILARITY_THRESHOLD", "0.8")),
    "account_limit": int(os.getenv("ACCOUNT_LIMIT", "100"))
}
import redis
from urllib.parse import urlparse

# ========================
# 配置区（按需修改）
# ========================
REDIS_HOST = '192.168.16.136'
REDIS_PORT = 6379
REDIS_DB = 11


try:
    client = redis.StrictRedis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,  # 自动将 bytes 转为 str
        socket_connect_timeout=5,
        socket_timeout=5
    )
    client.ping()
    print("✅ 成功连接到 Redis (db=11)")
except Exception as e:
    raise ConnectionError(f"❌ 连接 Redis 失败: {e}")


def get_url_metrics(url: str) -> dict:
    """
    根据传入的 URL，从 Redis DB11 中获取其行为数据
    返回字典，包含 comment, visit, attitudes 等
    """
    try:
        if client.type(url) != 'hash':
            print(f"⚠️ 未找到或类型不匹配: {url}")
            return {}

        data = client.hgetall(url)
        # 转成 int 类型更方便后续处理
        metrics = {}
        for k, v in data.items():
            try:
                metrics[k] = int(v)
            except (ValueError, TypeError):
                metrics[k] = v  # 保留原值
        print(f"🎯 命中: {url} → {metrics}")
        return metrics

    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return {}


# === 使用示例 ===
if __name__ == '__main__':
    test_url = "https://www.kuaishou.com/short-video/3xssix7euinazbe"
    result = get_url_metrics(test_url)
    print("结果:", result)
    # 输出: {'comment': 10}
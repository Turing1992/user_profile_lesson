import redis

# 连接到 Redis 服务器
client = redis.StrictRedis(host='192.168.187.3', port=6379, db=2, decode_responses=True)


def delete_keys_with_at_sign(r):
    pipe = r.pipeline()
    count = 0
    match_pattern = "*@*"

    # 使用 SCAN 游标迭代查找所有匹配的 key
    for key in r.scan_iter(match=match_pattern, count=10000):
        pipe.delete(key)
        count += 1

        # 每收集到一定数量的 key 就执行一次 pipeline
        if count % 10000 == 0:
            pipe.execute()
            print(f"总共删除了 {count} 个包含 '@' 字符的 key")

    # 处理剩余未执行的 pipeline 请求
    if count % 1000 != 0:
        pipe.execute()

    print(f"总共删除了 {count} 个包含 '@' 字符的 key")


if __name__ == "__main__":
    delete_keys_with_at_sign(client)
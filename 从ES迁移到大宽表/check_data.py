# check_user_posts_data.py
"""
检查 user_posts 表中是否意外写入了用户 profile 数据
"""

from cassandra.cluster import Cluster
from datetime import datetime

SCYLLA_CONTACT_POINTS = ['192.168.191.9']
SCYLLA_PORT = 9042
KEYSPACE_NAME = "user_post_keyspace"
TABLE_NAME = "user_posts"  # 👈 我们怀疑这里混进了 profile 数据


def main():
    print(f"[{datetime.now()}] 🔍 正在连接 ScyllaDB...")

    cluster = Cluster(contact_points=SCYLLA_CONTACT_POINTS, port=SCYLLA_PORT)
    session = cluster.connect()

    try:
        session.set_keyspace(KEYSPACE_NAME)
        print(f"✅ 使用 keyspace: {KEYSPACE_NAME}")

        # 查询前 5 条记录
        query = f"SELECT * FROM {TABLE_NAME} LIMIT 5"
        rows = session.execute(query)

        print(f"\n📊 正在查看 `{TABLE_NAME}` 中的前 5 条数据:")
        print("🔍 注意观察字段是否包含 name, age, city, tags 等 profile 字段\n")

        count = 0
        for row in rows:
            count += 1
            print(f"--- 第 {count} 条 ---")
            for field in row._fields:
                value = getattr(row, field)
                print(f"  {field:<15}: {value}")

        if count == 0:
            print("⚠️ 该表为空")
        else:
            print(f"\n✅ 已显示 {count} 条记录")

    except Exception as e:
        print(f"❌ 查询失败: {e}")
        raise
    finally:
        cluster.shutdown()


if __name__ == '__main__':
    main()
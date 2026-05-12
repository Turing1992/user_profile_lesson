'2320160211_快手'

from cassandra.cluster import Cluster
import traceback
class ScyllaPostTexts:
    def __init__(self, contact_points, port= 9042,
                 keyspace = "user_post_keyspace"):
        self.contact_points = contact_points
        self.port = port
        self.keyspace = keyspace
        self.session = self._connect()
        self.session.set_keyspace(self.keyspace)

    def _connect(self):
        cluster = Cluster(self.contact_points, port=self.port)
        return cluster.connect()

    # 插入新帖子函数
    def get_uid_post(self, uid):
        try:
            # 1. 查询用户现有帖子数量
            # count = self.post_count.get_post_count(uid)
            query_count = "SELECT * FROM user_posts WHERE uid=%s"
            rows = list(self.session.execute(query_count, (uid,)))
            return rows
        except Exception as e:
            print(f"[{uid}] 插入失败: {traceback.format_exc()}")

if __name__ == '__main__':
    scylla = ScyllaPostTexts(["192.168.191.9"])
    results = scylla.get_uid_post("1986181952447504-抖音")
    print(results)
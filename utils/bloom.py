import redis


class BloomFilter:
    def __init__(self,redis_url,bf_key):
        self.bf_key = bf_key
        self.redis_conn = redis.from_url(redis_url)
        if self.redis_conn.execute_command('BF.EXISTS', self.bf_key, 'init_test') >= 0:
            pass
        else:
            self.redis_conn.execute_command('BF.RESERVE', self.bf_key, '0.00001', '1000000000')
    def  is_double(self,value):
        exists = self.redis_conn.execute_command('BF.EXISTS', self.bf_key, value)
        if exists == 0:
            # 不存在，则添加进过滤器和结果列表
            # print("不重复项~~~~~:")
            return False
        else:
            # print("重复过滤")
            return True
    def add_value(self,value):
        self.redis_conn.execute_command('BF.ADD', self.bf_key, value)
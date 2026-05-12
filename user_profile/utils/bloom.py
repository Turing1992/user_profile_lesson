# -*- coding: utf-8 -*-
"""Redis 布隆过滤器模块。

基于 Redis 的 BF（Bloom Filter）命令实现数据去重功能。
用于在大规模数据处理管线中快速判断某个值是否已经处理过，避免重复入库。
"""
import redis


class BloomFilter:
    """基于 Redis 的布隆过滤器，用于数据去重。

    通过 Redis 的 BF.EXISTS / BF.ADD 命令实现高效的集合成员判断，
    适用于海量数据场景下的去重需求。

    Attributes:
        bf_key: 布隆过滤器在 Redis 中的 key 名称。
        redis_conn: Redis 连接实例。
    """

    def __init__(self, redis_url, bf_key):
        # type: (str, str) -> None
        """初始化布隆过滤器。

        连接 Redis 并检查布隆过滤器是否已存在，若不存在则创建。

        Args:
            redis_url: Redis 连接地址，格式如 ``redis://host:port/db``。
            bf_key: 布隆过滤器在 Redis 中的 key 名称。
        """
        self.bf_key = bf_key
        self.redis_conn = redis.from_url(redis_url)
        if self.redis_conn.execute_command('BF.EXISTS', self.bf_key, 'init_test') >= 0:
            pass
        else:
            self.redis_conn.execute_command('BF.RESERVE', self.bf_key, '0.00001', '1000000000')

    def is_double(self, value):
        # type: (str) -> bool
        """判断给定值是否已存在于布隆过滤器中（是否重复）。

        Args:
            value: 待检查的字符串值。

        Returns:
            True 表示该值已存在（重复），False 表示不存在（不重复）。
        """
        exists = self.redis_conn.execute_command('BF.EXISTS', self.bf_key, value)
        if exists == 0:
            # 不存在，则添加进过滤器和结果列表
            # print("不重复项~~~~~:")
            return False
        else:
            # print("重复过滤")
            return True

    def add_value(self, value):
        # type: (str) -> None
        """将给定值添加到布隆过滤器中。

        Args:
            value: 待添加的字符串值。
        """
        self.redis_conn.execute_command('BF.ADD', self.bf_key, value)

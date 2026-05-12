# -*- coding: utf-8 -*-
"""
MQ 客户端模块。

封装 RocketMQ 生产者，提供消息发送和重试功能。
本模块从 pipeline/draw_and_to_es.py、pipeline/identity_juge.py 等管线文件中
提取重复的 ProducerMQ 类，消除代码重复。
"""

from typing import Optional

from rocketmq import DefaultMQProducer, Message


class ProducerMQ(object):
    """RocketMQ 生产者封装，支持重试和优雅关闭。

    对 rocketmq.DefaultMQProducer 进行封装，提供简洁的消息发送接口，
    支持可配置的重试次数和 oneway 发送模式。

    Attributes:
        host: RocketMQ NameServer 地址
        groupid: 生产者组 ID
        producer: 底层 DefaultMQProducer 实例
    """

    def __init__(self, host, groupid, max_message_size=30000000):
        # type: (str, str, int) -> None
        """初始化 MQ 生产者并启动连接。

        Args:
            host: RocketMQ NameServer 地址，多个地址用分号分隔
            groupid: 生产者组 ID
            max_message_size: 最大消息体大小（字节），默认 30MB
        """
        self.host = host  # type: str
        self.groupid = groupid  # type: str
        self.producer = DefaultMQProducer(self.groupid)  # type: DefaultMQProducer
        self.producer.namesrv_addr = self.host
        self.producer.send_latency_fault_enable = False
        self.producer.max_message_size = max_message_size
        self.producer.start()

    def send2mq(self, info_json, key, topic, retries=3):
        # type: (str, str, str, int) -> str
        """发送消息到 MQ，支持重试。

        使用 oneway 模式发送消息，发送失败时自动重试。
        重试次数由 retries 参数控制，默认重试 3 次。

        Args:
            info_json: JSON 格式的消息体
            key: 消息 key，用于消息路由和查询
            topic: 目标 topic 名称
            retries: 重试次数，默认 3

        Returns:
            空字符串表示发送成功，否则返回最后一次异常的错误信息
        """
        msg = Message(topic=topic, body=info_json)
        msg.wait_store_msg_ok = True
        msg.keys = key
        error = ""  # type: str
        for _ in range(retries):
            try:
                self.producer.sendOneway(msg=msg)
                return ""
            except Exception as e:
                print(e)
                error = str(e)
        return error

    def close(self):
        # type: () -> None
        """关闭生产者连接，释放资源。"""
        self.producer.shutdown()

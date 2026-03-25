# -*- coding: utf-8 -*-
"""
@Time ： 2024/9/10 17:52
@Auth ： liuruixi
@File ：download_API.py
@IDE ：PyCharm
@Motto:project
"""


import requests
import json
import time
import traceback
from multiprocessing import Pool
import arrow
import os
import pandas as pd
import warnings
import numpy as np
from datetime import datetime, timezone
import datetime
import sys

# source = ["app", "blog", "forum", "insvideo", "news", "pingmei", "video", "weibo", "weixin", "tv"]
# label_dict = {'01': '全量新闻', '02': '论坛', '03': '博客', '04': '微博', '06': '微信', '07': '视频', '11': '短视频', '21': '音频电台',
#               '0105': '平媒', '0109': 'APP', '0101': '新闻', '0411': '新浪微博'}



warnings.filterwarnings('ignore')


def isLeapYear(years):
    '''
    通过判断闰年，获取年份years下一年的总天数
    :param years: 年份，int
    :return:days_sum，一年的总天数
    '''
    # 断言：年份不为整数时，抛出异常。
    assert isinstance(years, int), "请输入整数年，如 2018"

    if ((years % 4 == 0 and years % 100 != 0) or (years % 400 == 0)):  # 判断是否是闰年
        # print(years, "是闰年")
        days_sum = 366
        return days_sum
    else:
        # print(years, '不是闰年')
        days_sum = 365
        return days_sum


def getAllDayPerYear(years, start_time="2022-01-01 00:00:00", end_time="2022-11-30 00:00:00", ):
    '''
    获取一年的所有日期
    :param years:年份
    :return:全部日期列表
    '''
    start_date = '%s-1-1' % years
    a = 0
    all_date_list = []
    days_sum = isLeapYear(int(years))
    print()
    while a < days_sum:
        b = arrow.get(start_date).shift(days=a).format("YYYY-MM-DD HH:mm:ss")
        a += 1
        if (b >= start_time) and (b <= end_time):
            all_date_list.append(b)

    # print(all_date_list)
    return all_date_list


# 删除当前接口任务
def delete_cursor(next_cursor):
    while next_cursor != None:
        try:
            delete_url = "https://xgsj.istarshine.com/v3/sliceRemoveTask?token=0d57a4b0-c3da-4abe-b972-a729de1444f5"
            body = {
                "cursor": next_cursor
            }

            headers = {
                "Content-Type": "application/json",
            }
            # results,next_cursor = mydata.iter_search(ids,item,next_cursor,tn)
            requests.post(delete_url, json=body, headers=headers)
            break
            # print(str(tn)+"-"+"iter len results " + str(len(results)))
            # print(str(tn)+"-"+"iter next_cursor " + str(next_cursor))
        except Exception:
            # print(str(tn)+"-"+traceback.format_exc())
            next_cursor = None
            break


class MyData():

    def __init__(self):
        self.url = "https://xgsj.istarshine.com/v3/sliceYSearch?token=0d57a4b0-c3da-4abe-b972-a729de1444f5"
        # self.url = "https://xgsj.istarshine.com/v3/ysearch?token=0d57a4b0-c3da-4abe-b972-a729de1444f5"

    def iter_data(self):

        all_date_list = getAllDayPerYear("2024", start_time="2024-05-01 00:00:00", end_time="2024-08-01 00:00:00", )
        # all_date_list.extend(getAllDayPerYear("2024", start_time="2024-01-01 00:00:00", end_time="2024-09-01 00:00:00", ))
        # all_date_list.extend(getAllDayPerYear("2016", start_time="2016-01-01 00:00:00", end_time="2017-01-01 00:00:00", ))
        # all_date_list.extend(getAllDayPerYear("2017", start_time="2017-01-01 00:00:00", end_time="2018-01-01 00:00:00", ))
        # all_date_list.extend(getAllDayPerYear("2018", start_time="2018-01-01 00:00:00", end_time="2019-01-01 00:00:00", ))
        # all_date_list.extend(getAllDayPerYear("2019", start_time="2019-01-01 00:00:00", end_time="2020-01-01 00:00:00", ))
        # all_date_list.extend(getAllDayPerYear("2020", start_time="2020-01-01 00:00:00", end_time="2021-01-01 00:00:00", ))
        # all_date_list.extend(getAllDayPerYear("2021", start_time="2021-01-01 00:00:00", end_time="2022-01-01 00:00:00", ))
        # all_date_list.extend(getAllDayPerYear("2022", start_time="2022-01-01 00:00:00", end_time="2023-01-01 00:00:00", ))
        tmp_list = []
        now = 0
        # 按月
        # print(all_date_list)
        # for i in range(len(all_date_list)):
        #     if int(all_date_list[i].split("-")[1].strip("0")) != now:
        #         tmp_list.append(all_date_list[i])
        #         now = int(all_date_list[i].split("-")[1].strip("0"))
        # for i in range(1, len(tmp_list)):
        #     yield [tmp_list[i - 1], tmp_list[i]]
        # 按单日
        for i in range(1, len(all_date_list)):
          print(all_date_list[i-1])
          yield [all_date_list[i - 1], all_date_list[i]]

    def iter_data_day(self, item):
        all_date_list = getAllDayPerYear("2024", start_time=item[0], end_time=item[1], )
        # 按单日
        for i in range(1, len(all_date_list)):
            print(all_date_list[i - 1])
            yield [all_date_list[i - 1], all_date_list[i]]


    # 当查询周期过长时重新查询
    def search_data_day(self, body):
        num = 0
        payload = json.dumps(body)

        headers = {
            'Content-Type': 'application/json',
            'Cookie': 'aliyungf_tc=4e55f1debae4224ad61e1bb043e4dec7e2be042a60838d688c91c5733f0b88a8'
        }
        response = requests.request("POST", self.url, headers=headers, data=payload)
        result = json.loads(response.text)
        while True:
            try:
                if result["code"] != 0:
                    num = 0
                    break
                else:
                    num = result['data']['total_count']
                    break
            except Exception:
                print(str("开始") + "-" + "出错详情 " + traceback.format_exc())
                print(str("开始") + "-" + "result详情 " + str(response.text))
                if "您当前有10个任务在运行，超过任务限制数" in response.text:
                    time.sleep(2)
                    continue
                return [], None, num
        return result.get("data", {}).get("statuses", []), result.get("data", {}).get("next_cursor", ""), num

    # 按日获取数据
    def search_data(self, body):
        num = 0

        payload = json.dumps(body)

        headers = {
            'Content-Type': 'application/json',
            'Cookie': 'aliyungf_tc=4e55f1debae4224ad61e1bb043e4dec7e2be042a60838d688c91c5733f0b88a8'
        }
        times = 5
        while times>0:
            try:
                response = requests.request("POST", self.url, headers=headers, data=payload)
                data = json.loads(response.text)
            except Exception:
                print(traceback.print_exc())
                continue
            if data == {'mes': '请求代理超时，请重试', 'status': '-1007', 'data': {}} or "您2s内使用的次数超过了限制" in data.get("mes", ""):
                continue
            if "code" not in data or ("status" in data and data["status"] == "-1007"):
                print('重试')
                times-=1
                time.sleep(0.5)
                continue
            break
        try:
            result = json.loads(response.text)
        except:
            return '无', None, num

        while True:
            try:
                if result["code"] != 0:
                    num = 0
                    break
                else:
                    num = result['data']['total_count']
                    break
            except Exception:
                print(str("开始") + "-" + "出错详情 " + traceback.format_exc())
                print(str("开始") + "-" + "result详情 " + str(response.text))
                if "您当前有10个任务在运行，超过任务限制数" in response.text:
                    time.sleep(2)
                    continue
                elif "查询周期过长，出现网络延迟，请等30s再试，或减少查询时间" in str(response.text):
                    print('查询周期过长')
                    time.sleep(2)
                    delete_cursor(result.get("data", {}).get("next_cursor", ""))
                    print('已停止出错游标')
                    return '查询周期过长', None, num

                return [], None, num
        return result.get("data", {}).get("statuses", []), result.get("data", {}).get("next_cursor", ""), num
        # return num

    def iter_search(self, body,next_cursor):
        body["cursor"]=next_cursor
        payload = json.dumps(body)
        headers = {
            'Content-Type': 'application/json',
            'Cookie': 'aliyungf_tc=4e55f1debae4224ad61e1bb043e4dec7e2be042a60838d688c91c5733f0b88a8'
        }
        response = requests.request("POST", self.url, headers=headers, data=payload)
        result = json.loads(response.text)

        while True:
            try:
                if result["code"] != 0:
                    break
                else:
                    break
            except Exception:
                print(str("开始") + "-" + "出错详情 " + traceback.format_exc())
                print("-" + "出错next_cursor " + str(next_cursor))
                print(str("开始") + "-" + "result详情 " + str(response.text))
                if "您当前有10个任务在运行，超过任务限制数" in response.text:
                    time.sleep(2)
                    continue
                elif "查询周期过长，出现网络延迟，请等30s再试，或减少查询时间" in str(response.text):
                    print('查询周期过长')
                    time.sleep(2)
                    delete_cursor(result.get(next_cursor))
                    print('已停止出错游标')
                    return '查询周期过长', None

                return [], None
            # {"mes": "查询周期过长，出现网络延迟，请等30s再试，或减少查询时间", "status": "-1007", "data": {}}

        return result.get("data", {}).get("statuses", []), result.get("data", {}).get("next_cursor", "")


def time_trans(ctime):
    # 定义日期时间格式
    local_time = datetime.datetime.fromtimestamp(ctime)
    print("Local time:", local_time)
    # 将时间戳转换为UTC时间
    utc_time = str(datetime.datetime.utcfromtimestamp(ctime))
    return utc_time


def get_data(body):
    num = 0
    mydata = MyData()
    time.sleep(1)
    # 将完整时间标准化后传入body中

    results, next_cursor, total_count = mydata.search_data(body)
    # 查询完直接删除任务
    delete_cursor(next_cursor)
    # 判断是否有查询周期过长的情况，有则按天去查
    if results == '查询周期过长':
        print('查询周期过长')
    #     for item in mydata.iter_data_day():
    #         time.sleep(1)
    #         results, next_cursor, total_count = mydata.search_data_day(name, item)
    #         for result in results:
    #             data = result['_source']
    #
    #         while next_cursor != None:
    #             try:
    #                 results, next_cursor = mydata.iter_search(name, item, next_cursor, tn,uid)
    #                 # print(str(tn)+"-"+"iter len results " + str(len(results)))
    #                 # print(str(tn)+"-"+"iter next_cursor " + str(next_cursor))
    #             except Exception:
    #                 # print(str(tn)+"-"+traceback.format_exc())
    #                 next_cursor = None
    #             for result in results:
    #                 data = result['_source']
    else:
        contents=[]
        for result in results:
            data = result['_source']
            contents.append(data)
        return contents,total_count
            # msgid = mq_conn_write.push(data, key=key)
            #mq_conn_read.ack(source_msg_id)
            # if msgid:
            #     pass
            #     print('插入成功')
            #     print(data)
            #     # logger.info(self.index_str+"插入数据成功，url为：{}",key)
            # else:
            #     continue

        #短期任务不做分页
        # while next_cursor != None:
        #     try:
        #         results, next_cursor = mydata.iter_search(body,next_cursor)
        #         # 查询途中遇到‘查询周期过长’
        #         # if results == '查询周期过长':
        #         #     for item in mydata.iter_data_day(item):
        #         #         time.sleep(1)
        #         #         results, next_cursor, total_count = mydata.search_data_day(name, item)
        #         #         for result in results:
        #         #             data = result['_source']
        #         #
        #         #         while next_cursor != None:
        #         #             try:
        #         #                 results, next_cursor = mydata.iter_search(name, item, next_cursor, tn)
        #         #                 # print(str(tn)+"-"+"iter len results " + str(len(results)))
        #         #                 # print(str(tn)+"-"+"iter next_cursor " + str(next_cursor))
        #         #             except Exception:
        #         #                 # print(str(tn)+"-"+traceback.format_exc())
        #         #                 next_cursor = None
        #         #             for result in results:
        #         #                 data = result['_source']
        #         #
        #         #     break
        #         # print(str(tn)+"-"+"iter len results " + str(len(results)))
        #         # print(str(tn)+"-"+"iter next_cursor " + str(next_cursor))
        #     except Exception:
        #         # print(str(tn)+"-"+traceback.format_exc())
        #         next_cursor = None
        #     for result in results:
        #         data = result['_source']
        #         contents.append(data)


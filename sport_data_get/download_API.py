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
            delete_url = "http://xgsj.istarshine.net.cn/v3/sliceRemoveTask?token=0d57a4b0-c3da-4abe-b972-a729de1444f5"
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
        #self.url = "http://xgsj.istarshine.net.cn/v3/sliceYSearch?token=0d57a4b0-c3da-4abe-b972-a729de1444f5"
        self.url = "http://xgsj.istarshine.net.cn/v3/ysearch?token=0d57a4b0-c3da-4abe-b972-a729de1444f5"

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
        #     if int(all_date_list[i].split("-")[1].strip("0")) != now        :
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
        while times > 0:
            try:
                response = requests.request("POST", self.url, headers=headers, data=payload)
                data = json.loads(response.text)
            except Exception:
                print(traceback.print_exc())
                continue
            if data == {'mes': '请求代理超时，请重试', 'status': '-1007', 'data': {}} or "您2s内使用的次数超过了限制" in data.get("mes", ""):
                print(f"请求代理超时或频率限制，等待2秒后重试 (剩余重试次数: {times})")
                time.sleep(2)
                times -= 1
                continue
            if "code" not in data or ("status" in data and data["status"] == "-1007"):
                print(f'首次查询遇到-1007错误，等待5秒后重试 (剩余重试次数: {times})')
                times -= 1
                time.sleep(5)  # 从300秒改为5秒
                continue
            break
        try:
            result = json.loads(response.text)
        except:
            return '无', None, num
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

    def iter_search(self, body, next_cursor, max_retries=3):
        body["cursor"] = next_cursor
        payload = json.dumps(body)
        headers = {
            'Content-Type': 'application/json',
            'Cookie': 'aliyungf_tc=4e55f1debae4224ad61e1bb043e4dec7e2be042a60838d688c91c5733f0b88a8'
        }
        
        retry_count = 0
        while retry_count < max_retries:
            try:
                response = requests.request("POST", self.url, headers=headers, data=payload, timeout=30)
                result = json.loads(response.text)
                
                # 检查返回格式
                if "code" in result:
                    # 正常返回格式
                    if result["code"] != 0:
                        print(f"API返回code非0: {result}")
                        return [], None
                    return result.get("data", {}).get("statuses", []), result.get("data", {}).get("next_cursor", "")
                
                elif "status" in result and result["status"] == "-1007":
                    # 错误格式: {"mes": "查询出现问题", "status": "-1007", "data": {}}
                    print(f"遇到-1007错误，重试 {retry_count + 1}/{max_retries}: {result.get('mes', '')}")
                    retry_count += 1
                    time.sleep(2)
                    continue
                
                else:
                    print(f"未知返回格式: {result}")
                    return [], None
                    
            except requests.exceptions.Timeout:
                print(f"请求超时，重试 {retry_count + 1}/{max_retries}")
                retry_count += 1
                time.sleep(2)
                continue
                
            except Exception as e:
                print(f"iter_search出错: {traceback.format_exc()}")
                print(f"出错next_cursor: {next_cursor}")
                
                # 检查特定错误
                if "您当前有10个任务在运行，超过任务限制数" in str(e):
                    print("任务数超限，等待2秒")
                    time.sleep(2)
                    retry_count += 1
                    continue
                elif "查询周期过长" in str(e):
                    print('查询周期过长，停止查询')
                    return '查询周期过长', None
                
                retry_count += 1
                if retry_count < max_retries:
                    print(f"重试 {retry_count}/{max_retries}")
                    time.sleep(2)
                else:
                    print("达到最大重试次数，放弃")
                    return [], None
        
        print(f"重试{max_retries}次后仍失败")
        return [], None


def time_trans(ctime):
    # 定义日期时间格式
    local_time = datetime.datetime.fromtimestamp(ctime)
    print("Local time:", local_time)
    # 将时间戳转换为UTC时间
    utc_time = str(datetime.datetime.utcfromtimestamp(ctime))
    return utc_time


def get_data(body, max_count=999999999):
    """
    获取数据，支持分页直到达到max_count条
    """
    num = 0
    mydata = MyData()
    next_cursor = None
    
    try:
        time.sleep(1)
        
        results, next_cursor, total_count = mydata.search_data(body)
        
        # 判断是否有查询周期过长的情况
        if results == '查询周期过长':
            print('查询周期过长')
            if next_cursor:
                delete_cursor(next_cursor)
            return [], 0
        
        if results == '无':
            print('首次查询失败')
            if next_cursor:
                delete_cursor(next_cursor)
            return [], 0
        
        contents = []
        for result in results:
            data = result['_source']
            contents.append(data)
            if len(contents) >= max_count:
                break
        
        print(f"第一批获取: {len(contents)} 条, 总数: {total_count}, next_cursor: {next_cursor is not None}")
        
        # 分页获取直到达到max_count
        page_count = 1
        while next_cursor is not None and len(contents) < max_count:
            try:
                page_count += 1
                time.sleep(1)  # 增加间隔避免请求过快
                results, next_cursor = mydata.iter_search(body, next_cursor)
                
                if results == '查询周期过长':
                    print('分页查询周期过长，停止获取')
                    if next_cursor:
                        delete_cursor(next_cursor)
                    break
                
                if not results:
                    print(f"第{page_count}页未获取到数据，停止")
                    break
                    
                for result in results:
                    data = result['_source']
                    contents.append(data)
                    if len(contents) >= max_count:
                        break
                
                print(f"第{page_count}页获取完成，累计: {len(contents)} 条")
                
                if len(contents) >= max_count:
                    print(f"已达到目标数量 {max_count} 条")
                    break
                    
            except KeyboardInterrupt:
                print("\n检测到中断信号，清理资源...")
                if next_cursor:
                    delete_cursor(next_cursor)
                raise
            except Exception as e:
                print(f"分页获取出错: {traceback.format_exc()}")
                print(f"当前已获取 {len(contents)} 条数据，清理游标后继续使用已有数据")
                if next_cursor:
                    delete_cursor(next_cursor)
                break
        
        # 清理游标
        if next_cursor:
            print("清理游标...")
            delete_cursor(next_cursor)
        
        print(f"数据获取完成，共 {len(contents)} 条")
        return contents, total_count
        
    except KeyboardInterrupt:
        print("\n检测到中断信号，清理资源...")
        if next_cursor:
            delete_cursor(next_cursor)
        raise
    except Exception as e:
        print(f"get_data 出现异常: {traceback.format_exc()}")
        if next_cursor:
            print("清理游标...")
            delete_cursor(next_cursor)
        return [], 0
    
    print(f"数据获取完成，共 {len(contents)} 条")
    return contents, total_count


def get_data_by_days(keywords, start_time, end_time, max_count=999999999):
    """
    按天查询数据并汇总
    当时间跨度超过2天时使用此函数
    """
    from daoding_body import split_time_by_day, daoding_body_gen
    
    try:
        # 拆分时间范围
        time_ranges = split_time_by_day(start_time, end_time)
        print(f"时间跨度超过2天，拆分为 {len(time_ranges)} 天查询")
        
        all_contents = []
        total_count_sum = 0
        
        for idx, (day_start, day_end) in enumerate(time_ranges, 1):
            if len(all_contents) >= max_count:
                print(f"已达到目标数量 {max_count} 条，停止查询")
                break
            
            print(f"\n[{idx}/{len(time_ranges)}] 查询时间段: {day_start} ~ {day_end}")
            
            try:
                # 生成当天的查询body
                body = daoding_body_gen(keywords, day_start, day_end)
                
                # 计算当天还需要获取多少条
                remaining = max_count - len(all_contents)
                
                # 查询当天数据
                contents, total_count = get_data(body, max_count=remaining)
                
                if contents:
                    all_contents.extend(contents)
                    total_count_sum += total_count
                    print(f"当天获取 {len(contents)} 条，累计 {len(all_contents)} 条")
                else:
                    print(f"当天未获取到数据")
                
                # 避免请求过快
                if idx < len(time_ranges):
                    time.sleep(2)
                    
            except KeyboardInterrupt:
                print(f"\n检测到中断信号，停止查询")
                print(f"已获取 {len(all_contents)} 条数据")
                raise
            except Exception as e:
                print(f"查询 {day_start} 出错: {str(e)}")
                print(f"跳过该天，继续下一天")
                continue
        
        print(f"\n所有天数查询完成，共获取 {len(all_contents)} 条数据")
        return all_contents, total_count_sum
        
    except KeyboardInterrupt:
        print("\n检测到中断信号，返回已获取的数据")
        raise
    except Exception as e:
        print(f"get_data_by_days 出现异常: {traceback.format_exc()}")
        return [], 0
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


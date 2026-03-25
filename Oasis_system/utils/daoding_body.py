import time

# 时间周期相关处理函数
def time_transfer(start="2026-01-27 00:00:00",end="2026-01-27 18:46:00"):

    timeArray = time.strptime(start, "%Y-%m-%d %H:%M:%S")
    starttime = int(time.mktime(timeArray))

    timeArray2 = time.strptime(end, "%Y-%m-%d %H:%M:%S")
    endtime = int(time.mktime(timeArray2))
    return str(starttime)+'~'+str(endtime)



def daoding_body_gen(keyword, start=None, end=None, size=50, is_expression=False):
    """
    生成道丁接口请求体
    Args:
        keyword: 搜索关键词，多个关键词用中文逗号分隔
        start: 开始时间，格式 "2026-01-27 00:00:00"，默认当天00:00
        end: 结束时间，格式 "2026-01-27 18:00:00"，默认当前时间
        size: 返回条数，默认50
        is_expression: 是否为布尔表达式模式，True则不做任何关键词处理
    """
    source = ["app", "blog", "forum", "insvideo", "news", "pingmei", "video", "weibo", "weixin", "tv"]

    if is_expression:
        # 表达式模式：直接使用，不做任何转换
        processed_keyword = keyword
    else:
        # 简单模式：中文逗号转 OR
        processed_keyword = keyword
        if '，' in keyword:
            processed_keyword = keyword.replace('，', ' OR ')

    if start and end:
        time_range = time_transfer(start, end)
    else:
        time_range = time_transfer()

    final_body = {
        "source": source,
        "keyword": processed_keyword,
        "match_fields": ["title", "content"],
        "size": size,
        "time": time_range
    }
    return final_body
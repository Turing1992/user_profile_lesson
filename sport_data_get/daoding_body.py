import time
from datetime import datetime, timedelta

# 时间周期相关处理函数
def time_transfer(start="2025-06-01 00:00:00",end="2025-06-02 00:00:00"):

    timeArray = time.strptime(start, "%Y-%m-%d %H:%M:%S")
    starttime = int(time.mktime(timeArray))

    timeArray2 = time.strptime(end, "%Y-%m-%d %H:%M:%S")
    endtime = int(time.mktime(timeArray2))
    return str(starttime)+'~'+str(endtime)


def get_time_range_days(start="2025-06-01 00:00:00", end="2025-07-01 00:00:00"):
    """
    计算时间跨度的天数
    """
    start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    delta = end_dt - start_dt
    return delta.days


def split_time_by_day(start="2025-06-01 00:00:00", end="2025-07-01 00:00:00"):
    """
    将时间范围按天拆分
    返回: [(start1, end1), (start2, end2), ...]
    """
    start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    
    time_ranges = []
    current = start_dt
    
    while current < end_dt:
        next_day = current + timedelta(days=1)
        if next_day > end_dt:
            next_day = end_dt
        
        time_ranges.append((
            current.strftime("%Y-%m-%d %H:%M:%S"),
            next_day.strftime("%Y-%m-%d %H:%M:%S")
        ))
        current = next_day
    
    return time_ranges



def daoding_body_gen(keywords, start_time=None, end_time=None):
    source = ["app", "blog", "forum", "insvideo", "news", "pingmei", "video", "weibo", "weixin", "tv"]

    final_body={
            "source":"news,pingmei,app,forum,blog,weibo,weixin,video,insvideo",
            "fields_includes": "uuid,url,web_url,gather,content,title,ctime,channel,user,repost_source,place,position,face_img,surface_img,ocr_dic,pic_urls,video_urls,duration,device,translation,is_junk,edit_count,rank,search_topic_count,search_topic_read_count,trends,hot,type,location,geo,bullet_count,repost_count,reply_count,visit_count,like_count,share_count,video_count,wtype,ori_data,ocr",
            "keyword":keywords,
            "match_fields": ["title",
                             "content",
                             ],
            "sort_of": "ctime+desc",
            "size": 500,
            "time":''
        }

    if start_time and end_time:
        time_range = time_transfer(start_time, end_time)
    else:
        time_range = time_transfer()
    
    # final_body['source']=source
    final_body['time']=time_range
    return final_body
import time

# 时间周期相关处理函数
def time_transfer(start="2026-01-27 00:00:00",end="2026-01-27 18:46:00"):

    timeArray = time.strptime(start, "%Y-%m-%d %H:%M:%S")
    starttime = int(time.mktime(timeArray))

    timeArray2 = time.strptime(end, "%Y-%m-%d %H:%M:%S")
    endtime = int(time.mktime(timeArray2))
    return str(starttime)+'~'+str(endtime)



def daoding_body_gen(keyword):
    keywords=''
    source = ["app", "blog", "forum", "insvideo", "news", "pingmei", "video", "weibo", "weixin", "tv"]
    if '，' in keyword:
        keywords=keywords.replace('，',' OR ')
    final_body={
            "source":'',
            "keyword":keywords,
            "match_fields": ["title",
                             "content",
                             ],
            "size": 50,
            "time":''
        }

    time_range=time_transfer()
    # uid={
    #     "field": "user.uid",
    #     "values": [uid],
    #     "operator": "in"
    # }
    # site_name={
    #     "field": "gather.site_name",
    #     "logic": "in",
    #     "values": [sitename]
    # }
    # final_body['filters']=[site_name,uid]
    final_body['source']=source
    final_body['time']=time_range
    # final_body['keyword']=task_cofi['search_cofi'][0]
    return final_body
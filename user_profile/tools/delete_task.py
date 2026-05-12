import requests
import json
import traceback


def run_tmp_delete():
    headers = {u'Content-Type': u'application/json'}
    url = 'http://xgsj.istarshine.net.cn/v3/sliceRemoveTask?token={}'.format("0d57a4b0-c3da-4abe-b972-a729de1444f5")
    try:
        del_cursor = 'ce27b8b841da30d0596200f55d16cd86db5449707b9ec17c916b3129bdab91f73'
        data_remove = {"cursor": del_cursor}
        result = requests.post(url, data=json.dumps(data_remove), headers=headers,
                               timeout=(20, 20), verify=True)
        print("result=", result)
    except Exception:
        log_msg = "ResClient exception:" + str(traceback.format_exc())
        print(log_msg)


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

if __name__ == '__main__':
    run_tmp_delete()
    # delete_cursor('ce27b8b841da30d0596200f55d16cd86db5449707b9ec17c916b3129bdab91f73')
import requests
import time

def get_douyin_play_count(token: str, video_url: str, publish_time: int):

    url = f"https://xgsj.istarshine.com/v3/douyinInteract?token={token}"
    data = {
        "url": video_url,
        "ctime": publish_time
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(url, data=data, headers=headers, timeout=10)
        response.raise_for_status()  # 检查 HTTP 错误
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None

if __name__ == '__main__':
    info=get_douyin_play_count("0d57a4b0-c3da-4abe-b972-a729de1444f5","https://www.iesdouyin.com/share/video/7568807810889223424","1762250403")
    print(info)
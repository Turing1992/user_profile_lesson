import re
from collections import defaultdict
from utils.flash_user import get_douyin_play_count
from utils.opinin_extract import qiye_expect
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed


def merge_industries(industry_list):
    """合并多个 industry 字符串，拆分关键词并去重"""
    keywords = set()
    for ind in industry_list:
        if not ind:
            continue
        # 支持中文逗号、英文逗号、顿号、空格等分隔
        parts = re.split(r'[,\s，、]+', ind.strip())
        for p in parts:
            p_clean = p.strip()
            if p_clean:
                keywords.add(p_clean)
    return ','.join(sorted(keywords)) if keywords else ""


def merge_field_values(values):
    """将列表中每个字符串按 '/' 拆分，全局去重（保持首次出现顺序），再用 '/' 拼接返回"""
    seen = set()
    unique_tags = []

    for item in values:
        if not item:  # 跳过 None, "", 等 falsy 值
            continue
        # 拆分当前项（支持单个标签或多个）
        parts = str(item).split('/')
        for part in parts:
            part = part.strip()
            if part and part not in seen:
                unique_tags.append(part)
                seen.add(part)

    if len(unique_tags) == 1:
        return unique_tags[0]
    elif len(unique_tags) > 1:
        return "/".join(unique_tags)
    else:
        return ""


def process_single_record(record, task_id):
    user = record.get('user', {})
    username = user.get('nickname') or user.get('name') or 'unknown_user'
    url = record.get('url', '')
    ctime = record.get('ctime', 0)
    content = record.get('content', '')
    ocr = record.get('ocr', '')

    # 初始化默认值
    replay = like = repost = collection = visit = 0
    industries = account_locations = content_styles = content_qualities = []
    brand_url_map = defaultdict(list)

    # 获取互动数据
    try:
        play_stats = get_douyin_play_count(task_id, url, ctime)
        result = play_stats.get('data')
        if result and 'info' in result:
            info = result['info']
            replay = info.get('reply_count', 0)
            like = info.get('like_count', 0)
            collection = info.get('collection_count', 0)
            repost = info.get('repost_count', 0)
            visit = info.get('play_count', 0)  # 注意：疑似应为 'play_count'
    except Exception as e:
        pass  # 保持默认 0

    # 调用 qiye_expect
    full_content = content+ocr
    try:
        qiye_result = qiye_expect(full_content)
        industries = [qiye_result.get('industry', '')]
        account_locations = [qiye_result.get('account_location', '')]
        content_styles = [qiye_result.get('content_style', '')]
        content_qualities = [qiye_result.get('content_quelity', '')]  # 拼写注意

        past_brands = qiye_result.get('past_brands', [])
        for brand in past_brands:
            brand_url_map[brand].append(url)
    except Exception as e:
        pass

    return {
        'username': username,
        'url': url,
        'stats': {
            'replay': replay,
            'like': like,
            'repost': repost,
            'collection': collection,
            'visit': visit
        },
        'industries': industries,
        'account_locations': account_locations,
        'content_styles': content_styles,
        'content_qualities': content_qualities,
        'brand_url_map': dict(brand_url_map)
    }

def process_records(records):
    task_id = '0d57a4b0-c3da-4abe-b972-a729de1444f5'
    user_data = defaultdict(lambda: {
        'total_replay': 0,
        'total_like': 0,
        'total_repost': 0,
        'total_collection': 0,
        'total_visit': 0,
        'urls': [],
        'brand_url_map': defaultdict(list),
        'industries': [],
        'account_locations': [],
        'content_styles': [],
        'content_qualities': []
    })

    # 多线程处理
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_single_record, record, task_id) for record in records]
        for future in as_completed(futures):
            try:
                result = future.result()
                username = result['username']
                user_data[username]['total_replay'] += result['stats']['replay']
                user_data[username]['total_like'] += result['stats']['like']
                user_data[username]['total_repost'] += result['stats']['repost']
                user_data[username]['total_collection'] += result['stats']['collection']
                user_data[username]['total_visit'] += result['stats']['visit']
                user_data[username]['urls'].append(result['url'])

                user_data[username]['industries'].extend(result['industries'])
                user_data[username]['account_locations'].extend(result['account_locations'])
                user_data[username]['content_styles'].extend(result['content_styles'])
                user_data[username]['content_qualities'].extend(result['content_qualities'])

                for brand, urls in result['brand_url_map'].items():
                    user_data[username]['brand_url_map'][brand].extend(urls)
            except Exception as e:
                print(f"Error processing record: {e}")

    # 构建最终输出（保持不变）
    final_output = {}
    for username, data in user_data.items():
        merged_industry = merge_industries(data['industries'])
        merged_account_location = merge_industries(data['account_locations'])
        merged_content_style = merge_industries(data['content_styles'])
        merged_content_quality = merge_industries(data['content_qualities'])

        history_brands = {
            brand: {
                'count': len(set(urls)),
                'urls': list(set(urls))
            }
            for brand, urls in data['brand_url_map'].items()
        }

        final_output[username] = {
            'username': username,
            'total_interactions': {
                'replay': data['total_replay'],
                'like': data['total_like'],
                'repost': data['total_repost'],
                'collection': data['total_collection'],
                'visit': data['total_visit']
            },
            'industry': merged_industry,
            'account_location': merged_account_location,
            'content_style': merged_content_style,
            'content_quality': merged_content_quality,
            'history_brands': history_brands,
            'total_posts': len(data['urls'])
        }

    return final_output

if __name__ == '__main__':
    import json

    records = []
    with open('douyindata.json', 'r', encoding='utf-8') as f:
        for line in f:
            records.append(json.loads(line.strip()))

    result = process_records(records)

    # 转换为 DataFrame
    rows = []
    for username, data in result.items():
        row = {
            'username': data['username'],
            'total_replay': data['total_interactions']['replay'],
            'total_like': data['total_interactions']['like'],
            'total_repost': data['total_interactions']['repost'],
            'total_collection': data['total_interactions']['collection'],
            'total_visit': data['total_interactions']['visit'],
            'industry': data['industry'],
            'account_location': data['account_location'],
            'content_style': data['content_style'],
            'content_quality': data['content_quality'],
            'total_posts': data['total_posts'],
            'history_brands': str(data['history_brands'])  # 转为字符串存入 Excel
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_excel('douyin_analysis_output.xlsx', index=False, engine='openpyxl')
    print("✅ 结果已保存到 douyin_analysis_output.xlsx")
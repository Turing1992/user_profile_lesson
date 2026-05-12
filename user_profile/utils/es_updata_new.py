import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from opensearchpy import OpenSearch
from utils.about_log import get_logger
from config.settings import opensearch_config

# 全局 client（线程安全，OpenSearch 客户端本身是线程安全的）
client = OpenSearch(**opensearch_config)

# 日志
logger = get_logger("es_updata")


# sitename 映射表（复用你已有的逻辑）
def build_sitename_to_target_index_map():
    mapping_rules = {
        "media_douyin": ["抖音", "西瓜视频"],
        "media_weibo": ["新浪微博", "新浪长微博", "新浪微博视频", "新浪看点"],
        "media_weixin": ["微信视频号", "微信"],
        "media_kuaishou": ["快手", "快手极速版"],
        "media_douban": ["豆瓣广场", "豆瓣"],
        "media_baidu": ["百度贴吧", "百度百家", "度小视", "好看视频", "有驾", "百度知道"],
        "media_xhs": ["小红书"],
        "media_bilibili": ["bilibili"],
        "media_zhihu": ["知乎问答", "知乎", "知乎专栏", "知乎问题", "知乎视频"],
        "media_toutiao": ["今日头条"],
        "media_other": [
            "腾讯网", "企鹅号", "腾讯看点", "腾讯视频", "快资讯", "一点资讯",
            "UC头条", "UC", "搜狐新闻", "趣头条", "网易号", "澎湃新闻"
        ],
    }
    sitename_to_index = {}
    for target_index, sitenames in mapping_rules.items():
        for name in sitenames:
            if name in sitename_to_index:
                logger.warning(f"⚠️ sitename '{name}' 重复定义！已存在映射到 {sitename_to_index[name]}")
            sitename_to_index[name] = target_index
    return sitename_to_index


SITENAME_TO_TARGET_INDEX = build_sitename_to_target_index_map()


def clean_empty_bracket(value):
    if isinstance(value, str):
        cleaned = value.replace("[ ]", "").strip()
        return cleaned if cleaned != "" else None
    return value


def update_single_profile(doc: Dict[str, Any]) -> bool:
    """
    更新单条用户画像数据到目标 OpenSearch 索引。

    Args:
        doc (dict): 必须包含 'id', 'uid', 'sitename', 'identity' 等字段

    Returns:
        bool: True 表示成功（无论插入或更新），False 表示跳过或失败
    """
    try:
        # 1. 提取必要字段
        doc_id = doc.get("id")
        uid = doc.get("uid")
        sitename = doc.get("site_name")
        identity = doc.get("identity")

        if not doc_id or not uid or not sitename or not identity:
            logger.warning(f"❌ 缺少必要字段: id={doc_id}, uid={uid}, site_name={sitename}, identity={identity}")
            return False

        if not isinstance(sitename, str):
            logger.warning(f"❌ site_name 非字符串: {sitename}")
            return False

        # 2. 确定目标索引
        target_index = SITENAME_TO_TARGET_INDEX.get(sitename)
        if not target_index:
            logger.warning(f"❓ 未知 site_name: '{sitename}', 跳过 id={doc_id}")
            return False

        # 3. 检查目标索引是否存在（懒创建）
        # if not client.indices.exists(index=target_index):
        #     mapping = {
        #         "mappings": {
        #             "properties": {
        #                 "uid": {"type": "keyword"},
        #                 "sitename": {"type": "keyword"},
        #                 "identity": {"type": "text"},
        #                 "community": {"type": "text"},
        #                 "identity_standerd": {"type": "keyword"},
        #                 "industry": {"type": "keyword"},
        #                 "name": {"type": "text"},  # 对应 username
        #                 "site_name": {"type": "keyword"},  # 对应 sitename
        #                 "create_time": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss"},
        #             }
        #         }
        #     }
        #     client.indices.create(index=target_index, body=mapping)
        #     logger.info(f"✅ 索引 '{target_index}' 已创建")

        # 4. 查询是否已存在
        try:
            resp = client.get(
                index=target_index,
                id=doc_id,
                _source=["identity"],
                ignore=[404]
            )
            exists = resp.get("found", False)
            old_identity = None
            if exists:
                src = resp.get("_source", {})
                old_identity = src.get("identity")
        except Exception as e:
            logger.error(f"❌ get 文档失败 (id={doc_id}, index={target_index}): {e}")
            return False

        # 5. 决策：跳过 / 更新 / 插入
        if exists:
            # 如果旧 identity 非空，则跳过
            # if old_identity and isinstance(old_identity, str) and old_identity.strip():
            #     logger.debug(f"⏭️ 跳过更新（已有 identity）: id={doc_id}")
            #     return True  # 视为成功（只是跳过）

            # 否则尝试更新指定字段
            update_doc = {}
            for field in ['identity', 'community', 'identity_standerd', 'industry']:
                val = doc.get(field)
                cleaned = clean_empty_bracket(val)
                if cleaned is not None:
                    update_doc[field] = cleaned

            if not update_doc:
                logger.debug(f"⏭️ 无有效字段可更新: id={doc_id}")
                return True

            # 执行 update
            client.update(
                index=target_index,
                id=doc_id,
                body={"doc": update_doc}
            )
            logger.debug(f"🔄 更新成功: id={doc_id} -> {list(update_doc.keys())}")
            return True

        else:
            field_mapping = {
                'id': 'uid',
                'sitename': 'site_name',  # 修改为 site_name
                'age': 'age',
                'identity': 'identity',
                'identity_standerd': 'identity_standerd',
                # 注意：这里用 user_name 作为 name，忽略 data["name"]
                'user_name': 'name',  # user_name → name
                'verified_reason': 'verified_reason',
                'description': 'description',
                'ip_region': 'ip_region',
                'gender': 'gender',
                'followers_count': 'followers_count',
                'three_new_identity': 'three_new_identity',
                'community': 'community',
                # 注意：原始 data["name"] 被跳过，未包含在此映射中
            }
            # 插入新文档
            insert_doc = {}
            for field in [
                'identity', 'community', 'identity_standerd', 'industry',
                'description', 'uid', 'site_name', 'name', 'three_new_identity','verified_reason','ip_region','gender','age','followers_count'
            ]:
                val = doc.get(field)
                cleaned = clean_empty_bracket(val)
                if cleaned is not None:
                    if field == 'sitename':
                        insert_doc['site_name'] = cleaned
                    elif field == 'username':
                        insert_doc['name'] = cleaned
                    elif field == 'age':
                        # LLM 可能返回 "30岁" 等非纯数字，提取数字部分
                        import re
                        age_match = re.search(r'\d+', str(cleaned))
                        if age_match:
                            insert_doc['age'] = int(age_match.group())
                    else:
                        insert_doc[field] = cleaned

            insert_doc['id'] = doc_id
            insert_doc['create_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            client.index(
                index=target_index,
                id=doc_id,
                body=insert_doc
            )
            logger.debug(f"➕ 插入成功: id={doc_id}")
            return True

    except Exception as e:
        logger.error(f"💥 更新失败 (id={doc.get('id')}): {traceback.format_exc()}")
        return False

if __name__ == '__main__':
    record = {
        "id": "抖音|user123liuruixi",
        "uid": "user123liuruixi",
        "site_name": "抖音",
        "identity": "时尚达人",
        "community": "AI爱好者",
        "name": "张三",
        "industry": "互联网"
    }

    success = update_single_profile(record)
    if success:
        print("✅ 处理成功")
    else:
        print("❌ 处理失败或跳过")
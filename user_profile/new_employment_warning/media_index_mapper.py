# -*- coding: utf-8 -*-
"""预警 siteName → media_* 目标索引与标准 site_name 的解析。

回写画像时，文档 ``_id`` 必须是 ``site_name|uid``，且 ``site_name`` 要与
``media_*`` 索引里已有的取值完全一致，否则会查不到已有账号、造成重复插入。

预警索引的 ``siteName`` 存在两类与 ``media_*`` 不一致的情况，都在这里统一处理：

1. **带栏目后缀**：``今日头条-其他``、``百度百家-文章``、``bilibili-``、
   ``UC-社会``、``网易号-社会/百态``、``腾讯网-`` 等，需要截断到主站名；
2. **叫法不同**：``新浪新闻`` 实际落在 ``新浪微博``，``知乎回答`` / ``知乎想法``
   实际落在 ``知乎问答``。

下面的映射表取自线上 ``media_*`` 索引 ``site_name.keyword`` 的真实聚合结果，
不在表内的站点（如 ``腾讯新闻``、``黑猫投诉``、``消费保-投诉``）没有对应画像索引，
解析结果为 ``(None, None)``，调用方应跳过并计入统计。
"""


# media_* 索引 -> 该索引下真实存在的 site_name 取值。
MEDIA_INDEX_SITE_NAMES = {
    "media_douyin": ["抖音", "西瓜视频"],
    "media_toutiao": ["今日头条"],
    "media_weibo": ["新浪微博", "新浪微博视频", "新浪长微博", "新浪看点"],
    "media_weixin": ["微信", "微信视频号"],
    "media_kuaishou": ["快手", "快手极速版"],
    "media_xhs": ["小红书"],
    "media_bilibili": ["bilibili"],
    "media_douban": ["豆瓣", "豆瓣广场"],
    "media_baidu": [
        "百度贴吧", "百度百家", "有驾", "好看视频", "度小视", "百度知道",
    ],
    "media_zhihu": ["知乎问答", "知乎专栏", "知乎视频", "知乎问题"],
    "media_other": [
        "懂车帝", "搜狐新闻", "趣头条", "网易号", "UC", "UC头条",
        "腾讯视频", "腾讯网", "腾讯看点", "企鹅号", "一点资讯", "QQ浏览器",
        "微视", "澎湃新闻", "快资讯", "二三里", "凤凰网", "凤凰新闻",
        "汽车之家", "央视频", "手机新浪网", "ZAKER",
    ],
}

# site_name -> media_* 索引。
# 同名站点在多个索引都有少量数据时（如"懂车帝"、"西瓜视频"），
# 以数据量占绝对多数的索引为准，先定义者优先。
MEDIA_INDEX_BY_SITE = {}
for _index, _site_names in MEDIA_INDEX_SITE_NAMES.items():
    for _site_name in _site_names:
        MEDIA_INDEX_BY_SITE.setdefault(_site_name, _index)


# 预警 siteName 与 media_* site_name 叫法不一致时的显式别名。
SITE_NAME_ALIASES = {
    "新浪新闻": "新浪微博",
    "微博": "新浪微博",
    "知乎回答": "知乎问答",
    "知乎想法": "知乎问答",
    "微信公众号": "微信",
    "百家号": "百度百家",
    "头条": "今日头条",
    "B站": "bilibili",
    "哔哩哔哩": "bilibili",
}

# 栏目后缀分隔符：预警侧形如「今日头条-微头条」「网易号-社会/百态」。
_SUFFIX_SEPARATORS = ("-", "—", "|", "/")


def _strip_column_suffix(site_name):
    # type: (str) -> str
    """截断栏目后缀，取主站名。

    Args:
        site_name: 原始 siteName，如 ``今日头条-微头条``。

    Returns:
        主站名，如 ``今日头条``；无后缀时原样返回。
    """
    result = site_name
    for separator in _SUFFIX_SEPARATORS:
        if separator in result:
            result = result.split(separator, 1)[0]
    return result.strip()


def normalize_site_name(raw_site_name):
    # type: (str) -> str
    """把预警 siteName 归一为 media_* 里真实使用的 site_name。

    解析顺序：精确命中 → 别名表 → 截断栏目后缀后重试精确命中和别名表。

    Args:
        raw_site_name: 预警索引里的 siteName。

    Returns:
        归一后的 site_name；无法归一时返回空串。
    """
    site_name = str(raw_site_name or "").strip()
    if not site_name:
        return ""
    if site_name in MEDIA_INDEX_BY_SITE:
        return site_name
    if site_name in SITE_NAME_ALIASES:
        return SITE_NAME_ALIASES[site_name]

    trimmed = _strip_column_suffix(site_name)
    if trimmed and trimmed != site_name:
        if trimmed in MEDIA_INDEX_BY_SITE:
            return trimmed
        if trimmed in SITE_NAME_ALIASES:
            return SITE_NAME_ALIASES[trimmed]
    return ""


def resolve_media_target(raw_site_name):
    # type: (str) -> tuple
    """解析预警 siteName 对应的标准 site_name 与目标 media_* 索引。

    Args:
        raw_site_name: 预警索引里的 siteName。

    Returns:
        tuple: ``(site_name, media_index)``。无对应画像索引时返回 ``("", "")``。
    """
    site_name = normalize_site_name(raw_site_name)
    if not site_name:
        return "", ""
    return site_name, MEDIA_INDEX_BY_SITE.get(site_name, "")


def build_doc_id(site_name, uid):
    # type: (str, str) -> str
    """按 media_* 的既有规则拼接文档 ``_id``。

    Args:
        site_name: 已归一的 site_name。
        uid: 账号 id（预警侧的 ``author_persona.id``）。

    Returns:
        形如 ``抖音|101780330080`` 的文档 id；缺少任一部分时返回空串。
    """
    site_name = str(site_name or "").strip()
    uid = str(uid or "").strip()
    if not site_name or not uid:
        return ""
    return "{}|{}".format(site_name, uid)

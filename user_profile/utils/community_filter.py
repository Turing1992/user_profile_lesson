# -*- coding: utf-8 -*-
"""
社区(community)标签过滤模块。

在 LLM 判断出 community 后进行规则过滤，排除明显的非目标人群账号：
- 商家/店铺/公司、影视/短剧/小说、广告/营销、餐饮、美容、房产、
  教育、律师、医疗、汽车相关等
- 平台认证为商家/机构类（非个人认证）的账号

使用方式::

    from utils.community_filter import CommunityFilter

    cfg = {
        "enabled": True,
        "junk_categories": ["shop", "media", "ad"],
        "filter_merchant_verified": True,
    }
    cf = CommunityFilter(cfg)
    new_community = cf.apply(community, name, description, verified_reason)
"""

from typing import Iterable, List, Optional


# ==================== 内置分类关键词 ====================

JUNK_KEYWORD_CATEGORIES = {
    # 开店/商家类
    "shop": [
        "店", "厂", "公司", "有限", "商贸", "旗舰", "超市",
        "药房", "专卖", "批发", "经销", "供应", "贸易",
    ],
    # 影视/小说/剧情类
    "media": [
        "影视", "短剧", "小说", "电影", "电视剧",
        "追剧", "剧情", "动漫", "漫画",
    ],
    # 广告/营销类
    "ad": [
        "招聘", "加盟", "代理", "免费领", "优惠", "折扣",
        "推广", "引流", "变现", "赚钱", "日入", "月入",
    ],
    # 餐饮/美食类
    "food": [
        "餐饮", "美食", "奶茶", "烧烤", "火锅", "小吃",
        "蛋糕", "面包", "饭店", "食品",
    ],
    # 美容/护肤类
    "beauty": [
        "美容", "护肤", "化妆", "美甲", "美发", "减肥", "瘦身",
    ],
    # 房产/装修类
    "realestate": [
        "房产", "楼盘", "装修", "家具", "建材", "地产",
    ],
    # 教育/培训类
    "edu": [
        "教育", "培训", "驾校", "考试", "辅导", "课程",
    ],
    # 律师/法律类
    "lawyer": ["律师", "法律", "律所"],
    # 医疗类
    "medical": [
        "医院", "医生", "诊所", "中医", "牙科", "口腔",
    ],
    # 汽车相关类
    "car": [
        "汽车", "4s", "车行", "修车", "洗车", "轮胎", "二手车",
    ],
}

# 全部类别（默认启用所有类别）
ALL_CATEGORIES = list(JUNK_KEYWORD_CATEGORIES.keys())

# 商家/机构类认证关键词（非个人认证）
DEFAULT_MERCHANT_VERIFIED_KEYWORDS = [
    # 商家/公司/机构类
    "商家认证", "店铺账号", "店铺授权", "公司", "机构",
    "企业", "组织", "事业单位", "报社", "电视台",
    # 大V/博主/自媒体类（平台内容创作者认证，通常非目标人群）
    "博主", "创作者", "自媒体", "达人", "领域", "作家",
    "乘风计划", "头条文章", "优质", "原创",
]


def _contains_any(text, keywords):
    # type: (str, Iterable[str]) -> bool
    """检查文本是否包含任一关键词（大小写不敏感匹配英文关键词）。"""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


class CommunityFilter(object):
    """community 标签过滤器。

    根据账号的 name、description、verified_reason 字段，
    判断 LLM 给出的 community 标签是否应被清空。

    Attributes:
        enabled: 是否启用过滤。
        junk_keywords: 合并后的非目标人群关键词列表。
        merchant_verified_keywords: 商家认证关键词列表。
        filter_merchant_verified: 是否启用商家认证过滤。
        keep_personal_verified: 是否保留含"个人"字样的认证。
    """

    def __init__(self, cfg=None):
        # type: (Optional[dict]) -> None
        """初始化过滤器。

        Args:
            cfg: 过滤配置字典，支持以下字段（全部可选）:

                - ``enabled`` (bool): 是否启用过滤，默认 True。
                  设为 False 时 ``apply`` 直接返回原 community。
                - ``junk_categories`` (list[str]): 启用的非目标人群关键词类别，
                  默认 ``ALL_CATEGORIES``。可选值见 ``JUNK_KEYWORD_CATEGORIES`` 的 key。
                - ``extra_junk_keywords`` (list[str]): 在内置类别外追加的关键词。
                - ``filter_merchant_verified`` (bool): 是否对商家/机构类认证过滤，默认 True。
                - ``merchant_verified_keywords`` (list[str]): 自定义商家认证关键词，
                  默认 ``DEFAULT_MERCHANT_VERIFIED_KEYWORDS``。
                - ``keep_personal_verified`` (bool): 是否把含"个人"字样的认证视为有效，默认 True。
                - ``allowed_communities`` (list[str]): community 白名单。
                  非空时，过滤后仍不在白名单中的 community 也会被清空。
                  默认为 ``None``（不启用白名单校验）。
        """
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))

        categories = cfg.get("junk_categories", ALL_CATEGORIES)
        junk = []  # type: List[str]
        for cat in categories:
            junk.extend(JUNK_KEYWORD_CATEGORIES.get(cat, []))
        junk.extend(cfg.get("extra_junk_keywords", []))
        # 去重保持顺序
        seen = set()
        self.junk_keywords = [x for x in junk if not (x in seen or seen.add(x))]

        self.filter_merchant_verified = bool(cfg.get("filter_merchant_verified", True))
        self.merchant_verified_keywords = cfg.get(
            "merchant_verified_keywords", DEFAULT_MERCHANT_VERIFIED_KEYWORDS
        )
        self.keep_personal_verified = bool(cfg.get("keep_personal_verified", True))

        # community 白名单：非空时，不在白名单中的 community 一律清空
        allowed = cfg.get("allowed_communities")
        self.allowed_communities = set(allowed) if allowed else None

    def is_junk_account(self, name, description):
        # type: (str, str) -> bool
        """基于 name + description 判断是否为非目标人群账号。

        Args:
            name: 账号名称。
            description: 账号简介。

        Returns:
            True 如果命中非目标人群关键词，否则 False。
        """
        combined = str(name or "") + str(description or "")
        return _contains_any(combined, self.junk_keywords)

    def is_merchant_verified(self, verified_reason):
        # type: (str) -> bool
        """判断是否为商家/机构类认证（需要过滤）。

        规则：
        - 空认证不视为商家认证；
        - ``keep_personal_verified=True`` 时，含"个人"的认证视为有效，不过滤；
        - 其他情况下若命中商家关键词则视为需过滤。

        Args:
            verified_reason: 平台认证原因文本。

        Returns:
            True 如果是商家/机构认证需要过滤，否则 False。
        """
        if not self.filter_merchant_verified:
            return False
        if not verified_reason:
            return False
        vr = str(verified_reason).strip()
        if vr in ("", "None"):
            return False
        if self.keep_personal_verified and "个人" in vr:
            return False
        return _contains_any(vr, self.merchant_verified_keywords)

    def should_filter(self, name, description, verified_reason=""):
        # type: (str, str, str) -> bool
        """综合判断是否应过滤 community 标签。

        Args:
            name: 账号名称。
            description: 账号简介。
            verified_reason: 平台认证原因，默认空串。

        Returns:
            True 如果应过滤（清空 community），否则 False。
        """
        if not self.enabled:
            return False
        if self.is_junk_account(name, description):
            return True
        if self.is_merchant_verified(verified_reason):
            return True
        return False

    def apply(self, community, name, description, verified_reason=""):
        # type: (str, str, str, str) -> str
        """对 community 标签应用过滤。

        执行顺序：
        1. 若过滤器未启用或 community 为空，直接返回原值；
        2. 命中 name/description 非目标人群关键词 → 返回 ""；
        3. 命中商家/机构类认证 → 返回 ""；
        4. 白名单启用时，community 不在白名单中 → 返回 ""；
        5. 否则返回原 community。

        Args:
            community: LLM 给出的 community 标签。
            name: 账号名称。
            description: 账号简介。
            verified_reason: 平台认证原因。

        Returns:
            过滤后的 community 值，命中过滤时返回空串，否则返回原值。
        """
        if not community or not self.enabled:
            return community
        if self.should_filter(name, description, verified_reason):
            return ""
        # 白名单校验：不在白名单中的 community 一律清空
        if self.allowed_communities is not None and community not in self.allowed_communities:
            return ""
        return community


# 全局默认实例，供不传配置的调用方使用
default_filter = CommunityFilter()

# -*- coding: utf-8 -*-
"""新就业群体人工预警识别 - 配置。

集中管理：
- 源索引（人工预警 artificial_warning_push_*）
- OpenSearch 连接（复用集群 opensearch-o-00o160its7w7）
- 大模型（火山引擎/豆包）身份判断参数
- 扫描 / 去重 / 目标 media 索引映射
"""
import os

from utils.path_resolver import get_path_no_check


# ===== OpenSearch 连接 =====
# 复用 user_profile 里的 ca.cer；沿用统一集群。
ES_CONFIG = {
    "hosts": ["https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200"],
    "http_auth": ("admin", "Zhxg09z11@"),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": get_path_no_check("ca.cer"),
    "timeout": 120,
}

# ===== 源索引：人工预警 =====
# 先用 2026 年做验证；如需其它年份改这里即可。
SOURCE_INDEX = os.environ.get("WARNING_SOURCE_INDEX", "artificial_warning_push_2026")

# ===== 大模型 =====
# 判断算法统一走线上实时管线在用的阿里云百炼 qwen3.5-flash，
# 实际调用参数见 utils/http_llm_factory.py，封装见 new_employment_warning/llm_client.py。
# 下面三个火山引擎（豆包）配置已停用，仅为兼容历史脚本保留。
LLM_API_KEY = os.environ.get("ARK_API_KEY", "9ae7fe44-6195-4c9f-93b0-e95a250415a2")
LLM_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
LLM_MODEL = "ep-20250618113756-95fzt"
LLM_TIMEOUT = 30

# ===== 新就业群体类别 =====
# 与 utils/opinin_extract.py / community_filter 中的 community 取值保持一致。
NEW_EMPLOYMENT_COMMUNITIES = ["外卖员", "网约车司机", "货车司机", "快递员"]

# ===== 扫描参数 =====
SCAN_CONFIG = {
    "batch_size": 500,          # 每批 scroll 拉取条数
    "scroll_ttl": "5m",         # scroll 上下文存活时间
    "max_docs": None,           # 最多扫描的原始帖文数；None=全量
    "max_content_len": 1000,    # 送模型的正文最大截断长度
    "judge_workers": 16,        # 身份判断并发线程数
    "skip_text_over": 200,      # 正文超过该长度直接判为"非新就业群体"（与 prompt 规则一致）
}

# ===== 每日批量任务（daily_identity_job）=====
# 每天跑一次，把当天预警账号的身份算出来并回写 media_*。
JOB_CONFIG = {
    "page_size": 300,            # 候选帖每页拉取条数（search_after 翻页）
    # 按时间分片拉取：一天的候选集有 7 万+ 帖，单窗口 search_after 深度分页会让
    # ES 请求越来越慢直至读超时。按小时切片后每片只有几千条、翻页很浅，稳定得多。
    "window_hours": 1,
    "es_timeout": 300,           # 单次 ES 请求超时（秒）
    "es_retries": 2,             # ES 读超时后的重试次数
    "posts_per_account": 3,      # 每个账号最多保留几条帖文送判断
    "max_content_len": 1200,     # 正文送模型的最大长度
    "judge_workers": 16,         # 模型判断并发线程数
    "max_accounts": None,        # 账号数上限；None=当天全量
    "max_judge": None,           # 模型调用次数上限；None=不限
}

# ===== 历史回溯任务（backfill_identity_job）=====
# 历史数据量级很大（2025 单年身份词候选唯一账号 528 万，2026 至今 404 万），
# 所以回溯必须做跨天、跨运行的账号级去重，并支持断点续跑和限速。
BACKFILL_CONFIG = {
    # 账号级去重用的 Redis 布隆过滤器 key。
    # 换算法口径需要整体重算时，换一个 key（或删掉旧 key）即可。
    "bloom_key": "warning_identity_backfill_v1",
    # 是否跳过 media_* 里已有 identity/community 的账号。
    # 开启能省大量模型调用，但旧身份可能是历史口径写的，质量不一定达标。
    "skip_existing_identity": True,
    "judge_workers": 24,         # 回溯不抢线上资源时可以比增量路更高
    "day_sleep_seconds": 2,      # 每天之间的间隔，避免持续打满 ES / LLM
    "max_judge_per_day": None,   # 单日模型调用上限；None=不限
    "max_judge_total": None,     # 本次运行总上限，便于分批跑
}

# ===== 结果输出 =====
OUTPUT_DIR = os.environ.get(
    "WARNING_OUTPUT_DIR",
    os.path.join(os.path.dirname(__file__), "output"),
)


# ===== siteName -> 目标 media_* 索引映射 =====
# 复用 utils/es_updata_new.py 的映射规则，保持与主流程一致。
def build_sitename_to_media_index():
    # type: () -> dict
    """构建 siteName -> media_* 目标索引映射。

    Returns:
        dict: {siteName: media_index}。
    """
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
            "UC头条", "UC", "搜狐新闻", "趣头条", "网易号", "澎湃新闻",
        ],
    }
    sitename_to_index = {}
    for target_index, sitenames in mapping_rules.items():
        for name in sitenames:
            sitename_to_index[name] = target_index
    return sitename_to_index


SITENAME_TO_MEDIA_INDEX = build_sitename_to_media_index()

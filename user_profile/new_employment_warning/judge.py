# -*- coding: utf-8 -*-
"""新就业群体身份判断。

复用 user_profile 的判断算法（utils/opinin_extract.py 里的四类严格规则），
将外卖员 / 网约车司机 / 货车司机 / 快递员四类合并为单次大模型调用，
在保证判断口径一致的同时降低调用成本。

模型统一走线上阿里云百炼 qwen3.5-flash（``new_employment_warning.llm_client``）。

输入 = 标题(title) + 正文(content) + 账号名(name)，与需求一致。
"""
import re

from utils.community_filter import CommunityFilter
from new_employment_warning.llm_client import chat_json, strip_json
from new_employment_warning.config import (
    NEW_EMPLOYMENT_COMMUNITIES,
    SCAN_CONFIG,
)


# 合并四类判断的系统提示词（证据接地版）。
# 核心思想：判定必须有可原文引用的"直接证据"，禁止仅凭情境线索推断。
# 反面示例取自真实误判：堵车/塌方/开了一路车/压车/骑车查超速 等情境不能推断职业。
JUDGE_PROMPT = """你是"新就业群体"身份判定专家。我会给你一个账号的发帖数据（账号名 + 标题 + 正文），
请判定该账号的【发帖人本人】当前是否为以下四类新就业群体之一，并给出具体类别：
- 外卖员：网约配送员/外卖骑手，通过美团、饿了么等平台接单送餐送货
- 网约车司机：跑滴滴/快车/专车/顺风车/出租车等载客运营
- 货车司机：驾驶货车/卡车/半挂从事货物运输（含长途货运、同城拉货、配货）
- 快递员：从事快递揽收、派送、驿站收发

## 核心原则：只认"直接证据"，严禁情境推断
判定为四类之一，必须能在文本中找到至少一条【直接证据】，并可原文引用。直接证据仅限：
A. 本人自述职业身份：如"我是外卖员/骑手""我跑滴滴""我是货车司机/卡友""我送快递"
B. 本人自述从业工作行为（第一人称 + 具体职业动作）：如"我今天跑了30单""我拉了一车货没收到运费""我接的机场单""我派件"
C. 账号名或话题标签带明确职业标签，且正文内容不矛盾：如账号名含"货车司机"、话题"#外卖员 #网约车司机 #货运"

## 必须判为"其他"的情况（严格排除，宁缺毋滥）
1. 只有情境/场景线索、无本人从业表述：堵车、塌方、开了一路车、压车、路况、油价、加运费、无人区、跑长途等——这些都【不能】推断职业
2. 交通工具 ≠ 职业：骑电动车/摩托、开车、开大车本身不代表外卖员或司机
3. 消费者视角：点外卖的、坐网约车的、寄/收快递的
4. 描述他人：第三人称、他人姓名、"我朋友/我老公是…"
5. 新闻、政务通报、小说、短剧、剧情、影视解说、段子
6. 广告、招聘、加盟、代理、营销、引流
7. 从原文找不到 A/B/C 任一条直接证据

## 输出（只返回一个 JSON，不要任何多余文字）
- 命中四类之一：identity 填"平台配送与运输从业者"，identity2 填具体类别，
  evidence 填【原文中支撑判定的证据句摘录】，log 填简要理由
- 未命中：identity、identity2、evidence 均为空字符串，log 说明归"其他"的原因
- identity2 取值只能是：外卖员 / 网约车司机 / 货车司机 / 快递员 / 其他
- 格式示例：
{"identity":"平台配送与运输从业者","identity2":"货车司机","evidence":"卸完车不给运费，提醒卡友先结运费","log":"本人自述从事货物运输并自称卡友"}

## 参考示例（正例）
- "我从临沂到沈阳拉百货，卸完车不给运费，提醒卡友" → 货车司机（B：本人拉货 + 卡友自称）
- "雇我的货车给他拉了12车设备没给运费" → 货车司机（B：本人的货车从事运输）
- "#网约车司机 虹桥机场接的场站单被抢，滴滴不管" → 网约车司机（B/C：本人接单 + 标签）
- "我上个月跑京东外卖摔骨折了，找平台保险" → 外卖员（B：本人跑外卖）

## 参考示例（反例，必须判"其他"）
- "在塌方路段睡了两晚，今天能不能通" → 其他（仅情境，无从业证据）
- "国道堵车，加运费吧，堵了十一个小时" → 其他（情境词，未自述本人拉货）
- "压车二十天了，孤独寂寞冷" → 其他（仅情境，无本人从业表述）
- "从石家庄到日照开了一路车，这顿饭真贵" → 其他（开车≠货车司机，可能自驾）
- "骑车遇查超速，红绿灯时间短" → 其他（骑车≠外卖员）

信息如下：
"""


# community 过滤器：沿用默认规则，排除商家/机构/影视小说等明显非目标账号。
_community_filter = CommunityFilter()


# 四类新就业群体的"明确职业标签"词表，用于模型判定后的确定性硬门槛校验。
# 目的：排除“的哥”“最后一单”“送单”等歧义词和 OCR 噪声造成的误判。
NEW_EMPLOYMENT_HARD_TERMS = {
    "外卖员": [
        "外卖员", "外卖骑手", "外卖小哥", "跑外卖", "送外卖",
        "美团骑手", "饿了么骑手", "众包骑手", "配送骑手",
    ],
    "网约车司机": [
        "网约车司机", "滴滴司机", "跑滴滴", "出租车司机",
        "的士司机", "网约车车主", "滴滴车主",
    ],
    "货车司机": [
        "货车司机", "卡车司机", "货运司机", "跑货运", "卡友",
        "半挂司机", "大车司机",
    ],
    "快递员": [
        "快递员", "快递小哥", "快递骑手", "送快递", "派件员",
        "快递驿站工作人员",
    ],
}

_FIRST_PERSON_ACTION = re.compile(
    r"(?:我|本人|咱们|我们).{0,16}(?:跑|送|接|拉|开|派|揽|运|卸|装|抢|配送|营运)"
)

# 第一人称紧跟职业名词的直接自述（如"本人外卖骑手""我是一名货车司机"），
# 这类证据比"职业词 + 从业动作"更直接，单独成立。
# 否定前瞻排除指向他人的称谓，避免"我朋友是外卖骑手"被算成本人。
_OTHER_PERSON_REF = (
    r"(?:朋友|同事|邻居|老公|老婆|丈夫|妻子|对象|爸|妈|父|母|哥|姐|弟|妹|"
    r"儿子|女儿|孩子|亲戚|老板|客户|同学|室友|家人|家里人)"
)
_SELF_DECLARE_TEMPLATE = (
    r"(?:我是|本人是|本人|我)(?!" + _OTHER_PERSON_REF + r")"
    r"[^。！？；\n]{0,6}"
)


def build_judge_text(title, content, name):
    # type: (str, str, str) -> str
    """按需求拼接送模型的文本：标题 + 正文 + 账号名。

    Args:
        title: 帖文标题。
        content: 帖文正文。
        name: 账号名。

    Returns:
        拼接后的文本；正文按配置截断。
    """
    max_len = SCAN_CONFIG.get("max_content_len", 1000)
    content = (content or "")[:max_len]
    parts = []
    if name:
        parts.append("账号名：{}".format(name))
    if title:
        parts.append("标题：{}".format(title))
    if content:
        parts.append("正文：{}".format(content))
    return "\n".join(parts)


def _empty_result(reason=""):
    # type: (str) -> dict
    return {"identity": "", "identity2": "", "evidence": "", "log": reason}


# 证据接地阈值：证据句与原文的最长公共子串需 >= 该长度，否则视为编造。
_GROUNDING_MIN_LCS = 4


def _norm_text(s):
    # type: (str) -> str
    """归一化：只保留中英文数字和#，去空白标点，转小写。"""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff#]", "", s or "").lower()


def _lcs_len(a, b):
    # type: (str, str) -> int
    """最长公共子串长度（用于判断证据是否真实出现在原文）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _evidence_grounded(evidence, source_text):
    # type: (str, str) -> bool
    """校验模型给出的证据是否真实来自原文，防止编造证据。

    模型有时会输出原文里根本不存在的证据句（幻觉）。这里用最长公共子串
    做接地校验：证据与原文（账号名+标题+正文）需有足够长的连续重合。

    Args:
        evidence: 模型返回的证据句（可能带"标题：/正文："等前缀）。
        source_text: 送模型的原文（账号名+标题+正文）。

    Returns:
        True 证据可接地；False 疑似编造。
    """
    ev = _norm_text(evidence)
    src = _norm_text(source_text)
    if not ev:
        return False
    if ev in src:
        return True
    return _lcs_len(ev, src) >= _GROUNDING_MIN_LCS


def passes_new_employment_hard_gate(community, text, name):
    # type: (str, str, str) -> bool
    """四类新就业群体的确定性职业硬门槛（纯规则，无模型调用）。

    通过条件只有两种：

    1. 账号名本身带明确职业标签；
    2. 原文同时出现明确职业标签 + 第一人称从业动作。

    Args:
        community: 待校验的四类群体名（外卖员/网约车司机/货车司机/快递员）。
        text: 判定依据原文（账号名 + 标题 + 正文）。
        name: 账号名。

    Returns:
        True 表示通过硬门槛；community 不属于四类时返回 False。
    """
    category_terms = NEW_EMPLOYMENT_HARD_TERMS.get(community)
    if not category_terms:
        return False

    # 1) 账号名本身带明确职业标签
    name_norm = _norm_text(name)
    if any(_norm_text(term) in name_norm for term in category_terms):
        return True

    # 2) 第一人称直接自述职业（"本人外卖骑手"），不要求另有动作词
    for term in category_terms:
        if re.search(_SELF_DECLARE_TEMPLATE + re.escape(term), text or ""):
            return True

    # 3) 原文同时具备职业词 + 第一人称从业动作
    source_norm = _norm_text(text)
    text_has_label = any(_norm_text(term) in source_norm for term in category_terms)
    return bool(text_has_label and _FIRST_PERSON_ACTION.search(text or ""))


def judge_identity(title, content, name, verified_reason="", description=""):
    # type: (str, str, str, str, str) -> dict
    """判断账号是否为新就业群体之一。

    调用线上阿里云 qwen3.5-flash，使用合并后的四类判断提示词，
    并复用 community_filter 做规则兜底过滤。

    Args:
        title: 帖文标题。
        content: 帖文正文。
        name: 账号名。
        verified_reason: 账号认证原因（用于过滤商家/机构）。
        description: 账号简介（用于过滤）。

    Returns:
        dict: {"identity", "identity2", "log"}。
        identity2 为四类之一或""（其他/未命中/被过滤）。
    """
    text = build_judge_text(title, content, name)
    if not text:
        return _empty_result("空文本")

    # 与 prompt 规则8一致：超长文本直接判为非新就业群体，省一次模型调用。
    skip_over = SCAN_CONFIG.get("skip_text_over")
    if skip_over and len((content or "")) > skip_over:
        return _empty_result("正文超过{}字，判为非新就业群体".format(skip_over))

    result, _request_id, error = chat_json(JUDGE_PROMPT, text)
    if error or not isinstance(result, dict):
        return _empty_result(error or "模型返回结构异常")

    identity2 = (result.get("identity2") or "").strip()
    # 只保留四类目标群体
    if identity2 not in NEW_EMPLOYMENT_COMMUNITIES:
        return _empty_result(result.get("log", "非新就业群体"))

    # 证据接地校验：证据句必须真实出现在原文，否则视为模型编造，判"其他"
    evidence = (result.get("evidence") or "").strip()
    if not _evidence_grounded(evidence, text):
        return _empty_result(
            "证据未在原文出现，疑似编造[{}]:{}".format(evidence, result.get("log", ""))
        )

    # 职业硬门槛：模型判定之后，再用确定性规则做高精度兜底。
    if not passes_new_employment_hard_gate(identity2, text, name):
        return _empty_result(
            "职业硬门槛未通过:{}；需要账号名明确标签，或原文同时具备职业词和第一人称从业动作".format(identity2)
        )

    # community_filter 兜底：商家/机构认证、影视小说等直接清空
    filtered = _community_filter.apply(
        identity2, name or "", description or "", verified_reason or ""
    )
    if not filtered:
        return _empty_result("被community_filter过滤:{}".format(result.get("log", "")))

    return {
        "identity": "平台配送与运输从业者",
        "identity2": identity2,
        "evidence": evidence,
        "log": result.get("log", ""),
    }


# 向后兼容：general_judge 等模块从这里 import _strip_json，统一指向 llm_client。
_strip_json = strip_json


if __name__ == "__main__":
    # 简单自测
    samples = [
        ("", "我是一名外卖骑手，今天跑了30单，雨天路滑太难了", "外卖小哥阿强"),
        ("", "今天点了个外卖，商家送得好慢", "吃货日记"),
        ("", "我跑滴滴三年了，分享一下网约车司机的接单技巧", "老司机说车"),
        ("南宁比亚迪4S店突然关门", "近日南宁消费者曲先生报料，比亚迪4S店突然关门停业……", "汽车日历"),
    ]
    for t, c, n in samples:
        r = judge_identity(t, c, n)
        print(n, "=>", r)

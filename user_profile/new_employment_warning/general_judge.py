# -*- coding: utf-8 -*-
"""人工预警数据的通用高置信身份判断。

与 judge.py 的三新身份判断共用一套证据接地校验，覆盖 20 个标准身份。
模型统一走线上阿里云百炼 qwen3.5-flash（``new_employment_warning.llm_client``）。
"""
import re

from new_employment_warning.judge import _evidence_grounded
from new_employment_warning.llm_client import chat_json


# 18 个业务组，对应 20 个标准标签；农牧、公职在业务展示时合并，在数据中保留细分。
IDENTITY_GROUPS = {
    "家长": ["家长"],
    "医护人员": ["医护人员"],
    "教师": ["教师"],
    "学生": ["学生"],
    "老人": ["老人"],
    "农牧从业者": ["农民", "牧民"],
    "工人": ["工人"],
    "律师": ["律师"],
    "公职人员": ["公务员", "事业单位工作人员"],
    "警察": ["警察"],
    "退役军人": ["退役军人"],
    "外卖员": ["外卖员"],
    "快递员": ["快递员"],
    "网约车司机": ["网约车司机"],
    "货车司机": ["货车司机"],
    "家政服务人员": ["家政服务人员"],
    "餐饮从业者": ["餐饮从业者"],
    "维修人员": ["维修人员"],
}
IDENTITY_ALIASES = {
    "家长": ["宝妈", "宝爸", "全职妈妈", "全职宝妈", "孩子妈妈", "孩子爸爸", "学生家长", "家长"],
    "医护人员": ["医生", "医师", "护士", "护师", "药师", "麻醉师", "规培医生", "医务工作者"],
    "教师": ["教师", "老师", "班主任", "辅导员", "教授", "讲师", "幼师", "校长"],
    "学生": ["学生", "大学生", "研究生", "博士生", "高中生", "初中生", "小学生", "高三", "大一", "大二", "大三", "大四"],
    "老人": ["退休人员", "退休职工", "退休教师", "退休医生", "老年人", "老人", "银发族"],
    "农民": ["农民", "农户", "种植户", "养殖户", "果农", "菜农", "粮农", "新农人", "务农"],
    "牧民": ["牧民", "牧户", "放牧人", "牧场主"],
    "工人": ["工人", "工友", "产业工人", "建筑工", "电焊工", "瓦工", "木工", "矿工", "流水线工人"],
    "律师": ["律师", "实习律师", "律师助理", "法律顾问", "律所从业者"],
    "公务员": ["公务员", "公职人员", "机关干部", "政府工作人员"],
    "事业单位工作人员": ["事业编", "事业单位工作人员", "事业单位职工", "编制内人员"],
    "警察": ["警察", "民警", "辅警", "交警", "刑警", "公安干警"],
    "退役军人": ["退役军人", "退伍军人", "退役士兵", "转业军人", "老兵"],
    "外卖员": ["外卖员", "外卖骑手", "外卖小哥", "跑外卖", "送外卖", "美团骑手", "饿了么骑手"],
    "快递员": ["快递员", "快递小哥", "派件员", "收派员", "送快递", "快递驿站工作人员"],
    "网约车司机": ["网约车司机", "滴滴司机", "跑滴滴", "出租车司机", "的士司机", "滴滴车主"],
    "货车司机": ["货车司机", "卡车司机", "货运司机", "半挂司机", "大车司机", "跑货运", "卡友"],
    "家政服务人员": ["家政服务人员", "家政阿姨", "家政员", "保姆", "月嫂", "育婴师", "保洁员"],
    "餐饮从业者": ["餐饮从业者", "厨师", "厨师长", "面点师", "餐饮服务员", "后厨", "餐馆店主"],
    "维修人员": ["维修人员", "维修工", "维修师傅", "汽车维修技师", "修车师傅", "家电维修", "水电工"],
}

ALLOWED_IDENTITIES = set()
for _group_labels in IDENTITY_GROUPS.values():
    ALLOWED_IDENTITIES.update(_group_labels)


GENERAL_JUDGE_PROMPT = """你是账号身份核验员。根据账号名、认证、简介、标题和正文，判断发帖人本人是否具有下列标准身份之一：
家长、医护人员、教师、学生、老人、农民、牧民、工人、律师、公务员、事业单位工作人员、警察、退役军人、外卖员、快递员、网约车司机、货车司机、家政服务人员、餐饮从业者、维修人员。

严格规则：
1. 只判断发帖账号本人，不得把新闻人物、患者、顾客、家人、朋友或被采访者的身份算给账号。
2. 命中必须有直接证据，直接证据只有两类：
   A. 账号名/个人认证/个人简介明确标注身份，如账号名"二胎宝妈小李"、简介"三甲医院儿科医师"；
   B. 本人用第一人称明确自述身份或职业，如"我是外卖骑手""我是两个孩子的宝妈""我教高中数学"。
3. 新闻、政务通报、机构账号、医院/学校/律所/公司官方账号、招聘、广告、科普、影视剧情，一律不能据正文中的职业词判断账号身份。
4. 场景、工具、兴趣、泛称不能【单独】证明身份；例如只说开车不算司机，只说做饭不算厨师，只晒娃不算家长。
5. 可以输出多个身份，但每个身份必须分别提供能够从输入原文直接找到的证据。宁缺毋滥。
6. standard_identity 只能取上述标准身份；无直接证据时 identities 返回空数组。

判定顺序（重要）：先按规则2找直接证据，命中就必须输出该身份；规则4只用来排除
"只有场景线索、没有任何自述或资料标注"的情况，不能用来否决已经命中规则2的自述。

泛称与易混淆表述（必须按此归类，不得自行引申）：
- "打工人""上班族""社会人""老百姓""普通人""业主""消费者"都是泛称，
  不能推出任何标准身份，identities 返回空。"搬砖"多为自嘲，不能算工人。
- "农民工"要看实际从事的工作：从事建筑、工地、工厂、装修、外墙、搬运等
  → 判"工人"；确实从事种植、养殖等农业生产 → 判"农民"。不要一律判农民。
- 抱怨或质问里提到某个群体（如"难道老年人就活该被坑吗""为什么不管我们学生"），
  只是在指代该群体，**不等于**发帖人本人属于该群体；除非另有本人自述，identities 返回空。
- "老师"若指升学中介、招生咨询、才艺陪练等非教学岗，不判教师。

示例（必须命中）：
- 账号名"二胎宝妈小李"，正文"我是两个孩子的宝妈，记录带娃生活"
  → {"identities":[{"raw_identity":"二胎宝妈","standard_identity":"家长","evidence":"我是两个孩子的宝妈","reason":"账号名标注宝妈且本人第一人称自述"}]}
- 正文"我跑滴滴三年了" → 网约车司机
- 简介"某三甲医院护士" → 医护人员

示例（必须为空）：
- 正文"今天带孩子去公园玩" → 只有场景，无自述，identities 为空
- 正文"XX医院医生提醒市民注意防暑" → 机构口吻转述，identities 为空

只返回一个JSON对象，不要代码块和其他文字：
{"identities":[{"raw_identity":"原文细分身份","standard_identity":"标准身份","evidence":"原文证据摘录","reason":"简短理由"}]}
"""

_ORGANIZATION_ENDINGS = re.compile(
    r"(?:"
    # 医疗、教育
    r"医院|卫生院|疾控中心|学校|学院|大学|中学|小学|幼儿园|"
    # 企业、社会组织
    r"事务所|公司|总公司|分公司|集团|银行|支行|分行|协会|学会|基金会|商会|"
    # 党政机关：局/厅/委/办 这类单字后缀只在明确搭配下匹配，避免误伤个人账号名
    r"政府|委员会|管委会|管理局|教育局|公安局|民政局|人社局|税务局|监管局|"
    r"应急局|文旅局|卫健委|办事处|街道办|村委会|居委会|管理处|"
    # 司法、执法
    r"法院|检察院|派出所|分局|支队|大队|中队|"
    # 媒体、事业单位
    r"电视台|广播台|报社|日报|晚报|通讯社|融媒体中心|研究院|设计院|"
    r"工作站|服务中心|官方"
    r")$"
)
_OFFICIAL_NAME_ENDINGS = re.compile(
    r"(?:公安局|公安交管|交警支队|交警大队|警方|检察院|法院|消防救援(?:支队|大队)?|政法|政务|发布|网警|警务|税务局|海关|融媒)$"
)
_STRONG_ORGANIZATION_PROFILE = re.compile(
    r"政府机构|政府官方|政务账号|官方账号|机构认证|企业认证|组织认证|社会组织|事业单位法人|媒体官方|公安机关|检察机关|审判机关"
)
# 已用源索引样本校准：今日头条 verified=2、verified_type=10 为政务/机构官号。
_OFFICIAL_VERIFICATION_TYPES = {
    "今日头条": {("2", "10")},
}
_SELF_PREFIX = re.compile(r"(?:我是|本人是|作为|我是一名|我的职业是|我从事|我干|我做|我当|我现在是)")
# 账号资料无身份标签时，仅接受较短原帖中的本人自述；超长采访、新闻和故事稿误归风险高。
MAX_DIRECT_BODY_LEN = 1500


def _text(value):
    # type: (object) -> str
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def build_general_text(title, content, name, verified_reason="", description=""):
    # type: (str, str, str, str, str) -> str
    """构造模型输入，正文限长以控制 token。"""
    fields = [
        ("账号名", name),
        ("认证", verified_reason),
        ("简介", description),
        ("标题", title),
        ("正文", (content or "")[:1000]),
    ]
    return "\n".join("{}：{}".format(label, _text(value)) for label, value in fields if value)


def _is_organization_account(name, verified_reason="", description="",
                             verified="", verified_type="", platform=""):
    # type: (str, str, str, object, object, str) -> bool
    """识别机构/官号；认证状态本身不能作为机构依据。"""
    account_name = _text(name).strip()
    profile = " ".join((_text(verified_reason), _text(description))).strip()
    verification_pair = (_text(verified).strip(), _text(verified_type).strip())
    if verification_pair in _OFFICIAL_VERIFICATION_TYPES.get(_text(platform).strip(), set()):
        return True
    if _STRONG_ORGANIZATION_PROFILE.search(profile):
        return True
    if _ORGANIZATION_ENDINGS.search(account_name) or "官方账号" in account_name:
        return True
    is_verified = verification_pair[0].lower() not in ("", "0", "-1", "false", "none", "null")
    return bool(is_verified and _OFFICIAL_NAME_ENDINGS.search(account_name))


def is_organization_account(doc):
    # type: (dict) -> bool
    """按扁平化账号记录判断是否为机构/官方账号。"""
    return _is_organization_account(
        doc.get("name", ""), doc.get("verified_reason", ""),
        doc.get("description", ""), doc.get("verified", ""),
        doc.get("verified_type", ""), doc.get("platform", ""),
    )


def _contains_alias(text, identity):
    # type: (str, str) -> bool
    value = _text(text).lower()
    return any(alias.lower() in value for alias in IDENTITY_ALIASES[identity])


def _profile_has_identity(profile, identity):
    # type: (str, str) -> bool
    """账号资料中的显式身份；“老师”作为敬称时要求教育语境。"""
    value = _text(profile)
    if identity != "教师":
        return _contains_alias(value, identity)
    strong_aliases = [alias for alias in IDENTITY_ALIASES[identity] if alias != "老师"]
    if any(alias in value for alias in strong_aliases):
        return True
    if "老师" not in value:
        return False
    return bool(re.search(
        r"学校|教育|教学|教书|家长圈|升学|课程|课堂|培训|特训|书法|编程|语文|数学|英语|艺考|幼儿园",
        value,
    ))


# “我”后面紧跟这些词时说的是别人，不能算本人自述（如“我朋友是医生”“我儿子的老师”）。
_OTHER_PERSON_REFERENT = (
    r"(?:朋友|同事|邻居|老公|老婆|丈夫|妻子|对象|男友|女友|爸|妈|父|母|哥|姐|弟|妹|"
    r"儿子|女儿|孩子|娃|舅|姨|叔|婶|婆|公|表|堂|亲戚|老板|客户|师傅|同学|室友|"
    r"家人|家里人|一个|认识的)"
)
# 反问、质问语境里的身份词是在指代某个群体，不是本人自述。
# 例："我说：难道老年人去你这儿就活该被坑吗"——发帖人未必是老年人。
_RHETORICAL_MARKER = r"(?:难道|为什么|凭什么|岂|何必|凭啥|干嘛|算什么|说：|问道|反问)"

# 比喻、贬称结构里的身份词也不是本人职业，例：
# "我拿你当哥哥，你拿我当送外卖的"（被人看轻）、"你把我当保姆使唤"。
# 这类结构自带"我当X"字样，会命中更靠前的自述分支，所以在匹配前先整段剔除。
_DEROGATORY_CONTEXT = re.compile(
    r"(?:拿我当|把我当|当我是|当我成|当成|看成|以为我)[^。！？；，,\n]{0,12}"
)
# 本人自述：第一人称与身份词在同一短句内，中间既不指向他人、也不是反问语境。
_SELF_NEAR_ALIAS = (
    r"(?:我|本人|咱)(?!" + _OTHER_PERSON_REFERENT + r")"
    r"(?:(?!" + _RHETORICAL_MARKER + r")[^。！？；\n]){0,12}"
)


def _body_has_self_statement(body, identity):
    # type: (str, str) -> bool
    """要求职业词与第一人称自述在同一短窗口出现。"""
    # 先剔除"你拿我当送外卖的"这类比喻/贬称片段，避免其中的"我当X"被当成自述。
    value = _DEROGATORY_CONTEXT.sub(" ", _text(body))
    aliases = IDENTITY_ALIASES[identity]
    for alias in aliases:
        escaped = re.escape(alias)
        if re.search(
                r"(?:我是|本人是|作为(?:一名)?|我是一名|我的职业是|我从事|我干|我做|我当|我现在是)"
                r".{0,8}" + escaped,
                value):
            return True
        if re.search(escaped + r".{0,16}(?:是我的职业|是我现在的工作|这行我干|我干了|我做了)", value):
            return True
        # 覆盖动词型别名和“我在工地干了十几年电焊工”这类表达：
        # 第一人称与身份词同句且中间不指向他人，即视为本人自述。
        if re.search(_SELF_NEAR_ALIAS + escaped, value):
            return True

    # 家庭、学生、退休身份的常见第一人称直接表达。
    special_patterns = {
        "家长": r"(?:我是|作为).{0,10}(?:宝妈|宝爸|家长)|(?:我家孩子|我儿子|我女儿).{0,20}(?:上学|读书)",
        "学生": r"(?:我是|本人是).{0,10}(?:学生|大学生|研究生|博士生|高中生|初中生|小学生)|我(?:上|读)(?:大学|高中|初中|小学|研)",
        "老人": r"我.{0,8}(?:退休了|已经退休)|本人.{0,8}(?:退休|年满六十)",
        "教师": r"(?:我是|本人是).{0,30}(?:学校|培训机构).{0,12}(?:老师|教师)|我.{0,8}(?:教书|任教|带班)",
    }
    pattern = special_patterns.get(identity)
    return bool(pattern and re.search(pattern, value))


def identity_has_direct_signal(identity, title, content, name,
                               verified_reason="", description="", verified="",
                               verified_type="", platform=""):
    # type: (str, str, str, str, str, str, object, object, str) -> bool
    """确定性高精度门槛：个人资料显式标签，或正文第一人称自述。"""
    if identity not in ALLOWED_IDENTITIES:
        return False
    if _is_organization_account(
            name, verified_reason, description, verified, verified_type, platform):
        return False
    profile = " ".join((_text(name), _text(verified_reason), _text(description)))
    if _profile_has_identity(profile, identity):
        return True
    body = "{} {}".format(_text(title), _text(content))
    if len(body) > MAX_DIRECT_BODY_LEN:
        return False
    return _body_has_self_statement(body, identity)


def identity_evidence_has_direct_signal(identity, evidence, name,
                                        verified_reason="", description="",
                                        verified="", verified_type="", platform=""):
    # type: (str, str, str, str, str, object, object, str) -> bool
    """确保当前结果自己的证据足以证明身份，防止借正文其他片段过门槛。"""
    if identity not in ALLOWED_IDENTITIES:
        return False
    if _is_organization_account(
            name, verified_reason, description, verified, verified_type, platform):
        return False
    profile = " ".join((_text(name), _text(verified_reason), _text(description)))
    if _profile_has_identity(profile, identity):
        return True
    value = _text(evidence)
    if identity == "学生" and re.search(r"曾经|以前|小时候|当年", value):
        return False
    return len(value) <= MAX_DIRECT_BODY_LEN and _body_has_self_statement(value, identity)


def candidate_has_direct_signal(doc, identities=None):
    # type: (dict, object) -> bool
    """采集脚本调用的模型前预筛，官号先排除以避免误判和token消耗。"""
    if is_organization_account(doc):
        return False
    labels = identities or ALLOWED_IDENTITIES
    return any(identity_has_direct_signal(
        identity,
        doc.get("title", ""), doc.get("content", ""), doc.get("name", ""),
        doc.get("verified_reason", ""), doc.get("description", ""),
        doc.get("verified", ""), doc.get("verified_type", ""),
        doc.get("platform", ""),
    ) for identity in labels)


def _empty_result(reason):
    # type: (str) -> dict
    return {"identities": [], "request_id": "", "log": reason}


def judge_general_identity(title, content, name, verified_reason="", description="",
                           verified="", verified_type="", platform=""):
    # type: (str, str, str, str, str, object, object, str) -> dict
    """调用豆包并执行官号过滤、白名单、证据接地、直接信号校验。"""
    source_text = build_general_text(title, content, name, verified_reason, description)
    if not source_text:
        return _empty_result("空文本")
    if _is_organization_account(
            name, verified_reason, description, verified, verified_type, platform):
        return _empty_result("明确机构或官方账号")
    if not candidate_has_direct_signal({
            "title": title, "content": content, "name": name,
            "verified_reason": verified_reason, "description": description,
            "verified": verified, "verified_type": verified_type,
            "platform": platform,
    }):
        return _empty_result("确定性预筛无本人身份直接信号")

    parsed, request_id, error = chat_json(GENERAL_JUDGE_PROMPT, source_text)
    if error:
        return _empty_result(error)

    items = parsed.get("identities", []) if isinstance(parsed, dict) else []
    accepted = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        identity = _text(item.get("standard_identity")).strip()
        evidence = _text(item.get("evidence")).strip()
        if identity not in ALLOWED_IDENTITIES or identity in seen:
            continue
        if not _evidence_grounded(evidence, source_text):
            continue
        if not identity_evidence_has_direct_signal(
                identity, evidence, name, verified_reason, description,
                verified, verified_type, platform):
            continue
        seen.add(identity)
        accepted.append({
            "raw_identity": _text(item.get("raw_identity")).strip() or identity,
            "standard_identity": identity,
            "evidence": evidence,
            "reason": _text(item.get("reason")).strip(),
            "confidence": "高",
        })
    return {
        "identities": accepted,
        "request_id": request_id,
        "log": "通过{}个高置信身份".format(len(accepted)) if accepted else "模型结果未通过校验",
    }


if __name__ == "__main__":
    samples = [
        ("", "我是儿科医生，今天值夜班。", "张医生", "个人认证", "三甲医院儿科医师"),
        ("医院发布通知", "我院医生提醒市民及时就诊。", "某市人民医院", "机构认证", ""),
        ("", "我是两个孩子的宝妈，记录带娃生活。", "二胎宝妈小李", "", ""),
    ]
    for sample in samples:
        print(sample[2], judge_general_identity(*sample))

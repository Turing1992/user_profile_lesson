# -*- coding: utf-8 -*-
"""预警账号身份识别每日批量任务的单元测试。

覆盖不依赖网络的纯规则与数据构造逻辑：

- ``media_index_mapper``：siteName 归一化与 media_* 索引解析
  （断言值取自线上 ``media_*`` 索引 ``site_name.keyword`` 的真实聚合结果）
- ``general_judge``：本人身份自述识别的正反例，尤其是三类干扰
  （指向他人、反问质问、比喻贬称）
- ``judge``：三新身份的确定性职业硬门槛
- ``media_writer``：身份分流、写入字段构造、新账号文档构造
- ``llm_client``：模型返回的容错 JSON 解析
- ``daily_identity_job``：预警 hit 展平与判断帖选取

需要访问 OpenSearch / 大模型的端到端验证不在此文件内，
用 ``python3 -m new_employment_warning.daily_identity_job --dry-run`` 单独跑。
"""

import pytest

from new_employment_warning.general_judge import (
    _body_has_self_statement,
    is_organization_account,
)
from new_employment_warning.judge import passes_new_employment_hard_gate
from new_employment_warning.llm_client import loads_tolerant, strip_json
from new_employment_warning.media_index_mapper import (
    build_doc_id,
    normalize_site_name,
    resolve_media_target,
)
from new_employment_warning.media_writer import (
    THREE_NEW_IDENTITY_LABEL,
    build_identity_fields,
    build_new_account_doc,
    split_identities,
)


# --- media_index_mapper 测试 ---

class TestResolveMediaTarget(object):
    """siteName 归一化与目标索引解析测试。

    期望值全部来自线上 media_* 的真实归属，预警侧的栏目后缀
    （如「今日头条-微头条」）和异名（如「知乎回答」）都必须能落到
    media_* 里真实存在的 site_name 上，否则 doc_id 拼不上会重复插入。
    """

    @pytest.mark.parametrize("raw,site_name,media_index", [
        # 直接命中
        ("抖音", "抖音", "media_douyin"),
        ("今日头条", "今日头条", "media_toutiao"),
        ("小红书", "小红书", "media_xhs"),
        ("微信视频号", "微信视频号", "media_weixin"),
        ("新浪微博视频", "新浪微博视频", "media_weibo"),
        ("有驾", "有驾", "media_baidu"),
        ("好看视频", "好看视频", "media_baidu"),
        ("搜狐新闻", "搜狐新闻", "media_other"),
        ("手机新浪网", "手机新浪网", "media_other"),
        ("微视", "微视", "media_other"),
        ("QQ浏览器", "QQ浏览器", "media_other"),
        # 栏目后缀需要截断
        ("今日头条-其他", "今日头条", "media_toutiao"),
        ("今日头条-微头条", "今日头条", "media_toutiao"),
        ("百度百家-文章", "百度百家", "media_baidu"),
        ("百度百家-动态", "百度百家", "media_baidu"),
        ("bilibili-", "bilibili", "media_bilibili"),
        ("腾讯网-", "腾讯网", "media_other"),
        ("UC-社会", "UC", "media_other"),
        ("网易号-社会", "网易号", "media_other"),
        ("网易号-社会/百态", "网易号", "media_other"),
        # 异名需要走别名表
        ("新浪新闻", "新浪微博", "media_weibo"),
        ("知乎回答", "知乎问答", "media_zhihu"),
        ("知乎想法", "知乎问答", "media_zhihu"),
    ])
    def test_mapped_sites(self, raw, site_name, media_index):
        # type: (str, str, str) -> None
        """可映射的 siteName 解析出正确的 site_name 与索引。"""
        assert resolve_media_target(raw) == (site_name, media_index)

    @pytest.mark.parametrize("raw", [
        "腾讯新闻",                    # media_* 里查不到对应账号
        "黑猫投诉",
        "消费保-投诉",
        "奔流新闻",
        "电视节目-荆门新闻综合频道",
        "麻辣-巴中论坛",
        "",
        None,
    ])
    def test_unmapped_sites_return_empty(self, raw):
        # type: (str) -> None
        """没有对应画像索引的站点必须返回空，交由调用方跳过。"""
        assert resolve_media_target(raw) == ("", "")

    def test_normalize_strips_whitespace(self):
        # type: () -> None
        """两侧空白不影响归一化。"""
        assert normalize_site_name("  抖音  ") == "抖音"

    def test_build_doc_id(self):
        # type: () -> None
        """doc_id 按 media_* 既有规则拼接。"""
        assert build_doc_id("抖音", "101780330080") == "抖音|101780330080"

    @pytest.mark.parametrize("site_name,uid", [
        ("", "123"),
        ("抖音", ""),
        ("", ""),
    ])
    def test_build_doc_id_requires_both_parts(self, site_name, uid):
        # type: (str, str) -> None
        """缺 site_name 或 uid 时不生成 doc_id。"""
        assert build_doc_id(site_name, uid) == ""


# --- general_judge 本人自述识别测试 ---

class TestBodyHasSelfStatement(object):
    """本人身份自述识别测试。

    这道校验既用于模型调用前的预筛，也用于模型返回后的证据校验，
    是防止把新闻人物、家属、被吐槽对象的身份算到账号头上的关键。
    """

    @pytest.mark.parametrize("text,identity", [
        ("我是一名外卖骑手，今天跑了30单", "外卖员"),
        ("我今天送外卖被罚款了", "外卖员"),
        ("我跑滴滴三年了，分享网约车接单技巧", "网约车司机"),
        ("我当了三年货车司机", "货车司机"),
        ("我在工地干了十几年电焊工，手上全是伤", "工人"),
        ("我是两个孩子的宝妈", "家长"),
        ("我是地地道道的老农民，玉米地全是水", "农民"),
        ("每年八一我们这些退役老兵只能眼睁睁盼着", "退役军人"),
        ("我把跑外卖当成主业已经两年", "外卖员"),
    ])
    def test_first_person_statement_recognized(self, text, identity):
        # type: (str, str) -> None
        """本人第一人称自述职业应被识别。"""
        assert _body_has_self_statement(text, identity) is True

    @pytest.mark.parametrize("text,identity", [
        ("我朋友是医生，他说要多喝水", "医护人员"),
        ("我儿子的老师布置了很多作业", "教师"),
        ("我老公是货车司机，常年不在家", "货车司机"),
        ("我认识的一个律师说这事能打赢", "律师"),
    ])
    def test_other_person_not_recognized(self, text, identity):
        # type: (str, str) -> None
        """身份属于他人时不能算到账号本人头上。"""
        assert _body_has_self_statement(text, identity) is False

    @pytest.mark.parametrize("text,identity", [
        ("我说：难道老年人去你这儿就活该被坑吗", "老人"),
        ("我就问为什么学生就该被这样对待", "学生"),
        ("我凭什么要给老师送礼", "教师"),
    ])
    def test_rhetorical_question_not_recognized(self, text, identity):
        # type: (str, str) -> None
        """反问句里提到某群体只是指代，不代表本人属于该群体。"""
        assert _body_has_self_statement(text, identity) is False

    @pytest.mark.parametrize("text,identity", [
        ("我拿你当哥哥你拿我当送外卖的", "外卖员"),
        ("你把我当保姆使唤", "家政服务人员"),
        ("别人以为我送外卖的其实我是老板", "外卖员"),
    ])
    def test_derogatory_metaphor_not_recognized(self, text, identity):
        # type: (str, str) -> None
        """被人看轻的比喻用法不是真实职业。"""
        assert _body_has_self_statement(text, identity) is False

    @pytest.mark.parametrize("text,identity", [
        ("今天点了个外卖，商家送得好慢", "外卖员"),
        ("今天带孩子去公园玩，天气真好", "家长"),
    ])
    def test_no_statement_not_recognized(self, text, identity):
        # type: (str, str) -> None
        """只有消费或生活场景、没有自述时不判定身份。"""
        assert _body_has_self_statement(text, identity) is False


class TestIsOrganizationAccount(object):
    """机构/官方账号识别测试。"""

    @pytest.mark.parametrize("account", [
        {"name": "某市人民医院", "verified_reason": "机构认证"},
        {"name": "XX区教育局", "verified_reason": ""},
        {"name": "某某律师事务所", "verified_reason": ""},
        {"name": "普通账号", "verified_reason": "政府机构官方账号"},
        # 已校准：今日头条 verified=2 + verified_type=10 为政务/机构官号
        {"name": "XX发布", "verified": 2, "verified_type": 10, "platform": "今日头条"},
    ])
    def test_organization_detected(self, account):
        # type: (dict) -> None
        """机构、官方、政务类账号应被识别并排除。"""
        assert is_organization_account(account) is True

    @pytest.mark.parametrize("account", [
        {"name": "张医生", "verified_reason": "个人认证", "description": "三甲医院儿科医师"},
        {"name": "二胎宝妈小李", "verified_reason": "", "description": ""},
        # 认证状态本身不能当作机构依据，避免误删认证个人
        {"name": "老王说事", "verified": 1, "verified_type": 0, "platform": "抖音"},
    ])
    def test_personal_account_not_detected(self, account):
        # type: (dict) -> None
        """个人账号不能被误判为机构。"""
        assert is_organization_account(account) is False


# --- judge 三新硬门槛测试 ---

class TestNewEmploymentHardGate(object):
    """三新身份的确定性职业硬门槛测试。

    三新身份误判代价最高（直接写进 community），所以在模型判定之后
    还要再过一遍纯规则校验。
    """

    @pytest.mark.parametrize("community,text,name", [
        # 账号名自带明确职业标签
        ("外卖员", "今天路上车真多", "外卖小哥阿强"),
        ("货车司机", "有没有人知道前面什么情况", "卡车司机-小郑"),
        # 原文同时具备职业词 + 第一人称从业动作
        ("外卖员", "我是一名外卖骑手，今天跑了30单", "随便一个名字"),
        ("网约车司机", "我跑滴滴三年了，网约车司机不容易", "老司机说车"),
    ])
    def test_pass(self, community, text, name):
        # type: (str, str, str) -> None
        """满足任一条件即通过硬门槛。"""
        assert passes_new_employment_hard_gate(community, text, name) is True

    @pytest.mark.parametrize("community,text,name", [
        # 只有情境线索，没有职业标签和从业动作
        ("货车司机", "国道堵车，堵了十一个小时", "路人甲"),
        ("外卖员", "今天点了个外卖，商家送得好慢", "吃货日记"),
        # 有职业词但没有第一人称从业动作
        ("外卖员", "外卖骑手这个职业很辛苦啊", "旁观者"),
        # 职业属于他人，不能算本人
        ("外卖员", "我朋友是外卖骑手，他说很累", "路人"),
        ("货车司机", "我老公是货车司机，常年不在家", "某某"),
    ])
    def test_reject(self, community, text, name):
        # type: (str, str, str) -> None
        """缺少直接证据时拦截。"""
        assert passes_new_employment_hard_gate(community, text, name) is False

    def test_profile_only_statement_passes(self):
        # type: () -> None
        """职业信息只写在简介里也要能通过。

        真实误拦案例：账号简介写「本人外卖骑手」，但调用方只传了
        账号名+正文，导致这个明确的从业者被硬门槛拦掉。
        """
        source_text = "ᝰꫛꫀꪝ•⚘曙光  本人外卖骑手，每天在路上"
        assert passes_new_employment_hard_gate(
            "外卖员", source_text, "ᝰꫛꫀꪝ•⚘曙光") is True

    @pytest.mark.parametrize("community", ["教师", "医护人员", "", "其他"])
    def test_non_three_new_identity_rejected(self, community):
        # type: (str) -> None
        """非三新身份不走这道门槛，一律返回 False。"""
        assert passes_new_employment_hard_gate(
            community, "我是一名教师", "某老师") is False


# --- media_writer 写入口径测试 ---

class TestSplitIdentities(object):
    """三新身份与其他身份的分流测试。"""

    def test_three_new_only(self):
        # type: () -> None
        """纯三新身份进 community 桶。"""
        assert split_identities(["外卖员"]) == (["外卖员"], [])

    def test_other_only(self):
        # type: () -> None
        """纯其他身份进 identity 桶。"""
        assert split_identities(["教师"]) == ([], ["教师"])

    def test_mixed(self):
        # type: () -> None
        """混合身份分别进两个桶。"""
        three_new, others = split_identities(["货车司机", "家长"])
        assert three_new == ["货车司机"]
        assert others == ["家长"]

    def test_all_four_three_new(self):
        # type: () -> None
        """四类三新身份全部归入 community 桶。"""
        four = ["外卖员", "快递员", "网约车司机", "货车司机"]
        three_new, others = split_identities(four)
        assert three_new == four
        assert others == []

    def test_dedup_and_skip_blank(self):
        # type: () -> None
        """去重并跳过空值。"""
        three_new, others = split_identities(
            ["外卖员", "外卖员", "教师", "教师", "", None])
        assert three_new == ["外卖员"]
        assert others == ["教师"]

    def test_empty(self):
        # type: () -> None
        """空输入返回两个空列表。"""
        assert split_identities([]) == ([], [])


class TestBuildIdentityFields(object):
    """写入字段构造测试。"""

    def setup_method(self):
        # type: () -> None
        """构造精简映射表，避免依赖真实 Excel。"""
        self.identity_map = {
            "外卖员": "外卖骑手",
            "货车司机": "司机",
            "网约车司机": "司机",
            "教师": "教师",
            "家长": "家长",
        }  # type: dict

    def test_three_new_writes_community(self):
        # type: () -> None
        """三新身份写 community，并附带 three_new_identity 标记。"""
        fields = build_identity_fields(["外卖员"], self.identity_map)
        assert fields["community"] == "外卖员"
        assert fields["three_new_identity"] == THREE_NEW_IDENTITY_LABEL
        assert "identity" not in fields

    def test_other_writes_identity(self):
        # type: () -> None
        """其他身份写 identity，不写 community 和 three_new_identity。"""
        fields = build_identity_fields(["教师"], self.identity_map)
        assert fields["identity"] == "教师"
        assert "community" not in fields
        assert "three_new_identity" not in fields

    def test_mixed_writes_both(self):
        # type: () -> None
        """混合身份同时写两个字段。"""
        fields = build_identity_fields(["货车司机", "家长"], self.identity_map)
        assert fields["community"] == "货车司机"
        assert fields["identity"] == "家长"
        assert fields["three_new_identity"] == THREE_NEW_IDENTITY_LABEL

    def test_identity_standerd_mapped(self):
        # type: () -> None
        """identity_standerd 覆盖全部命中身份并做标准化映射。"""
        fields = build_identity_fields(["外卖员"], self.identity_map)
        assert fields["identity_standerd"] == "外卖骑手"

    def test_identity_standerd_multi(self):
        # type: () -> None
        """多身份的 identity_standerd 以逗号分隔且去重。"""
        fields = build_identity_fields(
            ["货车司机", "网约车司机", "教师"], self.identity_map)
        # 两类司机都标准化为"司机"，去重后只剩一个
        assert set(fields["identity_standerd"].split(",")) == {"司机", "教师"}

    def test_no_identity_map_skips_standerd(self):
        # type: () -> None
        """不传映射表时不写 identity_standerd。"""
        fields = build_identity_fields(["教师"], None)
        assert fields["identity"] == "教师"
        assert "identity_standerd" not in fields

    def test_empty_identities_returns_empty(self):
        # type: () -> None
        """没有有效身份时返回空 dict，调用方据此跳过写入。"""
        assert build_identity_fields([], self.identity_map) == {}
        assert build_identity_fields(["", None], self.identity_map) == {}


class TestBuildNewAccountDoc(object):
    """新账号完整文档构造测试（需对齐 media_* mapping）。"""

    def setup_method(self):
        # type: () -> None
        self.identity_fields = {"identity": "教师", "identity_standerd": "教师"}

    def test_required_fields(self):
        # type: () -> None
        """必备字段齐全，id 与 doc_id 规则一致。"""
        doc = build_new_account_doc(
            {"site_name": "抖音", "uid": "u1", "name": "某老师"},
            self.identity_fields,
        )
        assert doc["id"] == "抖音|u1"
        assert doc["uid"] == "u1"
        assert doc["site_name"] == "抖音"
        assert doc["name"] == "某老师"
        assert "create_time" in doc and "update_time" in doc
        assert doc["identity"] == "教师"

    def test_numeric_fields_converted(self):
        # type: () -> None
        """age 转 integer、粉丝等计数字段转 long，兼容"30岁"这类脏值。"""
        doc = build_new_account_doc(
            {"site_name": "抖音", "uid": "u1", "age": "30岁",
             "followers_count": "1200", "friends_count": 45.0},
            self.identity_fields,
        )
        assert doc["age"] == 30
        assert doc["followers_count"] == 1200
        assert doc["friends_count"] == 45

    def test_empty_values_skipped(self):
        # type: () -> None
        """空值不写入，避免给 integer 字段塞空串。"""
        doc = build_new_account_doc(
            {"site_name": "抖音", "uid": "u1", "age": "", "description": "",
             "gender": None, "ip_region": []},
            self.identity_fields,
        )
        for field in ("age", "description", "gender", "ip_region"):
            assert field not in doc

    def test_list_field_joined(self):
        # type: () -> None
        """列表型地域字段拼接为字符串。"""
        doc = build_new_account_doc(
            {"site_name": "抖音", "uid": "u1", "ip_region": ["江苏省"],
             "freq_history_location": ["江苏省", "上海市"]},
            self.identity_fields,
        )
        assert doc["ip_region"] == "江苏省"
        assert doc["freq_history_location"] == "江苏省,上海市"

    def test_verified_minus_one_skipped(self):
        # type: () -> None
        """预警侧用 -1 表示无认证类型，与 media_* 既有空串不一致，不写入。"""
        doc = build_new_account_doc(
            {"site_name": "抖音", "uid": "u1", "verified": 0, "verified_type": -1},
            self.identity_fields,
        )
        assert doc["verified"] == "0"
        assert "verified_type" not in doc

    def test_placeholder_bracket_cleaned(self):
        # type: () -> None
        """清洗 "[ ]" 空占位符。"""
        doc = build_new_account_doc(
            {"site_name": "抖音", "uid": "u1", "description": "[ ]"},
            self.identity_fields,
        )
        assert "description" not in doc

    @pytest.mark.parametrize("account", [
        {"site_name": "", "uid": "u1"},
        {"site_name": "抖音", "uid": ""},
    ])
    def test_missing_key_parts_returns_empty(self, account):
        # type: (dict) -> None
        """缺 site_name 或 uid 时返回空 dict，不生成脏文档。"""
        assert build_new_account_doc(account, self.identity_fields) == {}


# --- llm_client 容错解析测试 ---

class TestLoadsTolerant(object):
    """模型返回内容的容错 JSON 解析测试。

    qwen3.5-flash 偶尔会在证据字段里带未转义引号、加尾随逗号，
    或在 JSON 前后附带说明文字，标准库 json.loads 会直接失败。
    """

    def test_plain_json(self):
        # type: () -> None
        """标准 JSON 正常解析。"""
        assert loads_tolerant('{"identities":[]}') == {"identities": []}

    def test_code_fence(self):
        # type: () -> None
        """去掉 ```json 代码块包裹。"""
        assert loads_tolerant('```json\n{"a":1}\n```') == {"a": 1}

    def test_surrounding_text(self):
        # type: () -> None
        """截取被说明文字包围的 JSON 片段。"""
        text = '好的，判断结果如下：{"identities":[{"standard_identity":"教师"}]} 以上'
        assert loads_tolerant(text)["identities"][0]["standard_identity"] == "教师"

    def test_trailing_comma(self):
        # type: () -> None
        """容忍尾随逗号。"""
        assert loads_tolerant('{"a":1,}') == {"a": 1}

    def test_array_root(self):
        # type: () -> None
        """根节点为数组时也能解析。"""
        assert loads_tolerant('[{"a":1}]') == [{"a": 1}]

    def test_unparseable_raises(self):
        # type: () -> None
        """完全无法解析时抛 ValueError，由调用方转成错误原因。"""
        with pytest.raises(ValueError):
            loads_tolerant("这里根本没有 JSON")

    def test_strip_json_keeps_plain_text(self):
        # type: () -> None
        """没有代码块标记时原样返回并去除两侧空白。"""
        assert strip_json('  {"a":1}  ') == '{"a":1}'


# --- daily_identity_job 数据处理测试 ---

class TestFlattenPost(object):
    """预警 ES hit 展平测试。"""

    def test_flatten_full_hit(self):
        # type: () -> None
        """常规命中项各字段正确展平，并解析出目标索引。"""
        from new_employment_warning.daily_identity_job import flatten_post

        post = flatten_post({"_source": {
            "siteName": "今日头条-微头条",
            "title": "标题",
            "content": "正文内容",
            "url": "https://example.com/a",
            "publishTime": "2026-08-02 10:00:00",
            "author_persona": {
                "id": "12345", "name": "某账号", "verified": 0,
                "verified_type": -1, "gender": "男",
                "ip_region": ["江苏省"], "his_location": ["江苏省", "上海市"],
            },
        }})
        assert post["raw_site_name"] == "今日头条-微头条"
        assert post["site_name"] == "今日头条"
        assert post["media_index"] == "media_toutiao"
        assert post["uid"] == "12345"
        assert post["name"] == "某账号"
        assert post["ip_region"] == "江苏省"
        assert post["freq_history_location"] == "江苏省,上海市"
        # 预警索引没有这两个字段，展平后必须留空以便后续从 media_* 回补
        assert post["description"] == ""
        assert post["verified_reason"] == ""

    def test_flatten_unmapped_site(self):
        # type: () -> None
        """无对应画像索引的站点，media_index 为空。"""
        from new_employment_warning.daily_identity_job import flatten_post

        post = flatten_post({"_source": {
            "siteName": "电视节目-荆门新闻综合频道",
            "author_persona": {"id": "1"},
        }})
        assert post["media_index"] == ""

    def test_flatten_missing_persona(self):
        # type: () -> None
        """缺失 author_persona 时不报错，uid 为空。"""
        from new_employment_warning.daily_identity_job import flatten_post

        post = flatten_post({"_source": {"siteName": "抖音"}})
        assert post["uid"] == ""


class TestSelectJudgePost(object):
    """判断帖选取测试。

    刻意逐帖判断而非合并多帖：合并后文本很容易超过 1500 字的直接信号
    长度上限，导致有明确自述的账号被整体判为无信号。
    """

    def test_picks_post_with_signal(self):
        # type: () -> None
        """从多条帖里挑出有本人自述的那条。"""
        from new_employment_warning.daily_identity_job import select_judge_post

        account = {
            "name": "普通账号", "description": "", "verified_reason": "",
            "verified": 0, "verified_type": -1, "platform": "抖音",
            "posts": [
                {"title": "", "content": "今天天气不错", "url": "u1"},
                {"title": "", "content": "我是一名外卖骑手，今天跑了30单", "url": "u2"},
            ],
        }
        assert select_judge_post(account)["url"] == "u2"

    def test_returns_empty_when_no_signal(self):
        # type: () -> None
        """所有帖都没有直接信号时返回空 dict，账号不送模型。"""
        from new_employment_warning.daily_identity_job import select_judge_post

        account = {
            "name": "普通账号", "description": "", "verified_reason": "",
            "verified": 0, "verified_type": -1, "platform": "抖音",
            "posts": [{"title": "", "content": "今天天气不错", "url": "u1"}],
        }
        assert select_judge_post(account) == {}

    def test_profile_signal_accepts_first_post(self):
        # type: () -> None
        """账号资料本身带身份标签时，第一条帖即可作为判断输入。"""
        from new_employment_warning.daily_identity_job import select_judge_post

        account = {
            "name": "二胎宝妈小李", "description": "", "verified_reason": "",
            "verified": 0, "verified_type": -1, "platform": "抖音",
            "posts": [{"title": "", "content": "记录日常", "url": "u1"}],
        }
        assert select_judge_post(account)["url"] == "u1"


class TestIdentityGates(object):
    """身份专属硬门槛测试。

    模型 + 通用自述校验只能保证"有人自述了某身份"，挡不住"沾边"账号：
    只写「劳动维权找我」的代理人会被判律师、做升学咨询的中介会被判教师。
    这道门槛要求每个身份必须命中职业锚点词（资格 / 场所 / 工作动作），
    并对同领域的其他角色（中介、经营者、培训招生）显式否决。

    用例全部取自线上真实账号。
    """

    @pytest.mark.parametrize("identity,kwargs,expect_keyword", [
        # 维权代理不是律师：缺执业资格锚点，且命中否决词
        ("律师", dict(
            name="州哥劳动维权",
            description="7年经验，劳动维权找我：不出面、免奔波、提胜率、多赔偿",
            evidence="7年经验，劳动维权找我"), "否决词"),
        # 升学中介不是教师
        ("教师", dict(
            name="飞老师",
            description="小升初 初升高 单招 高报 招生政策实时解析 一对一升学规划陪跑",
            evidence="一对一升学规划陪跑"), "否决词"),
        # 技能培训讲师不算学历教育教师
        ("教师", dict(
            name="艾简妍·即刻美甲何老师",
            description="从事美业行业21年，培训教学17年 赣州市知名美甲讲师",
            evidence="培训教学17年 赣州市知名美甲讲师"), "否决词"),
        # 账号名是经营主体，不判基层工人
        ("工人", dict(
            name="周来源-海泉建筑工程", content="农民工苦",
            evidence="账号名：周来源 - 海泉建筑工程，正文：农民工苦"), "经营主体"),
        # 只说"家长"两个字，没有养育关系表述
        ("家长", dict(
            name="狮子先生",
            content="我们这边踢球家长，以后再也不支持和信任你了",
            evidence="我们这边踢球家长"), "锚点"),
        # 账号名带身份泛称但无任何从业场景
        ("农民", dict(
            name="东北农民", content="今天天气不错",
            evidence="账号名：东北农民"), "锚点"),
        ("律师", dict(
            name="北京玉华池律师", content="维权咨询",
            evidence="账号名：北京玉华池律师"), "锚点"),
        # 「打工」是泛称，需要配具体劳动场景
        ("工人", dict(
            name="累了谁疼",
            content="看看我们打工人挣点钱容易吗，两个月电费一千三百多",
            evidence="看看我们打工人挣点钱容易吗"), "泛称"),
        # 账号名是商家/机构/组织主体，对所有身份一律否决
        ("学生", dict(
            name="AAA老鼠肉批发——张总",
            content="#准高三#高三 我们原来B班的学生",
            evidence="我们原来B班的学生"), "商家/机构词"),
        ("医护人员", dict(
            name="深圳市·正盈信科技·随州护士赵洲琪",
            evidence="账号名：深圳市·正盈信科技·随州护士赵洲琪"), "商家/机构词"),
        ("退役军人", dict(
            name="2013老兵基地", content="举报和打击报复的控诉",
            evidence="老兵"), "商家/机构词"),
        ("家长", dict(
            name="千汇月子中心龙岗店维权宝妈",
            evidence="账号名：千汇月子中心龙岗店维权宝妈"), "商家/机构词"),
        # 美术/书法等才艺培训经营者不算教师
        ("教师", dict(
            name="TC 汤成", description="汤克成 鸿鹄岭美术教育校长",
            evidence="简介：汤克成 鸿鹄岭美术教育校长"), "否决词"),
    ])
    def test_rejected(self, identity, kwargs, expect_keyword):
        # type: (str, dict, str) -> None
        """沾边账号必须被拦掉，且拒绝原因可读。"""
        from new_employment_warning.identity_gates import passes_identity_gate

        passed, reason = passes_identity_gate(identity, **kwargs)
        assert passed is False
        assert expect_keyword in reason

    @pytest.mark.parametrize("identity,kwargs", [
        # 有执业资格
        ("律师", dict(
            name="济南冯顺律师",
            verified_reason="北京市道成（济南）律师事务所律师",
            description="执业律师，法学硕士，法律咨询，代理诉讼",
            evidence="认证：律师事务所律师；简介：执业律师")),
        ("家政服务人员", dict(
            name="东北小汤汤",
            description="我是东北的～汤汤是一个住家保姆，喜欢记录日常",
            evidence="简介：是一个住家保姆")),
        ("学生", dict(
            name="旅商小雨学姐",
            description="旅商在读大二电商学生｜见解仅个人分享",
            evidence="旅商在读大二电商学生")),
        ("农民", dict(
            name="梅姐",
            content="挖水沟排水，玉米地里全是水。我是地地道道的老农民",
            evidence="我是地地道道的老农民")),
        # 泛称"农民工" + 具体场景"建筑"，成立
        ("工人", dict(
            name="安徽人在邯务工的农民工",
            description="做建筑工程单项，七〇后。",
            evidence="账号名：安徽人在邯务工的农民工；简介：做建筑工程单项")),
        ("退役军人", dict(
            name="芝",
            content="我们长阳这些退役老兵，只能眼睁睁盼。去年去退役军人事务局去问",
            evidence="我们长阳这些退役老兵")),
        ("货车司机", dict(
            name="卡车司机-小郑",
            description="我是一个来自农村的货车司机，用抖音记录货车生涯",
            evidence="简介：我是一个来自农村的货车司机")),
        ("外卖员", dict(
            name="奇奇送外卖",
            description="逆袭中90后外卖小哥 现在跑外卖，努力挣钱",
            evidence="简介：逆袭中90后外卖小哥")),
        ("医护人员", dict(
            name="张医生", verified_reason="个人认证",
            description="三甲医院儿科医师",
            content="我是儿科医生，今天值夜班", evidence="我是儿科医生")),
        ("家长", dict(
            name="二胎宝妈小李", content="我是两个孩子的宝妈，记录带娃生活",
            evidence="我是两个孩子的宝妈")),
        ("老人", dict(
            name="老李头", content="我退休了，每天在公园遛鸟下棋",
            evidence="我退休了")),
        ("教师", dict(
            name="李老师", description="某中学语文老师，班主任",
            content="今天带班开家长会", evidence="简介：某中学语文老师，班主任")),
        # 「律师事务所」是职业资格证明，不能被商家/机构词表误伤
        ("律师", dict(
            name="北京姬维君律师", description="北京京康律师事务所律师",
            evidence="简介：北京京康律师事务所律师")),
        ("医护人员", dict(
            name="护士小李", description="三甲医院护士",
            evidence="简介：三甲医院护士")),
    ])
    def test_passed(self, identity, kwargs):
        # type: (str, dict) -> None
        """真实从业者必须放行，门槛不能过严。"""
        from new_employment_warning.identity_gates import passes_identity_gate

        passed, reason = passes_identity_gate(identity, **kwargs)
        assert passed is True, "{} 被误拦: {}".format(identity, reason)
        assert "锚点" in reason

    def test_unknown_identity_passes(self):
        # type: () -> None
        """未配置门槛的身份默认放行，不阻断新增身份。"""
        from new_employment_warning.identity_gates import passes_identity_gate

        passed, _reason = passes_identity_gate("某个新身份", evidence="随便")
        assert passed is True

    def test_empty_text_rejected(self):
        # type: () -> None
        """完全没有文本时拒绝，避免空证据通过。"""
        from new_employment_warning.identity_gates import passes_identity_gate

        passed, reason = passes_identity_gate("律师")
        assert passed is False
        assert "无可用文本" in reason

    def test_all_standard_identities_have_gate(self):
        # type: () -> None
        """20 个标准身份都必须配置门槛，避免新增身份漏配导致门槛失效。"""
        from new_employment_warning.general_judge import ALLOWED_IDENTITIES
        from new_employment_warning.identity_gates import IDENTITY_GATES

        missing = sorted(ALLOWED_IDENTITIES - set(IDENTITY_GATES))
        assert not missing, "以下标准身份缺少门槛配置: {}".format(missing)


class TestCleanupOldOutputs(object):
    """产物自动清理测试。

    每天一份 xlsx + jsonl，长期跑会堆几百个文件，所以每次运行结束自动清理。
    重点是**绝不能误删断点文件和回溯产物**——断点丢了会导致重复扫描几十小时。
    """

    def _make(self, directory, name, days_ago):
        # type: (object, str, float) -> str
        """在目录里造一个指定修改时间的文件。"""
        import os
        import time

        path = str(directory / name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x")
        stamp = time.time() - days_ago * 86400
        os.utime(path, (stamp, stamp))
        return path

    def test_removes_expired_keeps_fresh(self, tmp_path):
        # type: (object) -> None
        """超过保留期的删掉，当天的留下。"""
        import os

        from new_employment_warning.daily_identity_job import cleanup_old_outputs

        self._make(tmp_path, "daily_identity_20260801_010101.xlsx", 5)
        self._make(tmp_path, "daily_identity_20260801_010101.jsonl", 5)
        fresh = self._make(tmp_path, "daily_identity_20260805_020202.xlsx", 0)

        result = cleanup_old_outputs(keep_days=1, output_dir=str(tmp_path))
        assert len(result["removed"]) == 2
        assert result["kept"] == 1
        assert os.path.exists(fresh)

    def test_never_touches_checkpoint_or_backfill(self, tmp_path):
        # type: (object) -> None
        """断点文件、回溯产物、其它无关文件一律不动，即使已过期。"""
        import os

        from new_employment_warning.daily_identity_job import cleanup_old_outputs

        protected = [
            self._make(tmp_path, "backfill_artificial_warning_push_2026.checkpoint.json", 30),
            self._make(tmp_path, "backfill_20260101.jsonl", 30),
            self._make(tmp_path, "hits_artificial_warning_push_2026.jsonl", 30),
            self._make(tmp_path, "已确认写入账号_完整文档.json", 30),
        ]
        backfill_dir = tmp_path / "backfill"
        backfill_dir.mkdir()
        nested = self._make(backfill_dir, "daily_identity_20260101_000000.jsonl", 30)

        result = cleanup_old_outputs(keep_days=1, output_dir=str(tmp_path))
        assert result["removed"] == []
        for path in protected:
            assert os.path.exists(path), "不该删 {}".format(path)
        # 不递归子目录，回溯目录里的同名文件也不受影响
        assert os.path.exists(nested)

    @pytest.mark.parametrize("keep_days", [0, -1, None])
    def test_disabled_or_missing_dir(self, tmp_path, keep_days):
        # type: (object, int) -> None
        """keep_days<=0 时不清理；目录不存在时安全返回。"""
        import os

        from new_employment_warning.daily_identity_job import cleanup_old_outputs

        old = self._make(tmp_path, "daily_identity_20260101_000000.xlsx", 99)
        if keep_days is not None:
            result = cleanup_old_outputs(keep_days=keep_days, output_dir=str(tmp_path))
            assert result["removed"] == []
            assert os.path.exists(old)

        missing = cleanup_old_outputs(keep_days=1, output_dir=str(tmp_path / "nope"))
        assert missing["removed"] == []

    def test_keep_days_boundary(self, tmp_path):
        # type: (object) -> None
        """保留 3 天时，2 天前的留、4 天前的删。"""
        from new_employment_warning.daily_identity_job import cleanup_old_outputs

        self._make(tmp_path, "daily_identity_a.xlsx", 2)
        self._make(tmp_path, "daily_identity_b.xlsx", 4)

        result = cleanup_old_outputs(keep_days=3, output_dir=str(tmp_path))
        assert result["removed"] == ["daily_identity_b.xlsx"]
        assert result["kept"] == 1


class TestBackfillJob(object):
    """历史回溯任务测试。

    回溯要处理的量很大（2025 单年身份词候选唯一账号 528 万），
    跨天账号去重、倒序遍历和断点续跑是控制成本的关键。
    """

    def test_dates_descending(self):
        # type: () -> None
        """日期从新到旧遍历：中途停下时已完成的是价值最高的近期数据。"""
        from new_employment_warning.backfill_identity_job import iter_dates_desc

        dates = iter_dates_desc("2026-07-28", "2026-07-31")
        assert dates == ["2026-07-31", "2026-07-30", "2026-07-29", "2026-07-28"]

    def test_single_day_range(self):
        # type: () -> None
        """起止同一天时只产出一天。"""
        from new_employment_warning.backfill_identity_job import iter_dates_desc

        assert iter_dates_desc("2026-07-28", "2026-07-28",
                               clamp_to_yesterday=False) == ["2026-07-28"]

    def test_end_date_clamped_to_yesterday(self):
        # type: () -> None
        """结束日期截断到昨天，不空跑未来日期。

        真实踩坑：`--end-date 2026-12-31` 跑全年时，从 12-31 倒序空转了
        近 150 天才走到有数据的日期。未来数据交给每日增量任务处理。
        """
        import datetime

        from new_employment_warning.backfill_identity_job import iter_dates_desc

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        future = (datetime.date.today() + datetime.timedelta(days=200))
        start = (yesterday - datetime.timedelta(days=3)).strftime("%Y-%m-%d")

        dates = iter_dates_desc(start, future.strftime("%Y-%m-%d"))
        assert dates[0] == yesterday.strftime("%Y-%m-%d")
        assert len(dates) == 4

    def test_all_future_range_returns_empty(self):
        # type: () -> None
        """区间完全在未来时返回空列表，调用方据此直接结束。"""
        import datetime

        from new_employment_warning.backfill_identity_job import iter_dates_desc

        start = (datetime.date.today() + datetime.timedelta(days=10))
        end = (datetime.date.today() + datetime.timedelta(days=20))
        assert iter_dates_desc(start.strftime("%Y-%m-%d"),
                               end.strftime("%Y-%m-%d")) == []

    def test_clamp_can_be_disabled(self):
        # type: () -> None
        """显式关闭截断时保留原区间（供测试与特殊场景使用）。"""
        dates = __import__(
            "new_employment_warning.backfill_identity_job",
            fromlist=["iter_dates_desc"],
        ).iter_dates_desc("2030-01-01", "2030-01-03", clamp_to_yesterday=False)
        assert dates == ["2030-01-03", "2030-01-02", "2030-01-01"]

    def test_dedup_marks_and_skips(self):
        # type: () -> None
        """去重器：标记过的账号后续一律跳过，避免重复消耗模型调用。"""
        from new_employment_warning.backfill_identity_job import AccountDedup

        dedup = AccountDedup(enabled=True)
        # 强制走内存模式，避免测试依赖 Redis
        dedup.bloom = None
        dedup.backend = "memory"

        assert dedup.seen("抖音|123") is False
        dedup.mark("抖音|123")
        assert dedup.seen("抖音|123") is True
        assert dedup.seen("抖音|456") is False

    def test_dedup_disabled_never_skips(self):
        # type: () -> None
        """关闭去重时每个账号都要重新判断。"""
        from new_employment_warning.backfill_identity_job import AccountDedup

        dedup = AccountDedup(enabled=False)
        dedup.mark("抖音|123")
        assert dedup.seen("抖音|123") is False

    def test_dry_run_must_not_mark_accounts(self):
        # type: () -> None
        """dry_run 不能把账号标记为已处理。

        试跑没有真正写库，如果标记了，正式运行会把这些账号当成"已处理"
        跳过，导致它们永远不会被写入 media_*。这里直接检查 process_day
        的源码，确保 mark 调用被 dry_run 守卫包着。
        """
        import inspect

        from new_employment_warning import backfill_identity_job

        source = inspect.getsource(backfill_identity_job.process_day)
        assert "dedup.mark(" in source, "process_day 里应有 dedup.mark 调用"
        # mark 必须位于 "if not dry_run:" 之后，缩进比守卫更深
        guard_index = source.index("if not dry_run:")
        mark_index = source.index("dedup.mark(")
        assert guard_index < mark_index, "dedup.mark 必须在 if not dry_run 守卫内"

    def test_checkpoint_roundtrip(self, tmp_path):
        # type: (object) -> None
        """断点能存能读，已完成日期不会重跑。"""
        from new_employment_warning.backfill_identity_job import (
            _load_checkpoint,
            _save_checkpoint,
        )

        path = str(tmp_path / "ck.json")
        meta = {"source_index": "artificial_warning_push_2026"}
        state = _load_checkpoint(path, meta)
        assert state["done_dates"] == []

        state["done_dates"] = ["2026-07-30"]
        _save_checkpoint(path, state)
        assert _load_checkpoint(path, meta)["done_dates"] == ["2026-07-30"]

    def test_checkpoint_rejects_mismatched_meta(self, tmp_path):
        # type: (object) -> None
        """参数变了必须报错，避免把两次不同口径的结果混进同一个断点。"""
        from new_employment_warning.backfill_identity_job import (
            _load_checkpoint,
            _save_checkpoint,
        )

        path = str(tmp_path / "ck.json")
        _save_checkpoint(path, {"meta": {"source_index": "a"}, "done_dates": []})
        with pytest.raises(ValueError):
            _load_checkpoint(path, {"source_index": "b"})

    def test_checkpoint_error_points_out_the_diff(self, tmp_path):
        # type: (object) -> None
        """报错要指出哪个参数不一致并给出可执行的解决办法。

        真实踩坑：试跑（dry_run=True，7月27~30）留下的断点挡住了正式跑
        （dry_run=False，全年），报错只堆了两个 dict，得自己逐字段比对。
        """
        from new_employment_warning.backfill_identity_job import (
            _load_checkpoint,
            _save_checkpoint,
        )

        path = str(tmp_path / "ck.json")
        _save_checkpoint(path, {
            "meta": {"start_date": "2026-07-27", "dry_run": True},
            "done_dates": [],
        })
        with pytest.raises(ValueError) as excinfo:
            _load_checkpoint(path, {"start_date": "2026-01-01", "dry_run": False})
        message = str(excinfo.value)
        assert "start_date" in message and "dry_run" in message
        assert "rm -f" in message and path in message

    def test_dryrun_and_real_use_separate_checkpoints(self):
        # type: () -> None
        """默认断点文件名带参数指纹：试跑与正式跑、不同日期区间互不挡道。"""
        import inspect

        from new_employment_warning import backfill_identity_job

        source = inspect.getsource(backfill_identity_job.run)
        assert "fingerprint" in source, "默认断点路径应包含参数指纹"
        assert "_dryrun" in source, "dry_run 应使用独立的断点文件"

    def test_collect_accounts_skip_callback_signature(self):
        # type: () -> None
        """collect_accounts 必须支持 skip_account 与 window_hours，
        这是两路共用取数逻辑的前提。"""
        import inspect

        from new_employment_warning.daily_identity_job import collect_accounts

        params = inspect.signature(collect_accounts).parameters
        for name in ("index", "skip_account", "window_hours", "max_accounts"):
            assert name in params


class TestIterTimeWindows(object):
    """时间分片测试。

    一天的候选集有 7 万+ 帖，单窗口 search_after 深度分页会让 ES 请求
    越来越慢直到读超时，所以按小时切片。切片必须秒级不重不漏。
    """

    def test_one_hour_windows_cover_full_day(self):
        # type: () -> None
        """一天按 1 小时切成 24 片，首尾与原区间对齐。"""
        from new_employment_warning.daily_identity_job import iter_time_windows

        windows = iter_time_windows(
            "2026-08-02 00:00:00", "2026-08-02 23:59:59", 1)
        assert len(windows) == 24
        assert windows[0] == ("2026-08-02 00:00:00", "2026-08-02 00:59:59")
        assert windows[1] == ("2026-08-02 01:00:00", "2026-08-02 01:59:59")
        assert windows[-1] == ("2026-08-02 23:00:00", "2026-08-02 23:59:59")

    def test_windows_are_contiguous_without_overlap(self):
        # type: () -> None
        """相邻窗口首尾相差恰好 1 秒，既不重叠也不留空隙。"""
        import datetime

        from new_employment_warning.daily_identity_job import iter_time_windows

        fmt = "%Y-%m-%d %H:%M:%S"
        windows = iter_time_windows(
            "2026-08-02 00:00:00", "2026-08-02 23:59:59", 3)
        for previous, current in zip(windows, windows[1:]):
            previous_end = datetime.datetime.strptime(previous[1], fmt)
            current_start = datetime.datetime.strptime(current[0], fmt)
            assert current_start - previous_end == datetime.timedelta(seconds=1)

    def test_last_window_clamped_to_end(self):
        # type: () -> None
        """不能整除时最后一片被截到区间末尾，不会超出。"""
        from new_employment_warning.daily_identity_job import iter_time_windows

        windows = iter_time_windows(
            "2026-08-02 00:00:00", "2026-08-02 10:00:00", 4)
        assert windows[-1][1] == "2026-08-02 10:00:00"

    @pytest.mark.parametrize("hours", [0, None])
    def test_no_slicing(self, hours):
        # type: (int) -> None
        """hours 为 0 或 None 时退化为单个窗口。"""
        from new_employment_warning.daily_identity_job import iter_time_windows

        windows = iter_time_windows(
            "2026-08-02 00:00:00", "2026-08-02 23:59:59", hours)
        assert windows == [("2026-08-02 00:00:00", "2026-08-02 23:59:59")]


class TestSearchWithRetry(object):
    """ES 读超时重试测试。"""

    def test_returns_on_first_success(self):
        # type: () -> None
        """首次成功时不重试。"""
        from new_employment_warning.daily_identity_job import search_with_retry

        calls = []

        class FakeClient(object):
            def search(self, **kwargs):
                calls.append(kwargs)
                return {"hits": {"hits": []}}

        result = search_with_retry(FakeClient(), {"query": {}}, 300)
        assert result == {"hits": {"hits": []}}
        assert len(calls) == 1

    def test_retries_then_succeeds(self):
        # type: () -> None
        """前两次超时、第三次成功时返回结果。"""
        from new_employment_warning.daily_identity_job import search_with_retry

        state = {"calls": 0}

        class FlakyClient(object):
            def search(self, **kwargs):
                state["calls"] += 1
                if state["calls"] < 3:
                    raise IOError("read timeout")
                return {"ok": True}

        result = search_with_retry(
            FlakyClient(), {"query": {}}, 300, retries=2, timeout=1)
        assert result == {"ok": True}
        assert state["calls"] == 3

    def test_raises_after_retries_exhausted(self):
        # type: () -> None
        """重试用尽后抛出最后一次异常，由上层感知失败。"""
        from new_employment_warning.daily_identity_job import search_with_retry

        class DeadClient(object):
            def search(self, **kwargs):
                raise IOError("read timeout")

        with pytest.raises(IOError):
            search_with_retry(
                DeadClient(), {"query": {}}, 300, retries=1, timeout=1)


class TestBuildCandidateQuery(object):
    """候选帖查询构造测试。"""

    def test_uses_multi_match_phrase(self):
        # type: () -> None
        """每个别名用一条 multi_match/phrase 表达，避免子句数按字段翻倍。

        原实现是 别名 × 3 字段 = 408 条 match_phrase，ES 解析打分开销过大，
        全量拉取时会读超时。
        """
        from new_employment_warning.daily_identity_job import (
            ALL_ALIASES,
            build_candidate_query,
        )

        query = build_candidate_query(
            "2026-08-02 00:00:00", "2026-08-02 00:59:59")
        should = query["bool"]["filter"][-1]["bool"]["should"]
        assert len(should) == len(ALL_ALIASES)
        first = should[0]["multi_match"]
        assert first["type"] == "phrase"
        assert first["fields"] == ["author_persona.name", "title", "content"]

    def test_filters_include_time_and_required_fields(self):
        # type: () -> None
        """过滤条件含时间窗、账号 id 与平台名存在性。"""
        from new_employment_warning.daily_identity_job import build_candidate_query

        filters = build_candidate_query(
            "2026-08-02 00:00:00", "2026-08-02 00:59:59")["bool"]["filter"]
        time_range = filters[0]["range"]["publishTime"]
        assert time_range["gte"] == "2026-08-02 00:00:00"
        assert time_range["lte"] == "2026-08-02 00:59:59"
        assert time_range["time_zone"] == "+08:00"
        exists_fields = {
            item["exists"]["field"] for item in filters if "exists" in item
        }
        assert exists_fields == {"author_persona.id", "siteName.keyword"}


class TestRoughPrefilter(object):
    """本地粗预筛测试。"""

    def test_organization_rejected(self):
        # type: () -> None
        """机构账号直接排除，不消耗 ES 查询和模型调用。"""
        from new_employment_warning.daily_identity_job import rough_prefilter

        account = {
            "name": "某市人民医院", "verified_reason": "机构认证", "description": "",
            "posts": [{"title": "", "content": "我院医生提醒市民及时就诊"}],
        }
        assert rough_prefilter(account) is False

    def test_alias_hit_passes(self):
        # type: () -> None
        """命中身份别名的账号进入后续流程。"""
        from new_employment_warning.daily_identity_job import rough_prefilter

        account = {
            "name": "老王", "verified_reason": "", "description": "",
            "posts": [{"title": "", "content": "我是一名外卖骑手"}],
        }
        assert rough_prefilter(account) is True

    def test_no_alias_rejected(self):
        # type: () -> None
        """完全不含身份别名的账号在这一步就被砍掉。"""
        from new_employment_warning.daily_identity_job import rough_prefilter

        account = {
            "name": "路人甲", "verified_reason": "", "description": "",
            "posts": [{"title": "", "content": "今天天气真好，出去玩了"}],
        }
        assert rough_prefilter(account) is False

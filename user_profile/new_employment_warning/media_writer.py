# -*- coding: utf-8 -*-
"""把预警账号的身份判断结果回写到 media_* 画像索引。

写入口径（与需求一致）：

- **三新身份**（外卖员 / 网约车司机 / 货车司机 / 快递员）写入 ``community``，
  同时写 ``three_new_identity`` 标记为「平台配送与运输从业者」，与线上实时管线一致；
- **其余标准身份**（家长/医护人员/教师/学生/老人/农民/牧民/工人/律师/公务员/
  事业单位工作人员/警察/退役军人/家政服务人员/餐饮从业者/维修人员）写入 ``identity``；
- ``identity_standerd`` 由 ``utils/identity_mapper`` 统一标准化后写入。

新旧账号处理方式不同：

- **已有账号**：只 ``update`` 身份相关字段，绝不覆盖爬虫侧维护的账号资料字段；
- **新账号**：按 ``media_*`` 索引 mapping 构造完整文档 ``index`` 进去，
  字段名、类型（如 ``age`` 为 integer、``followers_count`` 为 long）都按 mapping 对齐。

账号是否已存在的判定分两步，避免重复插入：

1. 按 ``site_name|uid`` 批量 ``mget``；
2. 未命中的再按 ``uid`` 批量 ``terms`` 兜底查一次 —— 百度系（百度百家/有驾/
   好看视频/度小视）和 UC 系的 uid 跨子站通用，同一账号在 ``media_baidu`` 里
   可能以另一个 ``site_name`` 存在，只按 ``site_name|uid`` 判断会误判为新账号。
"""
import re
import traceback
from datetime import datetime

from opensearchpy import OpenSearch, helpers

from new_employment_warning.config import ES_CONFIG, NEW_EMPLOYMENT_COMMUNITIES
from new_employment_warning.media_index_mapper import build_doc_id


# 已有账号只允许更新这些身份字段，其余字段保持爬虫侧原值。
UPDATABLE_IDENTITY_FIELDS = (
    "identity", "community", "identity_standerd", "three_new_identity",
)

# 三新身份对应的 identity 大类，与线上实时管线的取值保持一致。
THREE_NEW_IDENTITY_LABEL = "平台配送与运输从业者"

# 新账号插入时的字段类型约束，按 media_* mapping 对齐。
_INTEGER_FIELDS = ("age",)
_LONG_FIELDS = ("followers_count", "friends_count", "statuses_count", "like_count")

_DIGITS = re.compile(r"-?\d+")


def get_client():
    # type: () -> OpenSearch
    """获取 OpenSearch 客户端。"""
    return OpenSearch(**ES_CONFIG)


def split_identities(standard_identities):
    # type: (list) -> tuple
    """把标准身份拆成写 community 的三新身份和写 identity 的其他身份。

    Args:
        standard_identities: 通过校验的标准身份列表。

    Returns:
        tuple: ``(three_new_list, other_list)``，均已去重且保持输入顺序。
    """
    three_new = []
    others = []
    for identity in standard_identities:
        identity = str(identity or "").strip()
        if not identity:
            continue
        bucket = three_new if identity in NEW_EMPLOYMENT_COMMUNITIES else others
        if identity not in bucket:
            bucket.append(identity)
    return three_new, others


def build_identity_fields(standard_identities, identity_map=None):
    # type: (list, dict) -> dict
    """按写入口径构造身份字段。

    Args:
        standard_identities: 通过校验的标准身份列表。
        identity_map: ``utils/identity_mapper.load_identity_mapping()`` 的映射表，
            为 None 时跳过 identity_standerd 标准化。

    Returns:
        dict: 待写入的身份字段，可能包含 ``community``、``three_new_identity``、
        ``identity``、``identity_standerd``；没有任何有效身份时返回空 dict。
    """
    three_new, others = split_identities(standard_identities)
    fields = {}
    if three_new:
        fields["community"] = ",".join(three_new)
        fields["three_new_identity"] = THREE_NEW_IDENTITY_LABEL
    if others:
        fields["identity"] = ",".join(others)

    if identity_map and (three_new or others):
        # identity_standerd 覆盖全部命中身份，便于按标准标签统一检索。
        # 注意 standardize_identity 只认逗号分隔的字符串，直接传 list 会被
        # str(list) 成 "['外卖员']" 而全部落到"其他"，这里必须先 join。
        from utils.identity_mapper import standardize_identity

        standard = standardize_identity(",".join(three_new + others), identity_map)
        if isinstance(standard, (list, tuple, set)):
            standard = ",".join(sorted(str(item) for item in standard if str(item).strip()))
        standard = str(standard or "").strip()
        if standard:
            fields["identity_standerd"] = standard
    return fields


def _to_int(value):
    # type: (object) -> object
    """把 "30岁" / "1.2万" 之类的值提取为整数，取不到返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = _DIGITS.search(str(value))
    return int(match.group()) if match else None


def _clean_text(value):
    # type: (object) -> object
    """清洗文本字段：列表拼接、去掉空占位，空值返回 None 以便跳过。"""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        value = ",".join(str(item) for item in value if str(item).strip())
    value = str(value).replace("[ ]", "").strip()
    return value or None


def build_new_account_doc(account, identity_fields):
    # type: (dict, dict) -> dict
    """按 media_* mapping 为新账号构造完整文档。

    只写 mapping 里实际存在的字段，数值字段做类型转换，空值一律不写入，
    避免给 integer/long 字段塞空串。

    Args:
        account: 预警侧账号信息，需含 ``site_name``、``uid``，
            可选 ``name``/``description``/``verified``/``verified_type``/
            ``verified_reason``/``gender``/``ip_region``/``cpt_location``/
            ``freq_history_location``/``age``/``followers_count`` 等。
        identity_fields: ``build_identity_fields`` 的产出。

    Returns:
        dict: 待 index 的文档；缺少 site_name 或 uid 时返回空 dict。
    """
    site_name = str(account.get("site_name") or "").strip()
    uid = str(account.get("uid") or "").strip()
    doc_id = build_doc_id(site_name, uid)
    if not doc_id:
        return {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc = {
        "id": doc_id,
        "uid": uid,
        "site_name": site_name,
        "create_time": now,
        "update_time": now,
    }

    # 账号资料类文本字段：预警侧有值才写。
    for field in (
            "name", "description", "verified", "verified_type", "verified_reason",
            "gender", "ip_region", "cpt_location", "freq_history_location",
            "location", "post_place", "user_url", "profile_img_url", "uid_org",
    ):
        cleaned = _clean_text(account.get(field))
        if cleaned is None:
            continue
        # 预警侧用 -1 表示"无认证类型"，media_* 既有数据里是空串，不写入更一致。
        if field in ("verified", "verified_type") and cleaned == "-1":
            continue
        doc[field] = cleaned

    for field in _INTEGER_FIELDS + _LONG_FIELDS:
        number = _to_int(account.get(field))
        if number is not None:
            doc[field] = number

    doc.update(identity_fields)
    return doc


def find_existing_docs(client, accounts):
    # type: (OpenSearch, list) -> dict
    """批量判断账号在 media_* 中是否已存在，返回真实文档 id。

    先按 ``site_name|uid`` mget；未命中的再按 ``uid`` 在同一索引内兜底查询，
    命中则复用其真实 ``_id``（解决百度系/UC 系同 uid 不同 site_name 的问题）。

    Args:
        client: OpenSearch 客户端。
        accounts: 账号列表，每项需含 ``dedup_key``、``site_name``、``uid``、
            ``media_index``。

    Returns:
        dict: ``{dedup_key: {"doc_id", "media_index", "matched_by",
        "source"}}``，只包含已存在的账号。
    """
    existing = {}
    by_index = {}
    for account in accounts:
        media_index = account.get("media_index")
        doc_id = build_doc_id(account.get("site_name"), account.get("uid"))
        if not media_index or not doc_id:
            continue
        by_index.setdefault(media_index, []).append((account, doc_id))

    fetch_source = [
        "id", "uid", "site_name", "name", "description", "verified",
        "verified_type", "verified_reason", "identity", "community",
        "identity_standerd", "three_new_identity",
    ]

    for media_index, items in by_index.items():
        # ---- 第一步：按 site_name|uid 精确 mget ----
        pending = []
        for chunk_start in range(0, len(items), 500):
            chunk = items[chunk_start:chunk_start + 500]
            docs = client.mget(
                index=media_index,
                body={"ids": [doc_id for _account, doc_id in chunk]},
                _source=fetch_source,
                request_timeout=120,
            )["docs"]
            for (account, doc_id), doc in zip(chunk, docs):
                if doc.get("found"):
                    existing[account["dedup_key"]] = {
                        "doc_id": doc_id,
                        "media_index": media_index,
                        "matched_by": "doc_id",
                        "source": doc.get("_source", {}),
                    }
                else:
                    pending.append(account)

        # ---- 第二步：未命中的按 uid 兜底（跨 site_name 复用同一 uid）----
        for chunk_start in range(0, len(pending), 200):
            chunk = pending[chunk_start:chunk_start + 200]
            uid_to_accounts = {}
            for account in chunk:
                uid_to_accounts.setdefault(str(account["uid"]), []).append(account)
            if not uid_to_accounts:
                continue
            response = client.search(
                index=media_index,
                size=len(uid_to_accounts) * 3,
                _source=fetch_source,
                body={"query": {"terms": {"uid": list(uid_to_accounts.keys())}}},
                request_timeout=120,
            )
            for hit in response["hits"]["hits"]:
                source = hit.get("_source", {})
                uid = str(source.get("uid") or "")
                for account in uid_to_accounts.get(uid, []):
                    if account["dedup_key"] in existing:
                        continue
                    existing[account["dedup_key"]] = {
                        "doc_id": hit["_id"],
                        "media_index": hit["_index"],
                        "matched_by": "uid",
                        "source": source,
                    }
    return existing


def build_actions(accounts, existing, identity_map=None):
    # type: (list, dict, dict) -> tuple
    """构造 bulk 操作列表。

    Args:
        accounts: 命中身份的账号列表，每项需含 ``dedup_key``、``site_name``、
            ``uid``、``media_index``、``standard_identities``。
        existing: ``find_existing_docs`` 的产出。
        identity_map: 身份标准化映射表。

    Returns:
        tuple: ``(actions, stats, skipped)``。``stats`` 统计 update/insert 数量，
        ``skipped`` 是被跳过的账号及原因。
    """
    actions = []
    skipped = []
    stats = {"update": 0, "insert": 0, "no_identity_field": 0}

    for account in accounts:
        identity_fields = build_identity_fields(
            account.get("standard_identities") or [], identity_map,
        )
        if not identity_fields:
            stats["no_identity_field"] += 1
            skipped.append((account.get("dedup_key"), "无有效身份字段"))
            continue

        account["identity_fields"] = identity_fields
        hit = existing.get(account["dedup_key"])
        if hit:
            # 已有账号：只更新身份字段，其余资料字段保持不动。
            update_doc = dict(identity_fields)
            update_doc["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            actions.append({
                "_op_type": "update",
                "_index": hit["media_index"],
                "_id": hit["doc_id"],
                "doc": update_doc,
                "retry_on_conflict": 5,
            })
            account["write_mode"] = "update"
            account["written_doc_id"] = hit["doc_id"]
            account["written_index"] = hit["media_index"]
            stats["update"] += 1
        else:
            doc = build_new_account_doc(account, identity_fields)
            if not doc:
                skipped.append((account.get("dedup_key"), "缺少site_name或uid"))
                continue
            actions.append({
                "_op_type": "index",
                "_index": account["media_index"],
                "_id": doc["id"],
                "_source": doc,
            })
            account["write_mode"] = "insert"
            account["written_doc_id"] = doc["id"]
            account["written_index"] = account["media_index"]
            stats["insert"] += 1
    return actions, stats, skipped


def write_back(accounts, identity_map=None, client=None, dry_run=False):
    # type: (list, dict, OpenSearch, bool) -> dict
    """把命中身份的账号回写到 media_*。

    Args:
        accounts: 命中身份的账号列表。
        identity_map: 身份标准化映射表。
        client: 复用的 OpenSearch 客户端，为 None 时新建。
        dry_run: 为 True 时只计算不实际写入，便于验证。

    Returns:
        dict: 写入统计，含 update/insert/failed 数量与错误摘要。
    """
    result = {
        "accounts": len(accounts),
        "update": 0, "insert": 0, "failed": 0,
        "no_identity_field": 0, "skipped": [], "errors": [],
        "dry_run": dry_run,
    }
    if not accounts:
        return result

    client = client or get_client()
    existing = find_existing_docs(client, accounts)
    actions, stats, skipped = build_actions(accounts, existing, identity_map)
    result.update({
        "update": stats["update"],
        "insert": stats["insert"],
        "no_identity_field": stats["no_identity_field"],
        "skipped": skipped,
        "existing_matched_by_uid": sum(
            1 for hit in existing.values() if hit["matched_by"] == "uid"
        ),
    })
    if dry_run or not actions:
        return result

    try:
        success, errors = helpers.bulk(
            client, actions, raise_on_error=False, request_timeout=180,
        )
        result["bulk_success"] = success
        for error in errors[:20]:
            result["errors"].append(str(error)[:300])
        result["failed"] = len(errors)
    except Exception:
        result["failed"] = len(actions)
        result["errors"].append(traceback.format_exc(limit=2))
    return result

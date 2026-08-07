# -*- coding: utf-8 -*-
"""预警账号身份判断的统一 LLM 客户端。

统一走线上实时管线在用的阿里云百炼 ``qwen3.5-flash``（见
``utils/http_llm_factory``），不再单独连火山引擎豆包，保证预警批量任务
和线上实时管线的模型口径、密钥、限流策略完全一致。

使用方式::

    from new_employment_warning.llm_client import chat_json

    parsed, request_id, error = chat_json(SYSTEM_PROMPT, user_text)
    if error:
        ...  # 调用或解析失败
"""
import json
import re

from utils.http_llm_factory import LLM_MODEL, _call_llm

try:
    import dirtyjson
except ImportError:  # pragma: no cover - 兜底解析器缺失时退化为标准库
    dirtyjson = None


# 对外暴露当前使用的模型名，便于运行汇总里记录口径。
MODEL_NAME = LLM_MODEL

# 从混杂文本中截取最外层 JSON 对象/数组，兼容模型偶尔带前后缀说明的情况。
_JSON_SPAN = re.compile(r"[\[{].*[\]}]", re.DOTALL)


def strip_json(text):
    # type: (str) -> str
    """去除模型可能包裹的 ```json 代码块标记。

    Args:
        text: 模型原始返回文本。

    Returns:
        去掉代码块标记后的纯 JSON 文本。
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    return text.strip()


def loads_tolerant(text):
    # type: (str) -> object
    """尽最大努力把模型返回文本解析成 JSON。

    模型偶尔会在证据字段里带未转义引号、尾随逗号，或在 JSON 前后附带说明文字，
    标准库 ``json.loads`` 会直接失败。这里按三级兜底解析：

    1. 标准 ``json.loads``；
    2. 截取最外层 ``{...}`` / ``[...]`` 片段后再解析；
    3. 用 ``dirtyjson`` 容错解析（可解未转义引号、单引号、尾随逗号）。

    Args:
        text: 模型返回的原始文本。

    Returns:
        解析后的 dict/list。

    Raises:
        ValueError: 三级兜底都失败时抛出。
    """
    cleaned = strip_json(text)
    candidates = [cleaned]
    span = _JSON_SPAN.search(cleaned)
    if span and span.group(0) != cleaned:
        candidates.append(span.group(0))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            pass
    if dirtyjson is not None:
        for candidate in candidates:
            try:
                # dirtyjson 返回自有的 AttributedDict/List，转成原生类型便于下游使用。
                return json.loads(json.dumps(dirtyjson.loads(candidate)))
            except Exception:
                pass
    raise ValueError("无法解析为JSON")


def chat_json(system_prompt, user_text, max_retries=3):
    # type: (str, str, int) -> tuple
    """调用 qwen3.5-flash 并把返回内容解析为 JSON 对象。

    Args:
        system_prompt: 系统提示词（``_call_llm`` 内部带 cache_control 复用缓存）。
        user_text: 待判断的用户文本。
        max_retries: 最大重试次数，默认 3。

    Returns:
        tuple: ``(parsed, request_id, error)``。成功时 ``error`` 为空串，
        ``parsed`` 为解析后的 dict/list；失败时 ``parsed`` 为 None。
    """
    content, request_id, _cache_rate, error = _call_llm(
        system_prompt, user_text, max_retries=max_retries,
    )
    if error:
        return None, request_id, "模型调用失败:{}".format(error)
    if not content:
        return None, request_id, "模型空返回"
    try:
        return loads_tolerant(content), request_id, ""
    except Exception as exc:
        return None, request_id, "JSON解析失败:{}[{}]".format(exc, content[:200])

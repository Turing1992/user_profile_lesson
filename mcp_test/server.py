"""
MCP Server 教学示例 - 文本工具箱

=== MCP 核心概念 ===

1. Server: MCP 服务器实例，是整个服务的核心
2. Tool: 定义一个工具（名称、描述、参数 schema）
3. list_tools(): 注册一个处理器，告诉客户端"我有哪些工具"
4. call_tool(): 注册一个处理器，当客户端调用工具时执行对应逻辑
5. stdio_server: 通过标准输入/输出与客户端通信（Kiro 就是通过这种方式连接的）

=== 运行方式 ===

MCP Server 不是 HTTP 服务，而是通过 stdin/stdout 与客户端通信。
Kiro 会在 .kiro/settings/mcp.json 中配置如何启动这个 server。
"""

import asyncio
import json
import re
from collections import Counter
from typing import Any, Dict, List

# === 第一步：导入 MCP 核心模块 ===
# Server: 创建 MCP 服务器实例
# stdio_server: 提供 stdin/stdout 通信通道
# Tool: 定义工具的数据结构
# TextContent: 工具返回文本结果的数据结构
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# === 第二步：创建 Server 实例 ===
# 参数是服务器名称，客户端会用这个名称来识别你的 server
server = Server("text-toolbox")


# === 第三步：注册 list_tools 处理器 ===
# 这个装饰器告诉 MCP 框架：当客户端问"你有什么工具"时，调用这个函数
# 返回一个 Tool 列表，每个 Tool 包含：
#   - name: 工具名称（客户端调用时用这个名字）
#   - description: 工具描述（AI 根据这个描述决定什么时候用这个工具）
#   - inputSchema: JSON Schema 格式的参数定义（告诉 AI 需要传什么参数）
@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="word_count",
            description="统计文本的字数、行数、段落数等基本信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要统计的文本内容"
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="find_and_replace",
            description="在文本中查找并替换指定内容，支持正则表达式",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "原始文本"
                    },
                    "find": {
                        "type": "string",
                        "description": "要查找的内容（支持正则表达式）"
                    },
                    "replace": {
                        "type": "string",
                        "description": "替换为的内容"
                    },
                    "use_regex": {
                        "type": "boolean",
                        "description": "是否使用正则表达式匹配",
                        "default": False
                    }
                },
                "required": ["text", "find", "replace"]
            }
        ),
        Tool(
            name="extract_info",
            description="从文本中提取邮箱、URL、手机号等结构化信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要提取信息的文本"
                    },
                    "info_type": {
                        "type": "string",
                        "description": "要提取的信息类型",
                        "enum": ["email", "url", "phone", "all"]
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="text_frequency",
            description="统计文本中词语出现的频率，返回 Top N 高频词",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要分析的文本"
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "返回前 N 个高频词",
                        "default": 10
                    }
                },
                "required": ["text"]
            }
        ),
    ]


# === 第四步：注册 call_tool 处理器 ===
# 当客户端调用某个工具时，这个函数会被触发
# 参数：
#   - name: 工具名称（和 list_tools 中定义的 name 对应）
#   - arguments: 客户端传入的参数（字典格式）
# 返回：TextContent 列表（工具的执行结果）
@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    try:
        if name == "word_count":
            result = handle_word_count(arguments)
        elif name == "find_and_replace":
            result = handle_find_and_replace(arguments)
        elif name == "extract_info":
            result = handle_extract_info(arguments)
        elif name == "text_frequency":
            result = handle_text_frequency(arguments)
        else:
            result = f"未知工具: {name}"

        # 返回结果必须是 TextContent 列表
        return [TextContent(type="text", text=result)]

    except Exception as e:
        return [TextContent(type="text", text=f"执行出错: {str(e)}")]


# === 第五步：实现各个工具的业务逻辑 ===
# 这些就是普通的 Python 函数，没有任何 MCP 特殊要求

def handle_word_count(args: Dict[str, Any]) -> str:
    """统计文本基本信息"""
    text = args["text"]

    lines = text.split("\n")
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    # 中文按字符计数，英文按空格分词
    chars = len(text)
    words = len(text.split())
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))

    result = {
        "总字符数": chars,
        "英文单词数": words,
        "中文字符数": chinese_chars,
        "行数": len(lines),
        "段落数": len(paragraphs),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def handle_find_and_replace(args: Dict[str, Any]) -> str:
    """查找替换"""
    text = args["text"]
    find = args["find"]
    replace = args["replace"]
    use_regex = args.get("use_regex", False)

    if use_regex:
        new_text = re.sub(find, replace, text)
        count = len(re.findall(find, text))
    else:
        count = text.count(find)
        new_text = text.replace(find, replace)

    result = {
        "匹配次数": count,
        "替换后文本": new_text,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def handle_extract_info(args: Dict[str, Any]) -> str:
    """提取结构化信息"""
    text = args["text"]
    info_type = args.get("info_type", "all")

    patterns = {
        "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "url": r'https?://[^\s<>"{}|\\^`\[\]]+',
        "phone": r'1[3-9]\d{9}',
    }

    result = {}
    types_to_extract = patterns.keys() if info_type == "all" else [info_type]

    for t in types_to_extract:
        if t in patterns:
            matches = re.findall(patterns[t], text)
            result[t] = list(set(matches))  # 去重

    return json.dumps(result, ensure_ascii=False, indent=2)


def handle_text_frequency(args: Dict[str, Any]) -> str:
    """词频统计"""
    text = args["text"]
    top_n = args.get("top_n", 10)

    # 简单分词：按空格和标点分割
    words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text.lower())
    # 过滤掉单字符的英文词
    words = [w for w in words if len(w) > 1]

    counter = Counter(words)
    top_words = counter.most_common(top_n)

    result = {
        "总词数": len(words),
        "不重复词数": len(counter),
        "高频词": [{"词": w, "次数": c} for w, c in top_words],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# === 第六步：启动服务器 ===
# stdio_server() 创建一个基于 stdin/stdout 的通信通道
# server.run() 开始监听并处理来自客户端的请求
#
# 整个流程：
# 1. Kiro 启动这个 Python 进程
# 2. Kiro 通过 stdin 发送 JSON-RPC 请求（如 "列出工具"、"调用工具"）
# 3. 这个进程通过 stdout 返回 JSON-RPC 响应
# 4. Kiro 解析响应并展示给用户
#
# 注意：mcp >= 1.20 版本中，server.run() 需要显式传入 InitializationOptions
# 旧版可以用 server.create_initialization_options()，新版签名有变化
from mcp.server.models import InitializationOptions

async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(
            read_stream,
            write_stream,
            init_options
        )


if __name__ == "__main__":
    asyncio.run(main())

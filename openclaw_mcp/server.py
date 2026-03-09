"""
OpenClaw MCP Server - Bridge between Kiro and OpenClaw
通过 CLI subprocess 调用本地 OpenClaw Agent，让 Kiro 可以直接使用 OpenClaw
"""
import asyncio
import json
from mcp.server.fastmcp import FastMCP

OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
SESSION_ID = "kiro2"

mcp = FastMCP("openclaw-bridge", instructions="OpenClaw AI Agent 桥接服务，通过此工具可以调用本地运行的 OpenClaw Agent")


async def _run_cli(args: list[str], timeout: int = 120) -> str:
    """执行 openclaw CLI 命令并返回结果"""
    try:
        proc = await asyncio.create_subprocess_exec(
            OPENCLAW_BIN, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8").strip()
        if proc.returncode != 0:
            err = stderr.decode("utf-8").strip()
            return f"命令执行失败 (code {proc.returncode}): {err or output}"
        return output
    except asyncio.TimeoutError:
        proc.kill()
        return f"OpenClaw 响应超时（{timeout}秒）"
    except FileNotFoundError:
        return f"找不到 openclaw 命令，请确认已安装: {OPENCLAW_BIN}"
    except Exception as e:
        return f"执行错误: {str(e)}"


@mcp.tool()
async def ask_openclaw(message: str) -> str:
    """发送消息给 OpenClaw Agent 并获取回复。
    OpenClaw 可以执行文件操作、上网搜索、调用各种 skills 等任务。

    Args:
        message: 要发送给 OpenClaw 的消息/指令
    """
    raw = await _run_cli(
        ["agent", "-m", message, "--session-id", SESSION_ID, "--json", "--timeout", "120"],
        timeout=130,
    )
    # 尝试解析 JSON 提取文本
    try:
        data = json.loads(raw)
        result = data.get("result", {})
        payloads = result.get("payloads", [])
        texts = [p.get("text", "") for p in payloads if p.get("text")]
        if texts:
            return "\n".join(texts)
        # fallback: 直接返回 result 中的内容
        if isinstance(result, str):
            return result
        return raw
    except (json.JSONDecodeError, AttributeError):
        return raw


@mcp.tool()
async def openclaw_status() -> str:
    """检查 OpenClaw Gateway 的运行状态"""
    return await _run_cli(["daemon", "status"], timeout=10)


@mcp.tool()
async def openclaw_sessions() -> str:
    """列出 OpenClaw 的所有会话"""
    return await _run_cli(
        ["agent", "-m", "列出所有会话", "--session-id", SESSION_ID, "--json", "--timeout", "30"],
        timeout=35,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

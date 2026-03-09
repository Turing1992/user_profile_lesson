# 文件: mcp_two_layer_mysql_demo.py
from __future__ import annotations
import logging
import re
import pymysql.cursors
from typing import Any, Dict, List, Tuple
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP

# Logging 设置，避免 stdio 干扰
logging.basicConfig(level=logging.INFO)

mcp = FastMCP("two_layer_intent_mysql_demo")

# 你的 MySQL 连接配置
CONFIG = {
    'host': '192.168.19.64',
    'port': 3306,
    'user': 'buser',
    'password': 'p3jnmja3',
    'database': 'event_data',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# MCP 模型类定义
class PrimaryClassification(BaseModel):
    label: str
    confidence: float
    rationale: str

class SecondaryClassification(BaseModel):
    label: str
    confidence: float
    rationale: str

class QueryResult(BaseModel):
    items: List[Dict[str, Any]]

# 一级意图关键词集合
GOV_KEYWORDS = ["政务", "政府", "涉党", "负面"]
MKT_KEYWORDS = ["营销", "推广", "兴趣", "带货"]

# 二级意图可选项定义
SECONDARY_OPTIONS = {
    "政务任务": ["涉党负面言论账号", "理想汽车负面事件账号"],
    "企业营销任务": ["对滑雪感兴趣账号", "对奢侈品感兴趣账号"]
}

def simple_score(text: str, keywords: List[str]) -> int:
    return sum(1 for kw in keywords if kw in text)

@mcp.tool()
async def classify_primary(text: str) -> PrimaryClassification:
    gov = simple_score(text, GOV_KEYWORDS)
    mkt = simple_score(text, MKT_KEYWORDS)
    label = "政务任务" if gov > mkt else "企业营销任务"
    confidence = abs(gov - mkt) / (gov + mkt + 1e-6)
    return PrimaryClassification(label=label, confidence=round(confidence,3),
                                 rationale=f"GOV={gov}, MKT={mkt}")

@mcp.tool()
async def classify_secondary(primary: str, text: str) -> SecondaryClassification:
    options = SECONDARY_OPTIONS.get(primary, [])
    best = max(options, key=lambda o: 1 if o in text else 0) if options else ""
    score = 1 if best and best in text else 0
    return SecondaryClassification(label=best or "通用", confidence=score,
                                   rationale=f"options={options}; matched={best}")

def query_mysql(primary: str, secondary: str, text: str) -> List[Dict[str, Any]]:
    # 建立连接
    conn = pymysql.connect(**CONFIG)
    cursor = conn.cursor()
    # 示例：按 primary / secondary / text 描述模糊匹配
    sql = """
    SELECT * FROM accounts
    WHERE primary_intent=%s AND secondary_intent=%s AND description LIKE %s
    LIMIT 10
    """
    cursor.execute(sql, (primary, secondary, f"%{text}%"))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

@mcp.tool()
async def query_accounts(primary: str, secondary: str, text: str) -> QueryResult:
    rows = query_mysql(primary, secondary, text)
    return QueryResult(items=rows)

@mcp.tool()
async def route_query(text: str) -> Dict[str, Any]:
    p = await classify_primary(text)
    s = await classify_secondary(p.label, text)
    qr = await query_accounts(p.label, s.label, text)
    return {
        "primary": p.model_dump(),
        "secondary": s.model_dump(),
        "results": qr.items
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")

"""
MCP服务器 - 意图识别系统
"""
import asyncio
import time
import hashlib
import sys
import os
from typing import Any, Dict, List

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 配置简单的日志记录
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from intent_recognition_system.services.triplet_extractor import TripletExtractor
from intent_recognition_system.services.account_searcher import AccountSearcher
from intent_recognition_system.models.triplet import IntentResult
from intent_recognition_system.config.config import MCP_CONFIG


class IntentRecognitionServer:
    """意图识别MCP服务器"""
    
    def __init__(self):
        self.server = Server(MCP_CONFIG["server_name"])
        self.triplet_extractor = TripletExtractor()
        self.account_searcher = AccountSearcher()
        self._setup_tools()
    
    def _setup_tools(self):
        """设置MCP工具"""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """列出可用工具"""
            return [
                Tool(
                    name="analyze_event_intent",
                    description="分析事件并识别参与评论的账号群体",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "event_description": {
                                "type": "string",
                                "description": "事件描述"
                            },
                            "use_cache": {
                                "type": "boolean",
                                "description": "是否使用缓存",
                                "default": True
                            }
                        },
                        "required": ["event_description"]
                    }
                ),
                Tool(
                    name="extract_triplets",
                    description="从事件描述中提取三元组",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "event_description": {
                                "type": "string",
                                "description": "事件描述"
                            }
                        },
                        "required": ["event_description"]
                    }
                ),
                Tool(
                    name="search_accounts",
                    description="根据关键词搜索相关账号",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "keywords": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "搜索关键词列表"
                            }
                        },
                        "required": ["keywords"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """调用工具"""
            try:
                if name == "analyze_event_intent":
                    return await self._analyze_event_intent(arguments)
                elif name == "extract_triplets":
                    return await self._extract_triplets(arguments)
                elif name == "search_accounts":
                    return await self._search_accounts(arguments)
                else:
                    return [TextContent(type="text", text=f"未知工具: {name}")]
                    
            except Exception as e:
                logger.error(f"工具调用失败 {name}: {e}")
                return [TextContent(type="text", text=f"工具执行失败: {str(e)}")]
    
    async def _analyze_event_intent(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """分析事件意图"""
        event_description = arguments["event_description"]
        use_cache = arguments.get("use_cache", True)
        
        start_time = time.time()
        
        # 生成缓存键
        cache_key = f"intent_analysis:{hashlib.md5(event_description.encode()).hexdigest()}"
        
        # 尝试从缓存获取
        if use_cache:
            cached_accounts = self.account_searcher.get_cached_result(cache_key)
            if cached_accounts:
                logger.info("使用缓存结果")
                # 仍需要提取三元组用于展示
                analysis = self.triplet_extractor.extract_triplets(event_description)
                result = IntentResult(
                    event_analysis=analysis,
                    matched_accounts=cached_accounts,
                    total_accounts=len(cached_accounts),
                    processing_time=time.time() - start_time
                )
                return [TextContent(type="text", text=result.json(indent=2, ensure_ascii=False))]
        
        # 提取三元组
        logger.info("开始提取三元组...")
        analysis = self.triplet_extractor.extract_triplets(event_description)
        
        if not analysis.triplets:
            return [TextContent(type="text", text="未能从事件描述中提取到有效的三元组")]
        
        # 搜索相关账号
        logger.info("开始搜索相关账号...")
        accounts = self.account_searcher.search_accounts(analysis)
        
        # 缓存结果
        if use_cache and accounts:
            self.account_searcher.cache_result(cache_key, accounts)
        
        # 构建结果
        result = IntentResult(
            event_analysis=analysis,
            matched_accounts=accounts,
            total_accounts=len(accounts),
            processing_time=time.time() - start_time
        )
        
        logger.info(f"分析完成，找到 {len(accounts)} 个相关账号，耗时 {result.processing_time:.2f}秒")
        
        return [TextContent(type="text", text=result.json(indent=2, ensure_ascii=False))]
    
    async def _extract_triplets(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """提取三元组"""
        event_description = arguments["event_description"]
        
        analysis = self.triplet_extractor.extract_triplets(event_description)
        
        return [TextContent(type="text", text=analysis.json(indent=2, ensure_ascii=False))]
    
    async def _search_accounts(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """搜索账号"""
        keywords = arguments["keywords"]
        
        # 创建临时分析对象
        from intent_recognition_system.models.triplet import EventAnalysis
        analysis = EventAnalysis(
            event_description="关键词搜索",
            all_keywords=keywords
        )
        
        accounts = self.account_searcher.search_accounts(analysis)
        
        result = {
            "keywords": keywords,
            "matched_accounts": [account.dict() for account in accounts],
            "total_accounts": len(accounts)
        }
        
        import json
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]


async def main():
    """启动MCP服务器"""
    logger.info(f"启动意图识别MCP服务器 v{MCP_CONFIG['version']}")
    
    server_instance = IntentRecognitionServer()
    
    # 使用stdio传输
    async with stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=MCP_CONFIG["server_name"],
                server_version=MCP_CONFIG["version"]
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
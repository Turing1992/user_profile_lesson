"""
意图分析器 - 主程序入口
"""
import asyncio
import json
from typing import Optional
from loguru import logger

from services.triplet_extractor import TripletExtractor
from services.account_searcher import AccountSearcher
from models.triplet import IntentResult


class IntentAnalyzer:
    """意图分析器"""
    
    def __init__(self):
        self.triplet_extractor = TripletExtractor()
        self.account_searcher = AccountSearcher()
    
    async def analyze_event(self, event_description: str, use_cache: bool = True) -> IntentResult:
        """分析事件并返回相关账号"""
        import time
        start_time = time.time()
        
        logger.info(f"开始分析事件: {event_description[:50]}...")
        
        # 提取三元组
        analysis = self.triplet_extractor.extract_triplets(event_description)
        
        if not analysis.triplets:
            logger.warning("未提取到有效三元组")
            return IntentResult(
                event_analysis=analysis,
                processing_time=time.time() - start_time
            )
        
        # 搜索相关账号
        accounts = self.account_searcher.search_accounts(analysis)
        
        result = IntentResult(
            event_analysis=analysis,
            matched_accounts=accounts,
            total_accounts=len(accounts),
            processing_time=time.time() - start_time
        )
        
        logger.info(f"分析完成，找到 {len(accounts)} 个相关账号")
        return result
    
    def print_result(self, result: IntentResult):
        """打印分析结果"""
        print("\n" + "="*80)
        print("意图识别分析结果")
        print("="*80)
        
        print(f"\n事件描述: {result.event_analysis.event_description}")
        print(f"处理时间: {result.processing_time:.2f}秒")
        
        print(f"\n提取的三元组 ({len(result.event_analysis.triplets)}个):")
        for i, triplet in enumerate(result.event_analysis.triplets, 1):
            print(f"  {i}. {triplet.subject} -> {triplet.predicate} -> {triplet.object}")
            print(f"     置信度: {triplet.confidence:.2f}")
            print(f"     关键词: {', '.join(triplet.keywords)}")
        
        print(f"\n所有关键词: {', '.join(result.event_analysis.all_keywords)}")
        
        print(f"\n匹配的账号 ({result.total_accounts}个):")
        for i, account in enumerate(result.matched_accounts[:10], 1):  # 只显示前10个
            print(f"  {i}. {account.username} (@{account.account_id})")
            print(f"     平台: {account.platform}")
            print(f"     相关性: {account.relevance_score:.2f}")
            print(f"     评论数: {account.comment_count}")
            print(f"     匹配词: {', '.join(account.matched_keywords[:5])}")
        
        if result.total_accounts > 10:
            print(f"  ... 还有 {result.total_accounts - 10} 个账号")


async def main():
    """主程序"""
    analyzer = IntentAnalyzer()
    
    # 示例事件
    test_events = [
        "网民对新冠疫情防控政策的讨论和评价",
        "用户对电商平台双十一活动的参与和评论",
        "公众对环保政策实施效果的看法和建议"
    ]
    
    print("意图识别系统测试")
    print("="*50)
    
    for i, event in enumerate(test_events, 1):
        print(f"\n测试事件 {i}: {event}")
        
        try:
            result = await analyzer.analyze_event(event)
            analyzer.print_result(result)
            
            # 保存结果到文件
            with open(f"result_{i}.json", "w", encoding="utf-8") as f:
                f.write(result.json(indent=2, ensure_ascii=False))
            
        except Exception as e:
            logger.error(f"分析事件失败: {e}")
        
        print("\n" + "-"*80)


if __name__ == "__main__":
    # 配置日志
    logger.add("logs/intent_analyzer.log", rotation="1 day", retention="7 days")
    
    # 运行主程序
    asyncio.run(main())
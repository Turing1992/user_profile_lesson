#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pandas as pd
import asyncio
import concurrent.futures
from typing import List, Dict, Any
import logging
from datetime import datetime
import os

# 导入配置和工具
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from utils import daoding_body, download_API
    from utils.opinin_extract import identity_auto
    from database import IdentityAutoDatabase
except ImportError as e:
    print(f"Import error: {e}")
    # 如果导入失败，使用备选方案
    from utils.opinin_extract import identity_auto
    from database import IdentityAutoDatabase

logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self):
        self.db = IdentityAutoDatabase()
    
    def data_get(self, keywords, limit=500):
        """
        根据关键词获取数据
        从OpenSearch中搜索包含关键词的用户发帖数据
        """
        try:
            # 尝试使用真实的数据获取API
            try:
                body = daoding_body.daoding_body_gen(keywords)
                result = download_API.get_data(body)
                
                # 处理API返回的数据格式 (contents, total_count)
                # if isinstance(result, tuple) and len(result) == 2:
                #     contents, total_count = result
                #     logger.info(f"Retrieved {len(contents)} records from real API for keywords: {keywords}")
                if True:

                    # 转换数据格式以匹配预期的结构
                    formatted_data = []
                    for item in result[0]:
                        formatted_data.append({
                            "user_id": item.get('user', {}).get('uid', ''),
                            "content": item.get('content', '') or item.get('title', ''),
                            "platform": item.get('source', 'unknown'),
                            "post_time": item.get('publish_time', ''),
                            "url": item.get('url', ''),
                            "es_id": item.get('id', '')
                        })
                    
                    return formatted_data
                # else:
                #     # 如果返回格式不符合预期，使用备选方案
                #     logger.warning("Unexpected API response format, falling back to OpenSearch")
                #     return self._get_opensearch_data(keywords, limit)
                    
            except (NameError, AttributeError) as e:
                logger.warning(f"API modules not available: {e}, using OpenSearch backup")
            
        except Exception as e:
            logger.error(f"Error getting data: {e}")
            # 如果所有方法都失败，返回模拟数据作为备选
            logger.warning("Falling back to mock data")
            return self._get_mock_data(keywords, limit)
    
    # def _get_opensearch_data(self, keywords, limit=500):
    #     """从OpenSearch获取数据的备选方法"""
    #     try:
    #         # 导入OpenSearch配置
    #         from config.config import config
    #         from opensearchpy import OpenSearch
    #
    #         # 初始化OpenSearch客户端
    #         es_client = OpenSearch(**config["ESsearch"])
    #
    #         # 构建搜索查询
    #         search_query = {
    #             "query": {
    #                 "bool": {
    #                     "should": [
    #                         {"match": {"content": keywords}},
    #                         {"match": {"text": keywords}},
    #                         {"match": {"title": keywords}}
    #                     ],
    #                     "minimum_should_match": 1
    #                 }
    #             },
    #             "size": limit,
    #             "_source": ["user_id", "content", "text", "title", "platform", "post_time", "url"]
    #         }
    #
    #         # 执行搜索
    #         response = es_client.search(
    #             index="user_profile*",  # 搜索所有用户画像相关索引
    #             body=search_query
    #         )
    #
    #         # 处理搜索结果
    #         data = []
    #         for hit in response['hits']['hits']:
    #             source = hit['_source']
    #
    #             # 统一内容字段
    #             content = source.get('content') or source.get('text') or source.get('title', '')
    #
    #             data.append({
    #                 "user_id": source.get('user_id', ''),
    #                 "content": content,
    #                 "platform": source.get('platform', 'unknown'),
    #                 "post_time": source.get('post_time', ''),
    #                 "url": source.get('url', ''),
    #                 "es_id": hit['_id']
    #             })
    #
    #         logger.info(f"Retrieved {len(data)} records from OpenSearch for keywords: {keywords}")
    #         return data
    #
    #     except Exception as e:
    #         logger.error(f"Error getting data from OpenSearch: {e}")
    #         raise
    
    def _get_mock_data(self, keywords: str, limit: int) -> List[Dict[str, Any]]:
        """生成模拟数据作为备选方案"""
        mock_data = []
        for i in range(min(limit, 50)):  # 限制模拟数据数量
            mock_data.append({
                "user_id": f"mock_user_{i}",
                "content": f"这是包含关键词 {keywords} 的模拟内容 {i}。我是一名{keywords}从业者，每天工作很辛苦。",
                "platform": "weibo",
                "post_time": "2024-01-01 12:00:00",
                "url": f"https://example.com/post_{i}",
                "es_id": f"mock_{i}"
            })
        
        logger.info(f"Generated {len(mock_data)} mock records for keywords: {keywords}")
        return mock_data
    
    def process_single_item(self, prompt: str, data_item: Dict[str, Any]) -> Dict[str, Any]:
        """处理单条数据"""
        try:
            # 调用身份识别函数
            result = identity_auto(prompt, data_item.get("content", ""))
            
            # 合并原始数据和识别结果
            processed_item = {
                **data_item,  # 原始数据
                **result      # 识别结果
            }
            
            return processed_item
        except Exception as e:
            logger.error(f"Error processing item: {e}")
            # 返回原始数据，标记处理失败
            return {
                **data_item,
                "identity": "",
                "identity2": "",
                "log": f"处理失败: {str(e)}"
            }
    
    async def process_data_parallel(self, task_id: int, prompt: str, keywords: str, max_workers: int = 10) -> str:
        """并行处理数据"""
        try:
            # 更新任务状态为测试中
            self.db.update_task_status(task_id, "测试中")
            
            # 获取数据
            logger.info(f"Getting data for keywords: {keywords}")
            raw_data = self.data_get(keywords, 500)
            print(raw_data)
            
            # 并行处理数据
            logger.info(f"Starting parallel processing with {max_workers} workers")
            processed_data = []
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_item = {
                    executor.submit(self.process_single_item, prompt, item): item 
                    for item in raw_data
                }
                
                # 收集结果
                for future in concurrent.futures.as_completed(future_to_item):
                    try:
                        result = future.result()
                        print(result)
                        processed_data.append(result)
                    except Exception as e:
                        logger.error(f"Error in future result: {e}")
                        # 添加失败的原始数据
                        original_item = future_to_item[future]
                        processed_data.append({
                            **original_item,
                            "identity": "",
                            "identity2": "",
                            "log": f"处理异常: {str(e)}"
                        })
            
            # 生成Excel文件
            excel_path = self.generate_excel_report(task_id, processed_data)
            
            # 更新任务状态为完成
            self.db.update_task_status(task_id, "创建完成", excel_path)
            
            logger.info(f"Task {task_id} completed successfully. Excel saved to: {excel_path}")
            return excel_path
            
        except Exception as e:
            logger.error(f"Error in parallel processing: {e}")
            # 更新任务状态为失败
            self.db.update_task_status(task_id, "创建完成", f"处理失败: {str(e)}")
            raise
    
    def generate_excel_report(self, task_id: int, processed_data: List[Dict[str, Any]]) -> str:
        """生成Excel报告"""
        try:
            # 创建结果目录
            results_dir = "identity_auto_get/results"
            os.makedirs(results_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"identity_analysis_task_{task_id}_{timestamp}.xlsx"
            filepath = os.path.join(results_dir, filename)
            
            # 创建DataFrame
            df = pd.DataFrame(processed_data)
            
            # 重新排列列的顺序，把识别结果放在前面
            columns_order = []
            if 'identity' in df.columns:
                columns_order.extend(['identity', 'identity2', 'log'])
            
            # 添加其他列
            other_columns = [col for col in df.columns if col not in columns_order]
            columns_order.extend(other_columns)
            
            df = df[columns_order]
            
            # 保存到Excel
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='身份识别结果', index=False)
                
                # 添加统计信息
                stats_data = self.generate_statistics(processed_data)
                stats_df = pd.DataFrame(list(stats_data.items()), columns=['统计项', '数值'])
                stats_df.to_excel(writer, sheet_name='统计信息', index=False)
            
            logger.info(f"Excel report generated: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating Excel report: {e}")
            raise
    
    def generate_statistics(self, processed_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成统计信息"""
        total_count = len(processed_data)
        
        # 统计身份识别结果
        identity_counts = {}
        identity2_counts = {}
        successful_count = 0
        
        for item in processed_data:
            identity = item.get('identity', '')
            identity2 = item.get('identity2', '')
            
            if identity:
                successful_count += 1
                identity_counts[identity] = identity_counts.get(identity, 0) + 1
            
            if identity2:
                identity2_counts[identity2] = identity2_counts.get(identity2, 0) + 1
        
        stats = {
            "总数据量": total_count,
            "成功识别数量": successful_count,
            "识别成功率": f"{(successful_count/total_count*100):.2f}%" if total_count > 0 else "0%",
            "主要身份类别": str(identity_counts),
            "具体身份分布": str(identity2_counts)
        }
        
        return stats

if __name__ == "__main__":
    # 测试数据处理
    processor = DataProcessor()
    
    # 模拟处理
    test_data = processor.data_get("网约车")
    print(f"Retrieved {len(test_data)} test records")
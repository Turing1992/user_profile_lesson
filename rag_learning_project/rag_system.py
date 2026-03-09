#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RAG系统核心模块 - 整合所有组件
这是RAG系统的主要协调器，整合文档处理、向量检索和生成功能
"""

import os
import time
from typing import List, Dict, Optional
from document_processor import DocumentProcessor
from vector_store import VectorStore
from llm_client import LLMClient

class RAGSystem:
    """
    RAG系统 - 检索增强生成系统
    
    这是一个完整的RAG实现，展示了RAG的核心工作流程：
    1. 文档摄入和处理
    2. 向量化和索引
    3. 查询检索
    4. 上下文增强生成
    """
    
    def __init__(self, 
                 chunk_size: int = 500,
                 chunk_overlap: int = 50,
                 vector_model: str = "all-MiniLM-L6-v2",
                 llm_model: str = "gpt-3.5-turbo",
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None):
        """
        初始化RAG系统
        
        Args:
            chunk_size: 文档分块大小
            chunk_overlap: 分块重叠大小
            vector_model: 向量化模型
            llm_model: 生成模型
            api_key: LLM API密钥
            base_url: LLM API基础URL
        """
        print("🚀 初始化RAG系统...")
        
        # 初始化各个组件
        self.document_processor = DocumentProcessor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        self.vector_store = VectorStore(
            model_name=vector_model,
            index_path="vector_db"
        )
        
        self.llm_client = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=llm_model
        )
        
        # 系统配置
        self.config = {
            'chunk_size': chunk_size,
            'chunk_overlap': chunk_overlap,
            'vector_model': vector_model,
            'llm_model': llm_model,
            'initialized_at': time.time()
        }
        
        print("✅ RAG系统初始化完成！")
        self._print_system_info()
    
    def add_documents(self, file_paths: List[str]) -> Dict:
        """
        添加文档到RAG系统
        
        Args:
            file_paths: 文档文件路径列表
            
        Returns:
            Dict: 处理结果统计
        """
        print(f"\n📚 开始添加 {len(file_paths)} 个文档到RAG系统...")
        
        total_chunks = 0
        processed_files = []
        failed_files = []
        
        for file_path in file_paths:
            try:
                print(f"\n处理文件: {os.path.basename(file_path)}")
                
                # 1. 文档处理和分块
                chunks = self.document_processor.process_file(file_path)
                
                # 2. 向量化和存储
                self.vector_store.add_documents(chunks)
                
                total_chunks += len(chunks)
                processed_files.append({
                    'file': os.path.basename(file_path),
                    'chunks': len(chunks)
                })
                
            except Exception as e:
                print(f"❌ 处理文件失败 {file_path}: {e}")
                failed_files.append({
                    'file': os.path.basename(file_path),
                    'error': str(e)
                })
        
        result = {
            'total_files': len(file_paths),
            'processed_files': len(processed_files),
            'failed_files': len(failed_files),
            'total_chunks': total_chunks,
            'processed_details': processed_files,
            'failed_details': failed_files
        }
        
        print(f"\n📊 文档添加完成:")
        print(f"   - 成功处理: {result['processed_files']}/{result['total_files']} 个文件")
        print(f"   - 生成文本块: {result['total_chunks']} 个")
        print(f"   - 失败文件: {result['failed_files']} 个")
        
        return result
    
    def query(self, 
              question: str, 
              top_k: int = 5,
              return_sources: bool = True) -> Dict:
        """
        RAG查询 - 系统的核心功能
        
        Args:
            question: 用户问题
            top_k: 检索文档数量
            return_sources: 是否返回源文档信息
            
        Returns:
            Dict: 包含答案和相关信息的完整结果
        """
        print(f"\n🔍 RAG查询开始...")
        print(f"   问题: {question}")
        
        start_time = time.time()
        
        try:
            # 步骤1: 向量检索
            print(f"\n📖 步骤1: 检索相关文档 (top_k={top_k})")
            retrieved_docs = self.vector_store.search(question, top_k=top_k)
            
            if not retrieved_docs:
                return {
                    'question': question,
                    'answer': '抱歉，我没有找到相关的文档来回答您的问题。请确保已经添加了相关文档。',
                    'sources': [],
                    'retrieval_time': time.time() - start_time,
                    'generation_time': 0,
                    'total_time': time.time() - start_time
                }
            
            retrieval_time = time.time() - start_time
            
            # 步骤2: 生成回答
            print(f"\n🤖 步骤2: 基于上下文生成回答")
            generation_start = time.time()
            
            generation_result = self.llm_client.generate_answer(
                question=question,
                context_docs=retrieved_docs
            )
            
            generation_time = time.time() - generation_start
            total_time = time.time() - start_time
            
            # 构建完整结果
            result = {
                'question': question,
                'answer': generation_result['answer'],
                'sources': self._format_sources(retrieved_docs) if return_sources else [],
                'retrieval_time': retrieval_time,
                'generation_time': generation_time,
                'total_time': total_time,
                'retrieved_docs_count': len(retrieved_docs),
                'model_info': {
                    'vector_model': self.vector_store.model_name,
                    'llm_model': self.llm_client.model
                }
            }
            
            print(f"\n✅ RAG查询完成!")
            print(f"   - 检索时间: {retrieval_time:.2f}s")
            print(f"   - 生成时间: {generation_time:.2f}s")
            print(f"   - 总时间: {total_time:.2f}s")
            print(f"   - 检索文档: {len(retrieved_docs)} 个")
            
            return result
            
        except Exception as e:
            print(f"❌ RAG查询失败: {e}")
            return {
                'question': question,
                'answer': f'查询过程中出现错误: {str(e)}',
                'sources': [],
                'error': str(e),
                'total_time': time.time() - start_time
            }
    
    def get_system_stats(self) -> Dict:
        """获取系统统计信息"""
        vector_stats = self.vector_store.get_stats()
        
        return {
            'system_config': self.config,
            'vector_store_stats': vector_stats,
            'total_documents': vector_stats.get('total_documents', 0),
            'vector_dimension': vector_stats.get('vector_dimension', 0),
            'status': 'ready' if vector_stats.get('total_documents', 0) > 0 else 'empty'
        }
    
    def clear_knowledge_base(self) -> None:
        """清空知识库"""
        print("🗑️ 清空知识库...")
        self.vector_store.clear_index()
        print("✅ 知识库已清空")
    
    def _format_sources(self, retrieved_docs: List[Dict]) -> List[Dict]:
        """格式化源文档信息"""
        sources = []
        for doc in retrieved_docs:
            source = {
                'source_file': doc['metadata']['source'],
                'chunk_id': doc['metadata']['chunk_id'],
                'similarity_score': doc['score'],
                'text_preview': doc['text'][:200] + '...' if len(doc['text']) > 200 else doc['text']
            }
            sources.append(source)
        return sources
    
    def _print_system_info(self):
        """打印系统信息"""
        print(f"\n📋 RAG系统配置:")
        print(f"   - 文档分块大小: {self.config['chunk_size']} 字符")
        print(f"   - 分块重叠: {self.config['chunk_overlap']} 字符")
        print(f"   - 向量模型: {self.config['vector_model']}")
        print(f"   - 生成模型: {self.config['llm_model']}")
        
        stats = self.get_system_stats()
        print(f"   - 当前文档数: {stats['total_documents']}")
        print(f"   - 系统状态: {stats['status']}")

# 使用示例和测试
if __name__ == "__main__":
    # 创建RAG系统实例
    rag = RAGSystem(
        chunk_size=300,
        chunk_overlap=30,
        vector_model="all-MiniLM-L6-v2"
        # 注意：这里没有配置API密钥，将使用模拟模式
    )
    
    # 创建测试文档
    os.makedirs('test_documents', exist_ok=True)
    
    test_content = """
    人工智能简介
    
    人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
    
    机器学习是人工智能的一个重要分支。机器学习算法通过分析大量数据来识别模式，并使用这些模式来做出预测或决策，而无需明确编程。
    
    深度学习是机器学习的一个子集，它使用人工神经网络来模拟人脑的工作方式。深度学习在图像识别、自然语言处理和语音识别等领域取得了显著成果。
    
    自然语言处理（NLP）是人工智能的另一个重要分支，它致力于让计算机理解、解释和生成人类语言。NLP技术被广泛应用于搜索引擎、机器翻译、聊天机器人等领域。
    """
    
    with open('test_documents/ai_knowledge.txt', 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    # 添加文档
    result = rag.add_documents(['test_documents/ai_knowledge.txt'])
    print(f"\n添加文档结果: {result}")
    
    # 测试查询
    questions = [
        "什么是人工智能？",
        "机器学习和深度学习有什么区别？",
        "自然语言处理有哪些应用？"
    ]
    
    for question in questions:
        print(f"\n{'='*60}")
        result = rag.query(question, top_k=3)
        
        print(f"问题: {result['question']}")
        print(f"回答: {result['answer']}")
        print(f"检索时间: {result['retrieval_time']:.2f}s")
        print(f"生成时间: {result['generation_time']:.2f}s")
        
        if result.get('sources'):
            print(f"\n参考来源:")
            for i, source in enumerate(result['sources']):
                print(f"  {i+1}. {source['source_file']} (相似度: {source['similarity_score']:.3f})")
    
    # 显示系统统计
    stats = rag.get_system_stats()
    print(f"\n📊 系统统计:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
向量存储模块 - RAG系统的检索核心
负责文本向量化、存储和相似度检索
"""

import os
import json
import numpy as np
import faiss
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer
import pickle

class VectorStore:
    """
    向量存储器 - RAG系统的检索引擎
    
    主要功能：
    1. 文本向量化（使用预训练模型）
    2. 向量索引构建（FAISS）
    3. 相似度检索
    4. 向量数据持久化
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", index_path: str = "vector_db"):
        """
        初始化向量存储器
        
        Args:
            model_name: 向量化模型名称
            index_path: 向量索引存储路径
        """
        self.model_name = model_name
        self.index_path = index_path
        self.index = None
        self.documents = []  # 存储原始文档
        self.metadata = []   # 存储元数据
        
        # 创建存储目录
        os.makedirs(index_path, exist_ok=True)
        
        print(f"🔧 初始化向量存储器...")
        
        # 加载向量化模型
        try:
            self.encoder = SentenceTransformer(model_name)
            print(f"✅ 向量化模型加载成功: {model_name}")
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            # 使用中文优化模型作为备选
            try:
                self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
                print(f"✅ 使用备选模型: paraphrase-multilingual-MiniLM-L12-v2")
            except:
                raise Exception("无法加载任何向量化模型")
        
        # 尝试加载已有索引
        self._load_index()
        
        print(f"📊 当前索引状态: {len(self.documents)} 个文档")
    
    def add_documents(self, document_chunks: List[Dict]) -> None:
        """
        添加文档到向量存储
        
        Args:
            document_chunks: 文档块列表
        """
        if not document_chunks:
            return
        
        print(f"\n🔄 开始向量化 {len(document_chunks)} 个文档块...")
        
        # 提取文本
        texts = [chunk['text'] for chunk in document_chunks]
        
        # 批量向量化
        try:
            vectors = self.encoder.encode(texts, show_progress_bar=True)
            print(f"✅ 向量化完成，向量维度: {vectors.shape[1]}")
        except Exception as e:
            print(f"❌ 向量化失败: {e}")
            raise
        
        # 构建或更新FAISS索引
        if self.index is None:
            # 创建新索引
            dimension = vectors.shape[1]
            self.index = faiss.IndexFlatIP(dimension)  # 使用内积相似度
            print(f"🆕 创建新的FAISS索引，维度: {dimension}")
        
        # 标准化向量（用于余弦相似度）
        faiss.normalize_L2(vectors)
        
        # 添加向量到索引
        self.index.add(vectors.astype('float32'))
        
        # 存储文档和元数据
        self.documents.extend(texts)
        self.metadata.extend([chunk['metadata'] for chunk in document_chunks])
        
        print(f"✅ 成功添加 {len(document_chunks)} 个文档块到向量存储")
        print(f"📊 总文档数: {len(self.documents)}")
        
        # 保存索引
        self._save_index()
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        相似度检索
        
        Args:
            query: 查询文本
            top_k: 返回最相似的k个结果
            
        Returns:
            List[Dict]: 检索结果列表
        """
        if self.index is None or len(self.documents) == 0:
            print("⚠️ 向量存储为空，请先添加文档")
            return []
        
        print(f"\n🔍 开始检索: '{query[:50]}...'")
        
        # 查询向量化
        query_vector = self.encoder.encode([query])
        faiss.normalize_L2(query_vector)
        
        # 执行检索
        scores, indices = self.index.search(query_vector.astype('float32'), top_k)
        
        # 构建结果
        results = []
        for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx < len(self.documents):  # 确保索引有效
                result = {
                    'rank': i + 1,
                    'text': self.documents[idx],
                    'score': float(score),
                    'metadata': self.metadata[idx]
                }
                results.append(result)
        
        print(f"✅ 检索完成，返回 {len(results)} 个结果")
        for i, result in enumerate(results):
            print(f"   {i+1}. 相似度: {result['score']:.4f} | 来源: {result['metadata']['source']}")
        
        return results
    
    def get_stats(self) -> Dict:
        """获取向量存储统计信息"""
        return {
            'total_documents': len(self.documents),
            'model_name': self.model_name,
            'index_type': type(self.index).__name__ if self.index else None,
            'vector_dimension': self.index.d if self.index else None
        }
    
    def _save_index(self) -> None:
        """保存向量索引和元数据"""
        try:
            # 保存FAISS索引
            if self.index:
                index_file = os.path.join(self.index_path, "faiss_index.bin")
                faiss.write_index(self.index, index_file)
            
            # 保存文档和元数据
            data_file = os.path.join(self.index_path, "documents.pkl")
            with open(data_file, 'wb') as f:
                pickle.dump({
                    'documents': self.documents,
                    'metadata': self.metadata,
                    'model_name': self.model_name
                }, f)
            
            print(f"💾 向量索引已保存到: {self.index_path}")
            
        except Exception as e:
            print(f"❌ 保存索引失败: {e}")
    
    def _load_index(self) -> None:
        """加载已有的向量索引"""
        try:
            index_file = os.path.join(self.index_path, "faiss_index.bin")
            data_file = os.path.join(self.index_path, "documents.pkl")
            
            if os.path.exists(index_file) and os.path.exists(data_file):
                # 加载FAISS索引
                self.index = faiss.read_index(index_file)
                
                # 加载文档数据
                with open(data_file, 'rb') as f:
                    data = pickle.load(f)
                    self.documents = data['documents']
                    self.metadata = data['metadata']
                
                print(f"📂 成功加载已有索引: {len(self.documents)} 个文档")
            else:
                print(f"📂 未找到已有索引，将创建新索引")
                
        except Exception as e:
            print(f"⚠️ 加载索引失败: {e}，将创建新索引")
            self.index = None
            self.documents = []
            self.metadata = []
    
    def clear_index(self) -> None:
        """清空向量索引"""
        self.index = None
        self.documents = []
        self.metadata = []
        
        # 删除存储文件
        try:
            index_file = os.path.join(self.index_path, "faiss_index.bin")
            data_file = os.path.join(self.index_path, "documents.pkl")
            
            if os.path.exists(index_file):
                os.remove(index_file)
            if os.path.exists(data_file):
                os.remove(data_file)
                
            print("🗑️ 向量索引已清空")
        except Exception as e:
            print(f"⚠️ 清空索引时出错: {e}")

# 使用示例和测试
if __name__ == "__main__":
    # 测试向量存储
    vector_store = VectorStore()
    
    # 创建测试文档
    test_documents = [
        {
            'text': '人工智能是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统。',
            'metadata': {'source': 'ai_intro.txt', 'chunk_id': 0}
        },
        {
            'text': '机器学习是人工智能的一个子领域，它使计算机能够在没有明确编程的情况下学习和改进。',
            'metadata': {'source': 'ai_intro.txt', 'chunk_id': 1}
        },
        {
            'text': '深度学习使用人工神经网络来模拟人脑的工作方式，在图像识别和自然语言处理方面表现出色。',
            'metadata': {'source': 'ai_intro.txt', 'chunk_id': 2}
        }
    ]
    
    # 添加文档
    vector_store.add_documents(test_documents)
    
    # 测试检索
    query = "什么是机器学习？"
    results = vector_store.search(query, top_k=2)
    
    print(f"\n📋 检索结果:")
    for result in results:
        print(f"排名: {result['rank']}")
        print(f"相似度: {result['score']:.4f}")
        print(f"内容: {result['text']}")
        print(f"来源: {result['metadata']['source']}")
        print("-" * 50)
    
    # 显示统计信息
    stats = vector_store.get_stats()
    print(f"\n📊 向量存储统计:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
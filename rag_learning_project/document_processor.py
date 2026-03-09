#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
文档处理模块 - RAG系统的第一步
负责将各种格式的文档转换为可处理的文本块
"""

import os
import re
import jieba
from typing import List, Dict
import PyPDF2
import docx
from io import BytesIO

class DocumentProcessor:
    """
    文档处理器 - RAG系统的数据预处理核心
    
    主要功能：
    1. 支持多种文档格式（PDF、Word、TXT）
    2. 智能文本分块（避免语义割裂）
    3. 文本清洗和标准化
    4. 元数据提取和管理
    """
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        """
        初始化文档处理器
        
        Args:
            chunk_size: 文本块大小（字符数）
            chunk_overlap: 文本块重叠大小（避免语义割裂）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # 初始化中文分词器
        jieba.initialize()
        
        print(f"📄 文档处理器初始化完成")
        print(f"   - 文本块大小: {chunk_size} 字符")
        print(f"   - 重叠大小: {chunk_overlap} 字符")
    
    def process_file(self, file_path: str) -> List[Dict]:
        """
        处理单个文件，返回文本块列表
        
        Args:
            file_path: 文件路径
            
        Returns:
            List[Dict]: 文本块列表，每个块包含text和metadata
        """
        print(f"\n🔄 开始处理文件: {os.path.basename(file_path)}")
        
        # 根据文件扩展名选择处理方法
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.pdf':
            text = self._extract_pdf_text(file_path)
        elif file_ext == '.docx':
            text = self._extract_docx_text(file_path)
        elif file_ext == '.txt':
            text = self._extract_txt_text(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {file_ext}")
        
        # 清洗文本
        cleaned_text = self._clean_text(text)
        
        # 分块处理
        chunks = self._split_text(cleaned_text)
        
        # 构建文档块
        document_chunks = []
        for i, chunk in enumerate(chunks):
            document_chunks.append({
                'text': chunk,
                'metadata': {
                    'source': os.path.basename(file_path),
                    'chunk_id': i,
                    'total_chunks': len(chunks),
                    'file_type': file_ext,
                    'char_count': len(chunk)
                }
            })
        
        print(f"✅ 文件处理完成: 生成 {len(document_chunks)} 个文本块")
        return document_chunks
    
    def _extract_pdf_text(self, file_path: str) -> str:
        """从PDF文件提取文本"""
        text = ""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            print(f"❌ PDF文件读取失败: {e}")
            raise
        return text
    
    def _extract_docx_text(self, file_path: str) -> str:
        """从Word文档提取文本"""
        text = ""
        try:
            doc = docx.Document(file_path)
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
        except Exception as e:
            print(f"❌ Word文档读取失败: {e}")
            raise
        return text
    
    def _extract_txt_text(self, file_path: str) -> str:
        """从文本文件提取文本"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
        except UnicodeDecodeError:
            # 尝试其他编码
            with open(file_path, 'r', encoding='gbk') as file:
                text = file.read()
        except Exception as e:
            print(f"❌ 文本文件读取失败: {e}")
            raise
        return text
    
    def _clean_text(self, text: str) -> str:
        """
        清洗文本 - 移除多余空白、特殊字符等
        """
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 移除特殊字符（保留中英文、数字、基本标点）
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\.,!?;:()（）。，！？；：]', '', text)
        
        # 移除过短的行
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if len(line.strip()) > 10]
        
        return '\n'.join(cleaned_lines)
    
    def _split_text(self, text: str) -> List[str]:
        """
        智能文本分块 - 基于语义边界分割
        """
        # 首先按段落分割
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # 如果当前块加上新段落不超过限制，则添加
            if len(current_chunk) + len(paragraph) <= self.chunk_size:
                current_chunk += paragraph + "\n"
            else:
                # 保存当前块
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # 如果单个段落就超过限制，需要进一步分割
                if len(paragraph) > self.chunk_size:
                    sub_chunks = self._split_long_paragraph(paragraph)
                    chunks.extend(sub_chunks[:-1])  # 除了最后一个
                    current_chunk = sub_chunks[-1] + "\n"
                else:
                    current_chunk = paragraph + "\n"
        
        # 添加最后一个块
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # 处理重叠
        if self.chunk_overlap > 0:
            chunks = self._add_overlap(chunks)
        
        return chunks
    
    def _split_long_paragraph(self, paragraph: str) -> List[str]:
        """分割过长的段落"""
        # 按句子分割
        sentences = re.split(r'[。！？.!?]', paragraph)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if not sentence.strip():
                continue
                
            sentence = sentence.strip() + "。"
            
            if len(current_chunk) + len(sentence) <= self.chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _add_overlap(self, chunks: List[str]) -> List[str]:
        """为文本块添加重叠部分"""
        if len(chunks) <= 1:
            return chunks
        
        overlapped_chunks = [chunks[0]]
        
        for i in range(1, len(chunks)):
            # 从前一个块的末尾取重叠部分
            prev_chunk = chunks[i-1]
            current_chunk = chunks[i]
            
            # 取前一个块的最后overlap_size个字符
            overlap_text = prev_chunk[-self.chunk_overlap:] if len(prev_chunk) > self.chunk_overlap else prev_chunk
            
            # 合并到当前块
            overlapped_chunk = overlap_text + " " + current_chunk
            overlapped_chunks.append(overlapped_chunk)
        
        return overlapped_chunks

# 使用示例和测试
if __name__ == "__main__":
    # 创建测试文档
    test_content = """
    人工智能（Artificial Intelligence，AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。

    机器学习是人工智能的一个重要分支，它使计算机能够在没有明确编程的情况下学习。机器学习算法通过分析数据来识别模式，并使用这些模式来做出预测或决策。

    深度学习是机器学习的一个子集，它使用人工神经网络来模拟人脑的工作方式。深度学习在图像识别、自然语言处理和语音识别等领域取得了显著成果。

    自然语言处理（NLP）是人工智能的另一个重要分支，它致力于让计算机理解、解释和生成人类语言。NLP技术被广泛应用于搜索引擎、机器翻译、聊天机器人等领域。
    """
    
    # 创建测试文件
    os.makedirs('test_documents', exist_ok=True)
    with open('test_documents/ai_intro.txt', 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    # 测试文档处理器
    processor = DocumentProcessor(chunk_size=200, chunk_overlap=30)
    chunks = processor.process_file('test_documents/ai_intro.txt')
    
    print(f"\n📊 处理结果统计:")
    for i, chunk in enumerate(chunks):
        print(f"块 {i+1}: {len(chunk['text'])} 字符")
        print(f"内容预览: {chunk['text'][:50]}...")
        print(f"元数据: {chunk['metadata']}")
        print("-" * 50)
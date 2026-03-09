#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LLM客户端模块 - RAG系统的生成核心
负责与大语言模型交互，生成基于上下文的回答
"""

import openai
import json
from typing import List, Dict, Optional
import time

class LLMClient:
    """
    大语言模型客户端 - RAG系统的生成引擎
    
    主要功能：
    1. 构建RAG提示模板
    2. 调用LLM生成回答
    3. 支持多种LLM提供商
    4. 错误处理和重试机制
    """
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model: str = "gpt-3.5-turbo"):
        """
        初始化LLM客户端
        
        Args:
            api_key: API密钥
            base_url: API基础URL（用于自定义端点）
            model: 模型名称
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        
        # 配置OpenAI客户端
        if api_key:
            openai.api_key = api_key
        if base_url:
            openai.base_url = base_url
        
        # RAG提示模板
        self.rag_prompt_template = """你是一个智能助手，请基于提供的上下文信息来回答用户的问题。

上下文信息：
{context}

用户问题：{question}

请根据上下文信息回答问题，要求：
1. 如果上下文中包含相关信息，请基于这些信息进行回答
2. 如果上下文中没有足够信息，请明确说明
3. 回答要准确、简洁、有条理
4. 可以适当引用上下文中的具体内容

回答："""
        
        print(f"🤖 LLM客户端初始化完成")
        print(f"   - 模型: {model}")
        print(f"   - API配置: {'已配置' if api_key else '未配置（将使用模拟模式）'}")
    
    def generate_answer(self, 
                       question: str, 
                       context_docs: List[Dict],
                       max_context_length: int = 2000) -> Dict:
        """
        基于检索到的文档生成回答
        
        Args:
            question: 用户问题
            context_docs: 检索到的相关文档
            max_context_length: 最大上下文长度
            
        Returns:
            Dict: 包含回答和元信息的字典
        """
        print(f"\n🤖 开始生成回答...")
        print(f"   - 问题: {question}")
        print(f"   - 上下文文档数: {len(context_docs)}")
        
        # 构建上下文
        context = self._build_context(context_docs, max_context_length)
        
        # 构建完整提示
        prompt = self.rag_prompt_template.format(
            context=context,
            question=question
        )
        
        print(f"   - 上下文长度: {len(context)} 字符")
        
        # 生成回答
        try:
            if self.api_key:
                # 使用真实API
                answer = self._call_openai_api(prompt)
            else:
                # 使用模拟回答
                answer = self._generate_mock_answer(question, context_docs)
            
            result = {
                'answer': answer,
                'question': question,
                'context_docs': context_docs,
                'context_length': len(context),
                'model': self.model,
                'timestamp': time.time()
            }
            
            print(f"✅ 回答生成完成")
            return result
            
        except Exception as e:
            print(f"❌ 生成回答失败: {e}")
            return {
                'answer': f"抱歉，生成回答时出现错误: {str(e)}",
                'question': question,
                'context_docs': context_docs,
                'error': str(e)
            }
    
    def _build_context(self, context_docs: List[Dict], max_length: int) -> str:
        """
        构建上下文字符串
        """
        context_parts = []
        current_length = 0
        
        for i, doc in enumerate(context_docs):
            doc_text = f"文档{i+1}（来源：{doc['metadata']['source']}）：\n{doc['text']}\n"
            
            if current_length + len(doc_text) > max_length:
                break
            
            context_parts.append(doc_text)
            current_length += len(doc_text)
        
        return "\n".join(context_parts)
    
    def _call_openai_api(self, prompt: str) -> str:
        """
        调用OpenAI API
        """
        try:
            response = openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            raise Exception(f"OpenAI API调用失败: {e}")
    
    def _generate_mock_answer(self, question: str, context_docs: List[Dict]) -> str:
        """
        生成模拟回答（当没有配置API时使用）
        """
        if not context_docs:
            return "抱歉，我没有找到相关的信息来回答您的问题。"
        
        # 简单的基于关键词匹配的模拟回答
        best_doc = context_docs[0]  # 取相似度最高的文档
        
        mock_answer = f"""基于检索到的相关信息，我来回答您的问题：

{best_doc['text']}

这个回答基于文档"{best_doc['metadata']['source']}"中的内容。

注意：这是一个模拟回答。要获得更智能的回答，请配置真实的LLM API密钥。"""
        
        return mock_answer
    
    def evaluate_answer_quality(self, question: str, answer: str, context_docs: List[Dict]) -> Dict:
        """
        评估回答质量（简单版本）
        """
        # 简单的质量评估指标
        metrics = {
            'answer_length': len(answer),
            'context_usage': self._calculate_context_usage(answer, context_docs),
            'relevance_score': self._calculate_relevance(question, answer),
            'completeness_score': min(len(answer) / 200, 1.0)  # 基于长度的完整性
        }
        
        return metrics
    
    def _calculate_context_usage(self, answer: str, context_docs: List[Dict]) -> float:
        """计算上下文使用率"""
        if not context_docs:
            return 0.0
        
        # 简单统计：检查答案中是否包含上下文的关键词
        context_words = set()
        for doc in context_docs:
            words = doc['text'].split()
            context_words.update(words[:20])  # 取前20个词
        
        answer_words = set(answer.split())
        overlap = len(context_words.intersection(answer_words))
        
        return min(overlap / len(context_words) if context_words else 0, 1.0)
    
    def _calculate_relevance(self, question: str, answer: str) -> float:
        """计算相关性得分"""
        # 简单的关键词重叠计算
        question_words = set(question.split())
        answer_words = set(answer.split())
        
        overlap = len(question_words.intersection(answer_words))
        return min(overlap / len(question_words) if question_words else 0, 1.0)

# 使用示例和测试
if __name__ == "__main__":
    # 测试LLM客户端
    llm_client = LLMClient()
    
    # 模拟检索结果
    mock_context_docs = [
        {
            'text': '人工智能（AI）是计算机科学的一个分支，它致力于创建能够执行通常需要人类智能的任务的系统。AI系统可以学习、推理、感知和做出决策。',
            'metadata': {'source': 'ai_intro.txt', 'chunk_id': 0},
            'score': 0.95
        },
        {
            'text': '机器学习是AI的一个重要子领域，它使计算机能够在没有明确编程的情况下从数据中学习和改进性能。',
            'metadata': {'source': 'ml_basics.txt', 'chunk_id': 1},
            'score': 0.87
        }
    ]
    
    # 测试问题
    question = "什么是人工智能？"
    
    # 生成回答
    result = llm_client.generate_answer(question, mock_context_docs)
    
    print(f"\n📋 生成结果:")
    print(f"问题: {result['question']}")
    print(f"回答: {result['answer']}")
    print(f"上下文长度: {result.get('context_length', 0)}")
    
    # 评估回答质量
    quality_metrics = llm_client.evaluate_answer_quality(
        question, result['answer'], mock_context_docs
    )
    
    print(f"\n📊 回答质量评估:")
    for metric, value in quality_metrics.items():
        print(f"   {metric}: {value:.3f}")
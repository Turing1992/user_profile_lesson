"""
三元组提取服务
"""
import json
import re
import logging
from typing import List
from openai import OpenAI

from intent_recognition_system.models.triplet import Triplet, EventAnalysis
from intent_recognition_system.config.config import LLM_CONFIG, TRIPLET_CONFIG

logger = logging.getLogger(__name__)


class TripletExtractor:
    """三元组提取器"""
    
    def __init__(self):
        self.client = OpenAI(api_key=LLM_CONFIG["openai"]["api_key"])
        self.model = LLM_CONFIG["openai"]["model"]
        
    def extract_triplets(self, event_description: str) -> EventAnalysis:
        """从事件描述中提取三元组"""
        try:
            prompt = self._build_extraction_prompt(event_description)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的信息提取专家，擅长从文本中提取结构化的三元组信息。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=LLM_CONFIG["openai"]["temperature"],
                max_tokens=LLM_CONFIG["openai"]["max_tokens"]
            )
            
            result_text = response.choices[0].message.content
            triplets = self._parse_triplets_response(result_text)
            
            analysis = EventAnalysis(
                event_description=event_description,
                triplets=triplets
            )
            analysis.all_keywords = analysis.extract_all_keywords()
            
            logger.info(f"提取到 {len(triplets)} 个三元组，共 {len(analysis.all_keywords)} 个关键词")
            return analysis
            
        except Exception as e:
            logger.error(f"三元组提取失败: {e}")
            return EventAnalysis(event_description=event_description)
    
    def _build_extraction_prompt(self, event_description: str) -> str:
        """构建提取提示词"""
        return f"""
请从以下事件描述中提取三元组信息，每个三元组包含主体(subject)、谓词(predicate)、客体(object)。

事件描述：{event_description}

要求：
1. 提取最多{TRIPLET_CONFIG['max_triplets']}个最重要的三元组
2. 每个三元组还需要提供3-5个相关关键词
3. 给出每个三元组的置信度(0-1之间)
4. 以JSON格式返回结果

返回格式示例：
{{
    "triplets": [
        {{
            "subject": "用户",
            "predicate": "评论",
            "object": "疫情政策",
            "confidence": 0.9,
            "keywords": ["网民", "发声", "防疫", "措施", "讨论"]
        }}
    ]
}}
"""
    
    def _parse_triplets_response(self, response_text: str) -> List[Triplet]:
        """解析LLM返回的三元组结果"""
        try:
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                data = json.loads(json_text)
                
                triplets = []
                for item in data.get("triplets", []):
                    triplet = Triplet(
                        subject=item.get("subject", ""),
                        predicate=item.get("predicate", ""),
                        object=item.get("object", ""),
                        confidence=item.get("confidence", 1.0),
                        keywords=item.get("keywords", [])
                    )
                    
                    # 过滤低置信度的三元组
                    if triplet.confidence >= TRIPLET_CONFIG["min_confidence"]:
                        triplets.append(triplet)
                
                return triplets
                
        except Exception as e:
            logger.error(f"解析三元组响应失败: {e}")
            
        return []
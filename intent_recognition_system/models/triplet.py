"""
三元组数据模型
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class Triplet(BaseModel):
    """三元组模型 (主体-谓词-客体)"""
    subject: str = Field(..., description="主体")
    predicate: str = Field(..., description="谓词/关系")
    object: str = Field(..., description="客体")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    keywords: List[str] = Field(default_factory=list, description="提取的关键词")
    
    def to_keywords(self) -> List[str]:
        """转换为关键词列表"""
        base_keywords = [self.subject, self.predicate, self.object]
        return base_keywords + self.keywords


class EventAnalysis(BaseModel):
    """事件分析结果"""
    event_description: str = Field(..., description="事件描述")
    triplets: List[Triplet] = Field(default_factory=list, description="提取的三元组")
    all_keywords: List[str] = Field(default_factory=list, description="所有关键词")
    
    def extract_all_keywords(self) -> List[str]:
        """提取所有关键词"""
        keywords = []
        for triplet in self.triplets:
            keywords.extend(triplet.to_keywords())
        # 去重并返回
        return list(set(keywords))


class AccountResult(BaseModel):
    """账号检索结果"""
    account_id: str = Field(..., description="账号ID")
    username: str = Field(..., description="用户名")
    platform: str = Field(..., description="平台")
    relevance_score: float = Field(default=0.0, description="相关性得分")
    matched_keywords: List[str] = Field(default_factory=list, description="匹配的关键词")
    comment_count: int = Field(default=0, description="相关评论数量")


class IntentResult(BaseModel):
    """意图识别结果"""
    event_analysis: EventAnalysis
    matched_accounts: List[AccountResult] = Field(default_factory=list)
    total_accounts: int = Field(default=0, description="匹配账号总数")
    processing_time: float = Field(default=0.0, description="处理时间(秒)")
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 4)
        }
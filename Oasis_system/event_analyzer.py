# -*- coding: utf-8 -*-
"""
事件分析器
从事件中抽取实体，匹配账号，推演画像
"""
import json
import re
from typing import Dict, List, Optional, Set
from llm_client import LLMClient
from profile_engine import ProfileEngine
from storage import ProfileStorage


class EventAnalyzer:
    """事件驱动的画像分析器"""
    
    def __init__(self):
        self.llm_client = LLMClient()
        self.profile_engine = ProfileEngine()
        self.storage = ProfileStorage()
    
    def analyze_event(self, event_data: Dict) -> Dict:
        """
        分析事件并推演涉事账号画像
        
        Args:
            event_data: 事件数据
                {
                    "event_id": "事件ID",
                    "event_type": "事件类型",
                    "event_description": "事件描述",
                    "related_content": ["相关内容1", "相关内容2"],
                    "timestamp": "时间戳"
                }
        
        Returns:
            分析结果
        """
        print(f"\n{'='*60}")
        print(f"开始分析事件: {event_data.get('event_id')}")
        print(f"{'='*60}\n")
        
        # 步骤1: 从事件中抽取实体
        print("步骤1: 抽取实体...")
        entities = self.extract_entities(event_data)
        print(f"  提取到 {len(entities.get('accounts', []))} 个账号实体")
        print(f"  提取到 {len(entities.get('keywords', []))} 个关键词")
        
        # 步骤2: 匹配账号画像库
        print("\n步骤2: 匹配账号画像库...")
        matched_profiles = self.match_profiles(entities)
        print(f"  匹配到 {len(matched_profiles)} 个账号")
        
        # 步骤3: 推演涉事账号画像
        print("\n步骤3: 推演涉事账号画像...")
        enriched_profiles = self.enrich_profiles(
            matched_profiles, 
            event_data, 
            entities
        )
        
        # 步骤4: 生成分析报告
        print("\n步骤4: 生成分析报告...")
        report = self.generate_report(
            event_data,
            entities,
            enriched_profiles
        )
        
        print(f"\n{'='*60}")
        print("事件分析完成")
        print(f"{'='*60}\n")
        
        return report
    
    def extract_entities(self, event_data: Dict) -> Dict:
        """
        从事件中抽取实体
        
        Returns:
            {
                "accounts": [账号ID列表],
                "keywords": [关键词列表],
                "topics": [话题列表],
                "locations": [地点列表]
            }
        """
        # 构建抽取 prompt
        prompt = self._build_extraction_prompt(event_data)
        
        # 调用 LLM 抽取
        result, _, _ = self.llm_client.call(prompt)
        
        if not result:
            # LLM 失败，使用规则抽取
            return self._rule_based_extraction(event_data)
        
        return result
    
    def _build_extraction_prompt(self, event_data: Dict) -> str:
        """构建实体抽取 prompt"""
        event_desc = event_data.get("event_description", "")
        related_content = event_data.get("related_content", [])
        
        content_text = "\n".join([f"- {c}" for c in related_content[:10]])
        
        prompt = f"""请从以下事件信息中抽取关键实体。

【事件描述】
{event_desc}

【相关内容】
{content_text}

请抽取以下实体：
1. 账号ID/用户名（如：@用户名、user_id等）
2. 关键词（事件相关的重要词汇）
3. 话题标签（如：#话题名）
4. 地点信息

返回JSON格式：
{{
    "accounts": ["账号1", "账号2"],
    "keywords": ["关键词1", "关键词2"],
    "topics": ["话题1", "话题2"],
    "locations": ["地点1", "地点2"]
}}
"""
        return prompt
    
    def _rule_based_extraction(self, event_data: Dict) -> Dict:
        """基于规则的实体抽取（LLM失败时的备选方案）"""
        text = event_data.get("event_description", "")
        related_content = event_data.get("related_content", [])
        
        all_text = text + " " + " ".join(related_content)
        
        entities = {
            "accounts": [],
            "keywords": [],
            "topics": [],
            "locations": []
        }
        
        # 抽取账号（@用户名 或 user_xxx）
        accounts = re.findall(r'@(\w+)|user[_-](\w+)', all_text)
        entities["accounts"] = [a[0] or a[1] for a in accounts if a[0] or a[1]]
        
        # 抽取话题（#话题）
        topics = re.findall(r'#(\w+)', all_text)
        entities["topics"] = topics
        
        # 简单的关键词抽取（高频词）
        words = re.findall(r'\w+', all_text)
        from collections import Counter
        word_freq = Counter(words)
        entities["keywords"] = [w for w, c in word_freq.most_common(10) if len(w) > 2]
        
        return entities
    
    def match_profiles(self, entities: Dict) -> List[Dict]:
        """
        在画像库中匹配账号
        
        Args:
            entities: 抽取的实体
        
        Returns:
            匹配到的账号画像列表
        """
        accounts = entities.get("accounts", [])
        matched = []
        
        for account_id in accounts:
            # 从数据库查询
            profile = self.storage.get_profile(account_id)
            
            if profile:
                matched.append({
                    "account_id": account_id,
                    "profile": profile,
                    "source": "database"
                })
            else:
                # 如果数据库没有，标记为需要新建
                matched.append({
                    "account_id": account_id,
                    "profile": None,
                    "source": "new"
                })
        
        return matched
    
    def enrich_profiles(self, matched_profiles: List[Dict], 
                       event_data: Dict, entities: Dict) -> List[Dict]:
        """
        推演和丰富账号画像
        
        Args:
            matched_profiles: 匹配到的账号
            event_data: 事件数据
            entities: 抽取的实体
        
        Returns:
            丰富后的画像列表
        """
        enriched = []
        
        for item in matched_profiles:
            account_id = item["account_id"]
            existing_profile = item["profile"]
            
            print(f"  处理账号: {account_id}")
            
            if existing_profile:
                # 已有画像，进行事件相关的深度推演
                enriched_profile = self._enrich_existing_profile(
                    existing_profile,
                    event_data,
                    entities
                )
            else:
                # 新账号，基于事件信息生成初始画像
                enriched_profile = self._create_profile_from_event(
                    account_id,
                    event_data,
                    entities
                )
            
            enriched.append(enriched_profile)
        
        return enriched
    
    def _enrich_existing_profile(self, profile: Dict, 
                                 event_data: Dict, entities: Dict) -> Dict:
        """丰富已有画像"""
        # 构建事件相关分析 prompt
        prompt = f"""基于以下信息，分析该账号在此事件中的角色和行为特征。

【账号画像】
账号ID: {profile.get('account_id')}
身份: {profile.get('identity')}
基础信息: {json.dumps(profile.get('basic_info', {}), ensure_ascii=False)}

【事件信息】
事件类型: {event_data.get('event_type')}
事件描述: {event_data.get('event_description')}
关键词: {', '.join(entities.get('keywords', []))}

请分析：
1. 该账号在事件中的角色（发起者/传播者/评论者/旁观者）
2. 该账号的立场和态度
3. 该账号的影响力评估
4. 该账号的风险等级

返回JSON格式：
{{
    "event_role": "角色",
    "stance": "立场",
    "attitude": "态度",
    "influence_level": "影响力等级",
    "risk_level": "风险等级",
    "analysis": "详细分析"
}}
"""
        
        result, _, _ = self.llm_client.call(prompt)
        
        # 合并到原有画像
        enriched = {
            "account_id": profile.get('account_id'),
            "basic_profile": profile,
            "event_analysis": result or {},
            "event_context": {
                "event_id": event_data.get('event_id'),
                "event_type": event_data.get('event_type'),
                "timestamp": event_data.get('timestamp')
            }
        }
        
        return enriched
    
    def _create_profile_from_event(self, account_id: str, 
                                   event_data: Dict, entities: Dict) -> Dict:
        """基于事件信息创建新画像"""
        # 从事件内容中推断账号特征
        prompt = f"""基于以下事件信息，推断账号 {account_id} 的基本特征。

【事件信息】
事件类型: {event_data.get('event_type')}
事件描述: {event_data.get('event_description')}
相关内容: {json.dumps(event_data.get('related_content', [])[:3], ensure_ascii=False)}

请推断该账号的：
1. 可能的身份/职业
2. 兴趣领域
3. 性格特征
4. 在事件中的角色

返回JSON格式：
{{
    "identity": "推断的身份",
    "interests": ["兴趣1", "兴趣2"],
    "personality": {{"type": "性格类型", "activity": "活跃度"}},
    "event_role": "在事件中的角色",
    "confidence": 0.7
}}
"""
        
        result, _, _ = self.llm_client.call(prompt)
        
        # 构建完整画像
        profile_data = {
            "account_id": account_id,
            "name": account_id,
            "identity": result.get("identity", "未知") if result else "未知",
            "description": f"从事件 {event_data.get('event_id')} 中识别"
        }
        
        # 使用画像推演引擎生成完整画像
        full_profile = self.profile_engine.generate_full_profile(profile_data)
        
        # 添加事件相关信息
        full_profile["event_analysis"] = result or {}
        full_profile["event_context"] = {
            "event_id": event_data.get('event_id'),
            "event_type": event_data.get('event_type'),
            "discovered_from_event": True
        }
        
        return full_profile
    
    def generate_report(self, event_data: Dict, entities: Dict, 
                       enriched_profiles: List[Dict]) -> Dict:
        """生成分析报告"""
        report = {
            "event_info": {
                "event_id": event_data.get("event_id"),
                "event_type": event_data.get("event_type"),
                "event_description": event_data.get("event_description"),
                "timestamp": event_data.get("timestamp")
            },
            "extracted_entities": entities,
            "account_analysis": {
                "total_accounts": len(enriched_profiles),
                "existing_accounts": sum(1 for p in enriched_profiles 
                                        if not p.get("event_context", {}).get("discovered_from_event")),
                "new_accounts": sum(1 for p in enriched_profiles 
                                   if p.get("event_context", {}).get("discovered_from_event"))
            },
            "profiles": enriched_profiles,
            "summary": self._generate_summary(enriched_profiles, event_data)
        }
        
        return report
    
    def _generate_summary(self, profiles: List[Dict], event_data: Dict) -> Dict:
        """生成摘要"""
        # 统计角色分布
        roles = {}
        risk_levels = {}
        
        for profile in profiles:
            event_analysis = profile.get("event_analysis", {})
            
            role = event_analysis.get("event_role", "未知")
            roles[role] = roles.get(role, 0) + 1
            
            risk = event_analysis.get("risk_level", "未知")
            risk_levels[risk] = risk_levels.get(risk, 0) + 1
        
        return {
            "role_distribution": roles,
            "risk_distribution": risk_levels,
            "high_risk_accounts": [
                p["account_id"] for p in profiles
                if p.get("event_analysis", {}).get("risk_level") in ["高", "high"]
            ]
        }
    
    def save_report(self, report: Dict, output_path: str = None):
        """保存分析报告"""
        if not output_path:
            event_id = report["event_info"]["event_id"]
            output_path = f"event_analysis_{event_id}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"分析报告已保存: {output_path}")
        
        # 同时保存到数据库
        for profile in report["profiles"]:
            if profile.get("status") == "success":
                self.storage.save_profile(profile)
        
        print(f"画像数据已保存到数据库")


def main():
    """测试函数"""
    # 示例事件
    event_data = {
        "event_id": "event_001",
        "event_type": "社会事件",
        "event_description": "某地发生火灾，多名网友发布现场视频",
        "related_content": [
            "@消防员小王 发布了现场救援视频",
            "@新闻记者李明 报道了事件经过",
            "user_12345 转发并评论：希望大家平安",
            "#火灾救援 话题下有大量讨论"
        ],
        "timestamp": "2025-03-06 10:00:00"
    }
    
    # 创建分析器
    analyzer = EventAnalyzer()
    
    # 分析事件
    report = analyzer.analyze_event(event_data)
    
    # 保存报告
    analyzer.save_report(report)
    
    # 打印摘要
    print("\n" + "="*60)
    print("分析摘要")
    print("="*60)
    print(f"事件ID: {report['event_info']['event_id']}")
    print(f"涉及账号数: {report['account_analysis']['total_accounts']}")
    print(f"已有画像: {report['account_analysis']['existing_accounts']}")
    print(f"新发现账号: {report['account_analysis']['new_accounts']}")
    print(f"\n角色分布: {report['summary']['role_distribution']}")
    print(f"风险分布: {report['summary']['risk_distribution']}")
    print(f"高风险账号: {report['summary']['high_risk_accounts']}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
事件分析器测试版本（使用 SQLite，不需要 MySQL）
"""
import json
import re
import sqlite3
from typing import Dict, List
from llm_client import LLMClient


class SimpleStorage:
    """简单的 SQLite 存储（用于测试）"""
    
    def __init__(self, db_path="test_profiles.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY,
                account_name TEXT,
                identity TEXT,
                profile_data TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_profile(self, account_id: str):
        """获取画像"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM profiles WHERE account_id = ?", (account_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def save_profile(self, account_id: str, data: Dict):
        """保存画像"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO profiles (account_id, account_name, identity, profile_data)
            VALUES (?, ?, ?, ?)
        """, (
            account_id,
            data.get('name', account_id),
            data.get('identity', '未知'),
            json.dumps(data, ensure_ascii=False)
        ))
        
        conn.commit()
        conn.close()


class TestEventAnalyzer:
    """测试版事件分析器"""
    
    def __init__(self):
        self.llm_client = LLMClient()
        self.storage = SimpleStorage()
    
    def analyze_event(self, event_data: Dict) -> Dict:
        """分析事件"""
        print(f"\n{'='*60}")
        print(f"开始分析事件: {event_data.get('event_id')}")
        print(f"{'='*60}\n")
        
        # 步骤1: 抽取实体
        print("步骤1: 抽取实体...")
        entities = self.extract_entities(event_data)
        print(f"  提取到 {len(entities.get('accounts', []))} 个账号实体")
        print(f"  账号列表: {entities.get('accounts', [])}")
        print(f"  关键词: {entities.get('keywords', [])}")
        
        # 步骤2: 匹配账号
        print("\n步骤2: 匹配账号画像库...")
        matched_profiles = self.match_profiles(entities)
        print(f"  匹配到 {len(matched_profiles)} 个账号")
        
        for item in matched_profiles:
            if item['profile']:
                print(f"    ✓ {item['account_id']} - 已有画像")
            else:
                print(f"    ✗ {item['account_id']} - 新账号")
        
        # 步骤3: 推演画像
        print("\n步骤3: 推演涉事账号画像...")
        enriched_profiles = self.enrich_profiles(matched_profiles, event_data, entities)
        
        # 步骤4: 生成报告
        print("\n步骤4: 生成分析报告...")
        report = self.generate_report(event_data, entities, enriched_profiles)
        
        print(f"\n{'='*60}")
        print("事件分析完成")
        print(f"{'='*60}\n")
        
        return report
    
    def extract_entities(self, event_data: Dict) -> Dict:
        """抽取实体（使用规则，避免 LLM 调用失败）"""
        text = event_data.get("event_description", "")
        related_content = event_data.get("related_content", [])
        all_text = text + " " + " ".join(related_content)
        
        entities = {
            "accounts": [],
            "keywords": [],
            "topics": [],
            "locations": []
        }
        
        # 抽取账号
        accounts = re.findall(r'@(\S+)|user[_-](\w+)', all_text)
        entities["accounts"] = list(set([a[0] or a[1] for a in accounts if a[0] or a[1]]))
        
        # 抽取话题
        topics = re.findall(r'#(\w+)', all_text)
        entities["topics"] = list(set(topics))
        
        # 简单关键词抽取
        keywords = ['火灾', '救援', '消防', '事故', '交通', '安全', '新闻', '报道']
        entities["keywords"] = [k for k in keywords if k in all_text]
        
        return entities
    
    def match_profiles(self, entities: Dict) -> List[Dict]:
        """匹配账号"""
        accounts = entities.get("accounts", [])
        matched = []
        
        for account_id in accounts:
            profile = self.storage.get_profile(account_id)
            
            matched.append({
                "account_id": account_id,
                "profile": profile,
                "source": "database" if profile else "new"
            })
        
        return matched
    
    def enrich_profiles(self, matched_profiles: List[Dict], 
                       event_data: Dict, entities: Dict) -> List[Dict]:
        """推演画像"""
        enriched = []
        
        for item in matched_profiles:
            account_id = item["account_id"]
            existing_profile = item["profile"]
            
            print(f"  处理账号: {account_id}")
            
            # 简化版：直接基于事件信息生成画像
            profile = {
                "account_id": account_id,
                "name": account_id,
                "identity": self._infer_identity(account_id, event_data),
                "event_analysis": {
                    "event_role": self._infer_role(account_id, event_data),
                    "stance": "中立",
                    "influence_level": "中等",
                    "risk_level": "低",
                    "analysis": f"该账号在事件 {event_data.get('event_id')} 中参与讨论"
                },
                "event_context": {
                    "event_id": event_data.get('event_id'),
                    "event_type": event_data.get('event_type')
                }
            }
            
            # 保存到数据库
            self.storage.save_profile(account_id, profile)
            
            enriched.append(profile)
        
        return enriched
    
    def _infer_identity(self, account_id: str, event_data: Dict) -> str:
        """推断身份"""
        account_lower = account_id.lower()
        
        if '消防' in account_lower or 'fire' in account_lower:
            return "消防员"
        elif '记者' in account_lower or '新闻' in account_lower:
            return "记者"
        elif '交警' in account_lower or 'police' in account_lower:
            return "交警"
        elif 'user' in account_lower:
            return "普通用户"
        else:
            return "未知身份"
    
    def _infer_role(self, account_id: str, event_data: Dict) -> str:
        """推断角色"""
        content = " ".join(event_data.get("related_content", []))
        
        if f"@{account_id}" in content or account_id in content:
            if "发布" in content or "报道" in content:
                return "信息发布者"
            elif "转发" in content:
                return "信息传播者"
            else:
                return "参与者"
        
        return "旁观者"
    
    def generate_report(self, event_data: Dict, entities: Dict, 
                       enriched_profiles: List[Dict]) -> Dict:
        """生成报告"""
        # 统计角色分布
        roles = {}
        for profile in enriched_profiles:
            role = profile.get("event_analysis", {}).get("event_role", "未知")
            roles[role] = roles.get(role, 0) + 1
        
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
                "existing_accounts": 0,
                "new_accounts": len(enriched_profiles)
            },
            "profiles": enriched_profiles,
            "summary": {
                "role_distribution": roles,
                "risk_distribution": {"低": len(enriched_profiles)},
                "high_risk_accounts": []
            }
        }
        
        return report
    
    def save_report(self, report: Dict, output_path: str = None):
        """保存报告"""
        if not output_path:
            event_id = report["event_info"]["event_id"]
            output_path = f"test_event_analysis_{event_id}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"分析报告已保存: {output_path}")


def main():
    """测试函数"""
    # 示例事件
    event_data = {
        "event_id": "test_fire_001",
        "event_type": "突发事件",
        "event_description": "某地发生火灾，多名网友发布现场视频",
        "related_content": [
            "@消防员小王 发布了现场救援视频",
            "@新闻记者李明 报道了事件经过",
            "user_12345 转发并评论：希望大家平安",
            "#火灾救援 话题下有大量讨论"
        ],
        "timestamp": "2025-03-06 10:00:00"
    }
    
    print("="*60)
    print("OASIS 事件分析系统 - 测试版")
    print("="*60)
    
    # 创建分析器
    analyzer = TestEventAnalyzer()
    
    # 分析事件
    report = analyzer.analyze_event(event_data)
    
    # 保存报告
    analyzer.save_report(report)
    
    # 打印摘要
    print("\n" + "="*60)
    print("分析摘要")
    print("="*60)
    print(f"事件ID: {report['event_info']['event_id']}")
    print(f"事件类型: {report['event_info']['event_type']}")
    print(f"涉及账号数: {report['account_analysis']['total_accounts']}")
    
    print(f"\n提取的实体:")
    print(f"  账号: {report['extracted_entities']['accounts']}")
    print(f"  关键词: {report['extracted_entities']['keywords']}")
    print(f"  话题: {report['extracted_entities']['topics']}")
    
    print(f"\n账号画像:")
    for profile in report['profiles']:
        print(f"  - {profile['account_id']}")
        print(f"    身份: {profile['identity']}")
        print(f"    角色: {profile['event_analysis']['event_role']}")
        print(f"    风险: {profile['event_analysis']['risk_level']}")
    
    print(f"\n角色分布: {report['summary']['role_distribution']}")
    print("="*60)


if __name__ == "__main__":
    main()

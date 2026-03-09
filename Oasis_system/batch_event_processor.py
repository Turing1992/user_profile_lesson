# -*- coding: utf-8 -*-
"""
批量事件处理器
处理多个事件，生成综合分析报告
"""
import json
import os
from typing import List, Dict
from event_analyzer import EventAnalyzer
from datetime import datetime


class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self):
        self.analyzer = EventAnalyzer()
        self.reports = []
    
    def process_events(self, events: List[Dict]) -> List[Dict]:
        """
        批量处理事件
        
        Args:
            events: 事件列表
        
        Returns:
            分析报告列表
        """
        print(f"\n{'='*60}")
        print(f"开始批量处理 {len(events)} 个事件")
        print(f"{'='*60}\n")
        
        for idx, event in enumerate(events, 1):
            print(f"\n[{idx}/{len(events)}] 处理事件: {event.get('event_id')}")
            
            try:
                report = self.analyzer.analyze_event(event)
                self.reports.append(report)
            except Exception as e:
                print(f"  错误: {e}")
                continue
        
        print(f"\n{'='*60}")
        print(f"批量处理完成，成功处理 {len(self.reports)} 个事件")
        print(f"{'='*60}\n")
        
        return self.reports
    
    def generate_cross_event_analysis(self) -> Dict:
        """生成跨事件分析"""
        if not self.reports:
            return {}
        
        # 收集所有涉事账号
        all_accounts = {}
        for report in self.reports:
            for profile in report["profiles"]:
                account_id = profile["account_id"]
                if account_id not in all_accounts:
                    all_accounts[account_id] = {
                        "account_id": account_id,
                        "events": [],
                        "roles": [],
                        "risk_levels": []
                    }
                
                all_accounts[account_id]["events"].append(report["event_info"]["event_id"])
                
                event_analysis = profile.get("event_analysis", {})
                if event_analysis.get("event_role"):
                    all_accounts[account_id]["roles"].append(event_analysis["event_role"])
                if event_analysis.get("risk_level"):
                    all_accounts[account_id]["risk_levels"].append(event_analysis["risk_level"])
        
        # 识别重点关注账号
        key_accounts = []
        for account_id, data in all_accounts.items():
            # 参与多个事件的账号
            if len(data["events"]) > 1:
                key_accounts.append({
                    "account_id": account_id,
                    "event_count": len(data["events"]),
                    "events": data["events"],
                    "primary_role": max(set(data["roles"]), key=data["roles"].count) if data["roles"] else "未知",
                    "risk_assessment": "高" if "高" in data["risk_levels"] or "high" in data["risk_levels"] else "中"
                })
        
        # 按参与事件数排序
        key_accounts.sort(key=lambda x: x["event_count"], reverse=True)
        
        return {
            "total_events": len(self.reports),
            "total_accounts": len(all_accounts),
            "key_accounts": key_accounts[:20],  # Top 20
            "statistics": {
                "multi_event_accounts": len([a for a in all_accounts.values() if len(a["events"]) > 1]),
                "high_risk_accounts": len([a for a in all_accounts.values() if "高" in a["risk_levels"] or "high" in a["risk_levels"]])
            }
        }
    
    def save_batch_report(self, output_dir: str = "event_reports"):
        """保存批量处理报告"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存各个事件报告
        for report in self.reports:
            event_id = report["event_info"]["event_id"]
            filename = os.path.join(output_dir, f"{event_id}_{timestamp}.json")
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 保存跨事件分析
        cross_analysis = self.generate_cross_event_analysis()
        cross_filename = os.path.join(output_dir, f"cross_event_analysis_{timestamp}.json")
        
        with open(cross_filename, 'w', encoding='utf-8') as f:
            json.dump(cross_analysis, f, ensure_ascii=False, indent=2)
        
        print(f"\n批量报告已保存到: {output_dir}")
        print(f"  - {len(self.reports)} 个事件报告")
        print(f"  - 1 个跨事件分析报告")
        
        return cross_analysis
    
    def print_summary(self):
        """打印摘要"""
        cross_analysis = self.generate_cross_event_analysis()
        
        print("\n" + "="*60)
        print("批量事件分析摘要")
        print("="*60)
        print(f"处理事件数: {cross_analysis['total_events']}")
        print(f"涉及账号数: {cross_analysis['total_accounts']}")
        print(f"多事件参与账号: {cross_analysis['statistics']['multi_event_accounts']}")
        print(f"高风险账号: {cross_analysis['statistics']['high_risk_accounts']}")
        
        print(f"\n重点关注账号 (Top 10):")
        for idx, account in enumerate(cross_analysis['key_accounts'][:10], 1):
            print(f"  {idx}. {account['account_id']}")
            print(f"     参与事件: {account['event_count']} 个")
            print(f"     主要角色: {account['primary_role']}")
            print(f"     风险评估: {account['risk_assessment']}")
        
        print("="*60 + "\n")


def load_events_from_file(file_path: str) -> List[Dict]:
    """从文件加载事件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        # 从文件加载事件
        events_file = sys.argv[1]
        print(f"从文件加载事件: {events_file}")
        events = load_events_from_file(events_file)
    else:
        # 使用示例事件
        print("使用示例事件")
        events = [
            {
                "event_id": "event_001",
                "event_type": "社会事件",
                "event_description": "某地发生火灾",
                "related_content": [
                    "@消防员小王 发布了现场救援视频",
                    "@新闻记者李明 报道了事件经过",
                    "user_12345 转发并评论"
                ],
                "timestamp": "2025-03-06 10:00:00"
            },
            {
                "event_id": "event_002",
                "event_type": "公共安全",
                "event_description": "交通事故引发关注",
                "related_content": [
                    "@交警张sir 发布了事故通报",
                    "@新闻记者李明 再次报道",
                    "user_67890 发布现场照片"
                ],
                "timestamp": "2025-03-06 14:00:00"
            }
        ]
    
    # 创建处理器
    processor = BatchEventProcessor()
    
    # 批量处理
    reports = processor.process_events(events)
    
    # 保存报告
    processor.save_batch_report()
    
    # 打印摘要
    processor.print_summary()


if __name__ == "__main__":
    main()

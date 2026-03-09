# -*- coding: utf-8 -*-
"""
批量事件处理器 - 测试版
"""
import json
import os
from test_event_analyzer import TestEventAnalyzer


def main():
    """测试批量处理"""
    print("="*60)
    print("批量事件处理测试")
    print("="*60)
    
    # 加载事件
    with open('test_batch_events.json', 'r', encoding='utf-8') as f:
        events = json.load(f)
    
    print(f"\n加载了 {len(events)} 个事件\n")
    
    # 创建分析器
    analyzer = TestEventAnalyzer()
    
    # 处理每个事件
    reports = []
    for idx, event in enumerate(events, 1):
        print(f"\n[{idx}/{len(events)}] 处理事件: {event['event_id']}")
        print("-"*60)
        
        report = analyzer.analyze_event(event)
        reports.append(report)
        
        # 保存单个报告
        analyzer.save_report(report, f"test_report_{event['event_id']}.json")
    
    # 跨事件分析
    print("\n" + "="*60)
    print("跨事件分析")
    print("="*60)
    
    # 收集所有账号
    all_accounts = {}
    for report in reports:
        for profile in report['profiles']:
            account_id = profile['account_id']
            if account_id not in all_accounts:
                all_accounts[account_id] = {
                    "account_id": account_id,
                    "events": [],
                    "roles": []
                }
            
            all_accounts[account_id]["events"].append(report['event_info']['event_id'])
            all_accounts[account_id]["roles"].append(
                profile['event_analysis']['event_role']
            )
    
    # 识别重点账号
    multi_event_accounts = [
        acc for acc in all_accounts.values() 
        if len(acc["events"]) > 1
    ]
    
    print(f"\n总事件数: {len(reports)}")
    print(f"总账号数: {len(all_accounts)}")
    print(f"参与多个事件的账号: {len(multi_event_accounts)}")
    
    if multi_event_accounts:
        print(f"\n重点关注账号:")
        for acc in multi_event_accounts:
            print(f"  - {acc['account_id']}")
            print(f"    参与事件: {acc['events']}")
            print(f"    角色: {set(acc['roles'])}")
    
    # 保存跨事件分析
    cross_analysis = {
        "total_events": len(reports),
        "total_accounts": len(all_accounts),
        "multi_event_accounts": multi_event_accounts,
        "all_accounts": list(all_accounts.values())
    }
    
    with open('test_cross_event_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(cross_analysis, f, ensure_ascii=False, indent=2)
    
    print(f"\n跨事件分析已保存: test_cross_event_analysis.json")
    print("="*60)


if __name__ == "__main__":
    main()

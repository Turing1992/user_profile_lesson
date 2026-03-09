# 事件驱动的画像推演系统 - 使用指南

## 系统概述

这是一个**事件驱动的智能画像分析系统**，能够：
1. 从事件中自动抽取涉事账号
2. 在画像库中匹配账号信息
3. 使用 OASIS 推演深度画像
4. 生成事件分析报告

---

## 核心流程

```
事件输入
   ↓
实体抽取 (LLM + 规则)
   ├─ 账号ID
   ├─ 关键词
   ├─ 话题标签
   └─ 地点信息
   ↓
账号匹配
   ├─ 在画像库中查找
   ├─ 已有画像 → 深度推演
   └─ 新账号 → 创建画像
   ↓
画像推演 (OASIS)
   ├─ 基础信息分析
   ├─ 身份深度分析
   ├─ 行为模式预测
   ├─ 事件角色分析
   └─ 风险评估
   ↓
生成报告
   ├─ 单事件报告
   └─ 跨事件分析
```

---

## 快速开始

### 1. 单个事件分析

```bash
# 使用示例事件
python3 event_analyzer.py

# 输出：
# - event_analysis_event_001.json (分析报告)
# - 画像数据保存到数据库
```

### 2. 批量事件处理

```bash
# 使用示例事件文件
python3 batch_event_processor.py example_events.json

# 输出：
# - event_reports/ 目录
#   ├─ fire_incident_001_20250306_120000.json
#   ├─ traffic_accident_002_20250306_120000.json
#   └─ cross_event_analysis_20250306_120000.json
```

---

## 输入格式

### 事件数据结构

```json
{
    "event_id": "事件唯一标识",
    "event_type": "事件类型",
    "event_description": "事件描述",
    "related_content": [
        "相关内容1",
        "相关内容2"
    ],
    "timestamp": "时间戳",
    "location": "地点（可选）",
    "severity": "严重程度（可选）"
}
```

### 完整示例

```json
{
    "event_id": "fire_incident_001",
    "event_type": "突发事件",
    "event_description": "某商场发生火灾，消防部门紧急救援",
    "related_content": [
        "@消防员小王 发布了现场救援视频",
        "@新闻记者李明 报道了事件经过",
        "user_12345 转发并评论：希望大家平安",
        "#火灾救援 话题下有大量讨论"
    ],
    "timestamp": "2025-03-06 10:30:00",
    "location": "某市中心商场",
    "severity": "严重"
}
```

---

## 输出格式

### 单事件分析报告

```json
{
    "event_info": {
        "event_id": "fire_incident_001",
        "event_type": "突发事件",
        "event_description": "某商场发生火灾...",
        "timestamp": "2025-03-06 10:30:00"
    },
    "extracted_entities": {
        "accounts": ["消防员小王", "新闻记者李明", "user_12345"],
        "keywords": ["火灾", "救援", "消防"],
        "topics": ["火灾救援"],
        "locations": ["某市中心商场"]
    },
    "account_analysis": {
        "total_accounts": 3,
        "existing_accounts": 1,
        "new_accounts": 2
    },
    "profiles": [
        {
            "account_id": "消防员小王",
            "basic_profile": {...},
            "event_analysis": {
                "event_role": "信息发布者",
                "stance": "中立",
                "attitude": "专业",
                "influence_level": "中等",
                "risk_level": "低",
                "analysis": "该账号是消防员，发布了专业的救援信息..."
            },
            "event_context": {
                "event_id": "fire_incident_001",
                "event_type": "突发事件"
            }
        }
    ],
    "summary": {
        "role_distribution": {
            "信息发布者": 1,
            "传播者": 2
        },
        "risk_distribution": {
            "低": 2,
            "中": 1
        },
        "high_risk_accounts": []
    }
}
```

### 跨事件分析报告

```json
{
    "total_events": 5,
    "total_accounts": 25,
    "key_accounts": [
        {
            "account_id": "新闻记者李明",
            "event_count": 4,
            "events": ["fire_incident_001", "traffic_accident_002", ...],
            "primary_role": "信息传播者",
            "risk_assessment": "低"
        }
    ],
    "statistics": {
        "multi_event_accounts": 3,
        "high_risk_accounts": 1
    }
}
```

---

## 实战案例

### 案例 1: 突发事件分析

**场景：** 某地发生火灾，需要快速了解涉事账号

**步骤：**

1. 准备事件数据 `fire_event.json`:
```json
{
    "event_id": "fire_20250306",
    "event_type": "突发事件",
    "event_description": "某商场发生火灾",
    "related_content": [
        "@消防局官方 发布救援通报",
        "@目击者张三 发布现场视频",
        "user_abc123 转发并评论"
    ],
    "timestamp": "2025-03-06 10:00:00"
}
```

2. 运行分析：
```bash
python3 -c "
from event_analyzer import EventAnalyzer
import json

with open('fire_event.json') as f:
    event = json.load(f)

analyzer = EventAnalyzer()
report = analyzer.analyze_event(event)
analyzer.save_report(report)
"
```

3. 查看结果：
```bash
cat event_analysis_fire_20250306.json
```

### 案例 2: 舆情监控

**场景：** 监控一周内的所有事件，识别重点账号

**步骤：**

1. 收集一周的事件数据 `weekly_events.json`

2. 批量处理：
```bash
python3 batch_event_processor.py weekly_events.json
```

3. 分析跨事件报告：
```bash
cat event_reports/cross_event_analysis_*.json
```

4. 识别重点关注账号：
```python
import json

with open('event_reports/cross_event_analysis_xxx.json') as f:
    analysis = json.load(f)

# 参与多个事件的账号
for account in analysis['key_accounts']:
    if account['event_count'] >= 3:
        print(f"重点账号: {account['account_id']}")
        print(f"  参与事件: {account['event_count']} 个")
        print(f"  主要角色: {account['primary_role']}")
```

### 案例 3: 与现有画像库集成

**场景：** 已有用户画像库，需要分析新事件

**步骤：**

1. 确保画像库已初始化：
```python
from storage import ProfileStorage

storage = ProfileStorage()
storage.init_table()

# 查看已有画像
profile = storage.get_profile("某账号ID")
```

2. 分析新事件：
```python
from event_analyzer import EventAnalyzer

analyzer = EventAnalyzer()

event = {
    "event_id": "new_event",
    "event_description": "...",
    "related_content": ["@某账号ID 发布了..."]
}

# 系统会自动：
# 1. 在画像库中查找 "某账号ID"
# 2. 如果找到，使用已有画像进行深度分析
# 3. 如果没找到，创建新画像
report = analyzer.analyze_event(event)
```

---

## 高级功能

### 1. 自定义实体抽取规则

```python
from event_analyzer import EventAnalyzer

class CustomEventAnalyzer(EventAnalyzer):
    def _rule_based_extraction(self, event_data):
        """自定义抽取规则"""
        entities = super()._rule_based_extraction(event_data)
        
        # 添加自定义规则
        # 例如：抽取手机号、邮箱等
        text = event_data.get("event_description", "")
        
        import re
        phones = re.findall(r'1[3-9]\d{9}', text)
        entities["phones"] = phones
        
        return entities

# 使用自定义分析器
analyzer = CustomEventAnalyzer()
```

### 2. 集成外部数据源

```python
from event_analyzer import EventAnalyzer

# 从微博 API 获取事件
def fetch_weibo_event(topic):
    # 调用微博 API
    posts = weibo_api.search(topic)
    
    event = {
        "event_id": f"weibo_{topic}",
        "event_type": "社交媒体事件",
        "event_description": f"关于 {topic} 的讨论",
        "related_content": [post.text for post in posts],
        "timestamp": datetime.now().isoformat()
    }
    
    return event

# 分析
analyzer = EventAnalyzer()
event = fetch_weibo_event("#某热门话题")
report = analyzer.analyze_event(event)
```

### 3. 实时事件流处理

```python
from event_analyzer import EventAnalyzer
import time

analyzer = EventAnalyzer()

def process_event_stream():
    """处理实时事件流"""
    while True:
        # 从消息队列获取事件
        event = event_queue.get()
        
        # 分析事件
        report = analyzer.analyze_event(event)
        
        # 检查高风险账号
        high_risk = report['summary']['high_risk_accounts']
        if high_risk:
            send_alert(high_risk)
        
        time.sleep(1)
```

---

## API 集成

### Flask API 示例

```python
from flask import Flask, request, jsonify
from event_analyzer import EventAnalyzer

app = Flask(__name__)
analyzer = EventAnalyzer()

@app.route('/analyze_event', methods=['POST'])
def analyze_event():
    """事件分析 API"""
    event_data = request.json
    
    try:
        report = analyzer.analyze_event(event_data)
        return jsonify({
            "status": "success",
            "report": report
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/batch_analyze', methods=['POST'])
def batch_analyze():
    """批量分析 API"""
    events = request.json.get('events', [])
    
    from batch_event_processor import BatchEventProcessor
    processor = BatchEventProcessor()
    
    reports = processor.process_events(events)
    cross_analysis = processor.generate_cross_event_analysis()
    
    return jsonify({
        "status": "success",
        "reports": reports,
        "cross_analysis": cross_analysis
    })

if __name__ == '__main__':
    app.run(port=5002)
```

**使用：**
```bash
# 启动 API
python3 event_api.py

# 调用 API
curl -X POST http://localhost:5002/analyze_event \
  -H "Content-Type: application/json" \
  -d @fire_event.json
```

---

## 性能优化

### 1. 批量处理优化

```python
# 使用多线程处理
from concurrent.futures import ThreadPoolExecutor

def process_events_parallel(events, max_workers=5):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(analyzer.analyze_event, event) 
                  for event in events]
        
        reports = [f.result() for f in futures]
    
    return reports
```

### 2. 缓存优化

```python
# 缓存画像查询结果
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_cached_profile(account_id):
    return storage.get_profile(account_id)
```

---

## 常见问题

### Q1: 如何提高实体抽取准确率？

**A:** 
1. 使用更好的 LLM 模型
2. 优化 prompt 设计
3. 添加领域特定的规则
4. 使用 NER 模型辅助

### Q2: 画像库很大，查询很慢怎么办？

**A:**
1. 为 account_id 建立索引
2. 使用 Redis 缓存热点数据
3. 考虑使用 Elasticsearch 存储

### Q3: 如何处理实时事件流？

**A:**
1. 使用消息队列（RocketMQ/Kafka）
2. 多进程/多线程并发处理
3. 异步处理，避免阻塞

---

## 总结

这个系统实现了：
✅ 自动从事件中抽取涉事账号
✅ 智能匹配画像库
✅ 深度画像推演
✅ 跨事件关联分析
✅ 风险账号识别

**适用场景：**
- 舆情监控
- 突发事件分析
- 重点人员识别
- 社交网络分析

开始使用吧！🚀

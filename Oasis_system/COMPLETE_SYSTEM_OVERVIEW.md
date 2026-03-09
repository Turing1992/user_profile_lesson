# OASIS 完整系统概览

## 系统全貌

OASIS 现在是一个**三合一的智能分析平台**：

```
┌─────────────────────────────────────────────────────────┐
│                    OASIS 系统                            │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  模块 1      │  │  模块 2      │  │  模块 3      │  │
│  │  账号画像    │  │  社交模拟    │  │  事件分析    │  │
│  │  推演系统    │  │  系统        │  │  系统        │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                 │                 │            │
│         │                 │                 │            │
│    推演单个账号      模拟社交网络      分析事件涉事账号  │
│    的深度画像        的演化过程        并推演画像        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 模块 1: 账号画像推演系统

### 功能
从少量信息推演出完整的用户画像

### 输入
```json
{
    "account_id": "user_001",
    "name": "科技小王",
    "identity": "科技博主",
    "description": "985毕业，大厂产品经理"
}
```

### 输出
```json
{
    "basic_info": "真实姓名、性别、年龄、地域...",
    "identity_analysis": "主要身份、隐藏身份...",
    "behavior_prediction": "活跃时间、发帖频率...",
    "social_inference": "关注类型、粉丝画像...",
    "content_preference": "兴趣领域、价值观...",
    "risk_assessment": "风险等级、可信度..."
}
```

### 使用
```bash
python3 oasis_main.py input.json output.json
```

---

## 模块 2: 社交模拟系统

### 功能
模拟成百上千个 AI 用户在虚拟社交平台上的互动

### 输入
```json
[
    {
        "account_id": "agent_001",
        "name": "科技博主",
        "interests": ["AI", "编程"],
        "personality": {"type": "外向", "activity": "高"}
    }
]
```

### 输出
- SQLite 数据库（所有用户、帖子、互动数据）
- 统计报告（用户排行、热门内容、网络分析）

### 使用
```bash
python3 oasis_simulation.py
# 输入 Agent 数量、模拟步数
```

---

## 模块 3: 事件分析系统 ⭐ 新增

### 功能
从事件中自动抽取涉事账号，匹配画像库，推演深度画像

### 输入
```json
{
    "event_id": "fire_001",
    "event_type": "突发事件",
    "event_description": "某地发生火灾",
    "related_content": [
        "@消防员小王 发布救援视频",
        "@记者李明 报道事件",
        "user_123 转发评论"
    ]
}
```

### 处理流程
```
1. 实体抽取
   └─ 提取账号: [@消防员小王, @记者李明, user_123]

2. 账号匹配
   ├─ @消防员小王 → 在画像库中找到
   ├─ @记者李明 → 在画像库中找到
   └─ user_123 → 新账号，需要创建画像

3. 画像推演
   ├─ 已有账号 → 深度分析在事件中的角色
   └─ 新账号 → 基于事件信息创建画像

4. 生成报告
   ├─ 每个账号的详细画像
   ├─ 事件角色分析
   └─ 风险评估
```

### 输出
```json
{
    "event_info": {...},
    "extracted_entities": {
        "accounts": ["消防员小王", "记者李明", "user_123"],
        "keywords": ["火灾", "救援"],
        "topics": ["#火灾救援"]
    },
    "profiles": [
        {
            "account_id": "消防员小王",
            "event_analysis": {
                "event_role": "信息发布者",
                "stance": "中立",
                "influence_level": "中等",
                "risk_level": "低"
            }
        }
    ],
    "summary": {
        "role_distribution": {...},
        "high_risk_accounts": [...]
    }
}
```

### 使用
```bash
# 单个事件
python3 event_analyzer.py

# 批量事件
python3 batch_event_processor.py events.json
```

---

## 三个模块的关系

### 数据流转

```
事件分析系统 ──提取账号ID──> 画像推演系统 ──生成画像──> 画像库
                                                        │
                                                        ↓
                                            社交模拟系统 ←─加载画像
```

### 典型使用场景

**场景 1: 舆情监控**
```
1. 事件分析系统 → 从热点事件中提取涉事账号
2. 画像推演系统 → 推演账号的深度画像
3. 识别高风险账号 → 重点监控
```

**场景 2: 社交网络研究**
```
1. 画像推演系统 → 生成大量用户画像
2. 社交模拟系统 → 模拟社交网络演化
3. 分析网络结构 → 研究传播规律
```

**场景 3: 事件预测**
```
1. 历史事件分析 → 识别关键账号
2. 社交模拟 → 模拟未来可能的传播路径
3. 风险预警 → 提前识别潜在风险
```

---

## 完整工作流示例

### 示例：分析突发事件并模拟传播

**步骤 1: 分析事件**
```bash
# 创建事件数据
cat > fire_event.json << 'EOF'
{
    "event_id": "fire_001",
    "event_description": "某商场发生火灾",
    "related_content": [
        "@消防员小王 发布救援视频",
        "@大V张三 转发并评论",
        "user_001 发布现场照片"
    ]
}
EOF

# 分析事件
python3 event_analyzer.py
```

**步骤 2: 获取涉事账号画像**
```python
import json

# 读取分析报告
with open('event_analysis_fire_001.json') as f:
    report = json.load(f)

# 提取账号画像
profiles = []
for profile in report['profiles']:
    profiles.append({
        "account_id": profile['account_id'],
        "name": profile['account_id'],
        "identity": profile.get('event_analysis', {}).get('event_role', '未知'),
        "interests": ["事件相关"],
        "personality": {"type": "外向", "activity": "高"}
    })

# 保存为模拟输入
with open('simulation_input.json', 'w') as f:
    json.dump(profiles, f, ensure_ascii=False, indent=2)
```

**步骤 3: 模拟信息传播**
```bash
# 使用涉事账号进行社交模拟
python3 oasis_simulation.py simulation_input.json

# 输入参数
模拟步数: 20
使用 LLM: n
```

**步骤 4: 分析传播效果**
```bash
# 分析模拟结果
python3 analyze_simulation.py

# 查看：
# - 哪些账号成为了意见领袖
# - 信息如何传播
# - 形成了什么样的社交网络
```

---

## 系统架构

### 文件结构
```
Oasis_system/
├── README.md                      # 总体说明
├── USAGE_GUIDE.md                 # 社交模拟使用指南
├── EVENT_ANALYSIS_GUIDE.md        # 事件分析使用指南
├── COMPLETE_SYSTEM_OVERVIEW.md    # 本文件
│
├── config.py                      # 配置文件
├── llm_client.py                  # LLM 客户端
├── storage.py                     # 数据存储
│
├── 模块 1: 画像推演
│   ├── profile_engine.py          # 推演引擎
│   ├── prompts.py                 # 提示词模板
│   ├── oasis_main.py              # 主程序
│   └── api_server.py              # API 服务
│
├── 模块 2: 社交模拟
│   ├── social_platform.py         # 社交平台
│   ├── agent.py                   # AI Agent
│   ├── recommendation.py          # 推荐系统
│   ├── simulation_engine.py       # 模拟引擎
│   ├── oasis_simulation.py        # 主程序
│   └── analyze_simulation.py      # 数据分析
│
├── 模块 3: 事件分析
│   ├── event_analyzer.py          # 事件分析器
│   ├── batch_event_processor.py   # 批量处理器
│   └── example_events.json        # 示例事件
│
├── 示例数据
│   ├── example_input.json         # 画像推演示例
│   ├── example_profiles.json      # 社交模拟示例
│   └── example_events.json        # 事件分析示例
│
└── 工具脚本
    ├── quick_test.py              # 快速测试
    └── run_simulation.sh          # 启动脚本
```

### 数据库设计

**MySQL (画像库)**
```sql
oasis_profiles
├── account_id (主键)
├── account_name
├── identity
├── basic_info (JSON)
├── identity_analysis (JSON)
├── behavior_prediction (JSON)
├── social_inference (JSON)
├── content_preference (JSON)
└── risk_assessment (JSON)
```

**SQLite (模拟数据)**
```sql
users (用户表)
posts (帖子表)
follows (关注关系表)
interactions (互动表)
mutes (屏蔽表)
```

---

## 快速开始

### 1. 环境准备
```bash
# 安装依赖
pip3 install -r requirements.txt

# 测试系统
python3 quick_test.py
```

### 2. 选择你的使用场景

**场景 A: 我有账号数据，想推演画像**
```bash
python3 oasis_main.py my_accounts.json
```

**场景 B: 我想模拟社交网络**
```bash
python3 oasis_simulation.py
```

**场景 C: 我有事件数据，想分析涉事账号**
```bash
python3 event_analyzer.py
# 或
python3 batch_event_processor.py my_events.json
```

---

## 核心优势

### 1. 模块化设计
- 三个模块独立运行
- 也可以组合使用
- 灵活适应不同需求

### 2. 智能化分析
- LLM 驱动的深度推演
- 规则引擎作为备选
- 准确率高，可解释性强

### 3. 可扩展性
- 支持大规模数据处理
- 可以集成外部数据源
- 易于添加新功能

### 4. 实用性强
- 真实场景验证
- 完整的文档和示例
- 开箱即用

---

## 应用案例

### 案例 1: 舆情监控平台
```
实时监控社交媒体 → 事件分析系统提取涉事账号 
→ 画像推演系统分析账号特征 → 识别高风险账号 
→ 预警通知
```

### 案例 2: 社交网络研究
```
收集用户数据 → 画像推演系统生成画像 
→ 社交模拟系统模拟网络演化 → 分析传播规律 
→ 发表研究论文
```

### 案例 3: 内容推荐优化
```
分析用户行为 → 画像推演系统理解用户 
→ 社交模拟系统测试推荐算法 → 优化推荐策略 
→ 提升用户体验
```

---

## 下一步计划

### 短期 (1-2周)
- [ ] 添加更多实体抽取规则
- [ ] 优化 LLM prompt
- [ ] 增加可视化界面

### 中期 (1-2月)
- [ ] 支持更多社交平台
- [ ] 集成图数据库
- [ ] 实时流处理

### 长期 (3-6月)
- [ ] 机器学习模型集成
- [ ] 分布式部署
- [ ] 商业化产品

---

## 总结

OASIS 系统现在是一个**完整的社交智能分析平台**：

✅ **画像推演** - 深度理解用户
✅ **社交模拟** - 预测网络演化
✅ **事件分析** - 快速响应突发事件

**三个模块相互配合，形成闭环：**
```
事件 → 账号 → 画像 → 模拟 → 预测 → 决策
```

开始使用，探索社交网络的奥秘！🚀

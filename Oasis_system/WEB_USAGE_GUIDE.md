# OASIS Web 测试平台使用指南

## 启动方式

```bash
cd Oasis_system
python3 web_server.py
```

浏览器打开 http://localhost:5001

---

## 系统概览

OASIS 是一个三合一的社交智能分析平台，包含三个模块：

| 模块 | 功能 | 入口 |
|------|------|------|
| 画像推演 | 从少量账号信息推演完整用户画像 | 第一个 Tab |
| 社交模拟 | 模拟多个 AI Agent 在虚拟社交平台上互动 | 第二个 Tab |
| 事件分析 | 从事件中抽取涉事账号并推演画像 | 第三个 Tab |

三个模块都依赖腾讯混元 LLM（配置在 `config.py`），每个模块都有"加载示例数据"按钮可以一键填充测试数据。

---

## 模块 1：画像推演

### 操作流程

1. 在输入框填入账号 JSON（单个对象或数组）
2. 点"开始推演"（单个）或"批量推演"（数组）
3. 系统依次调用 6 次 LLM，串行推演 6 个维度：
   - 基础信息（姓名/性别/年龄/地域/职业）
   - 身份深度分析（主要身份、隐藏身份、矛盾点）
   - 行为模式预测（活跃时间、发帖频率、情绪特征）
   - 社交关系推断（关注类型、粉丝画像、影响力）
   - 内容偏好（兴趣领域、价值观）
   - 风险评估（虚假信息风险、账号真实性）
4. 单个账号大约需要 10-30 秒
5. 结果以 JSON 展示在页面下方

### 输入参数

| 字段 | 必填 | 说明 |
|------|------|------|
| account_id | ✅ | 账号唯一标识 |
| name | 否 | 账号昵称 |
| identity | 否 | 身份标签，如"医生"、"程序员" |
| description | 否 | 个人简介/自我描述 |
| verified_reason | 否 | 平台认证原因 |
| platform | 否 | 平台标识：weibo / douyin，影响推演时的平台语境 |

信息给得越多，推演结果越准。最极端情况下只给 `account_id` + `name` 也能跑。

### 输入示例

```json
{
  "account_id": "test_001",
  "name": "科技小王",
  "identity": "互联网从业者",
  "description": "985毕业，某大厂产品经理",
  "verified_reason": "互联网公司产品经理"
}
```

### 输出结构

```json
{
  "account_id": "test_001",
  "platform": "unknown",
  "status": "success",
  "profile": {
    "basic_info": { "data": { "real_name": "...", "gender": "...", "age_range": "...", "location": "...", "occupation": "...", "confidence": 0.85 } },
    "identity_analysis": { "data": { "primary_identities": [...], "hidden_identities": [...] } },
    "behavior_prediction": { "data": { ... } },
    "social_inference": { "data": { ... } },
    "content_preference": { "data": { ... } },
    "risk_assessment": { "data": { ... } }
  }
}
```

---

## 模块 2：社交模拟

### 操作流程

1. 切到"社交模拟"Tab
2. 设置页面参数（平台、Agent 数量、步数、是否用 LLM）
3. 输入框留空（自动生成随机 Agent）或填入自定义画像 JSON
4. 点"启动模拟"
5. 模拟异步执行，页面每 2 秒自动轮询状态
6. 完成后返回所有用户、帖子、互动记录和统计信息

建议先用小参数试：10 个 Agent、5 步、不用 LLM（规则引擎快很多）。

### 页面控制参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| platform | weibo | 模拟平台：weibo / douyin |
| agent_count | 10 | 自动生成的 Agent 数量（提供自定义画像时忽略） |
| steps | 5 | 模拟步数，每步所有 Agent 各执行一次行为 |
| use_llm | false | 是否用 LLM 决策行为（false 用规则引擎，快很多） |

### 自定义 Agent 画像参数（可选）

| 字段 | 必填 | 说明 |
|------|------|------|
| account_id | ✅ | Agent 唯一标识 |
| name | ✅ | Agent 名称 |
| identity | 否 | 身份，如"科技博主" |
| interests | 否 | 兴趣标签数组，如 `["AI", "编程"]` |
| personality | 否 | 性格对象，如 `{"type": "外向", "activity": "高", "sentiment": "积极"}` |
| description | 否 | 人物描述 |

### 输入示例

```json
[
  {
    "account_id": "tech_blogger_001",
    "name": "科技小王",
    "identity": "科技博主",
    "interests": ["AI", "编程", "科技"],
    "personality": { "type": "外向", "activity": "高", "sentiment": "积极" },
    "description": "关注AI和前沿科技"
  },
  {
    "account_id": "doctor_li",
    "name": "李医生",
    "identity": "医生",
    "interests": ["医疗", "健康", "养生"],
    "personality": { "type": "内向", "activity": "中", "sentiment": "中性" },
    "description": "三甲医院医生，分享健康知识"
  }
]
```

### 输出结构

包含 users（用户列表）、posts（帖子列表）、follows（关注关系）、interactions（互动记录）和 statistics（统计摘要）。

---

## 模块 3：事件分析

### 操作流程

1. 切到"事件分析"Tab
2. 填入事件 JSON（单个对象或数组）
3. 点"分析事件"（单个）或"批量分析"（数组）
4. 系统处理流程：
   - 用 LLM 从 related_content 中抽取账号实体
   - 去画像库匹配已有账号
   - 对每个涉事账号推演画像和事件角色
   - 生成分析报告
5. 批量分析额外生成"跨事件分析"，识别同时参与多个事件的重点账号

### 输入参数

| 字段 | 必填 | 说明 |
|------|------|------|
| event_id | ✅ | 事件唯一标识 |
| event_type | 否 | 事件类型，如"突发事件"、"食品安全" |
| event_description | 否 | 事件描述 |
| related_content | 否 | 相关内容数组，系统从中抽取涉事账号 |
| timestamp | 否 | 事件时间 |
| location | 否 | 事件地点 |
| severity | 否 | 严重程度 |

`related_content` 是实体抽取的数据来源，支持的格式：
- `@xxx` 格式的账号名
- `user_xxx` 格式的用户 ID
- `#话题#` 格式的话题标签

### 输入示例

```json
{
  "event_id": "fire_001",
  "event_type": "突发事件",
  "event_description": "某商场发生火灾",
  "related_content": [
    "@消防员小王 发布救援视频",
    "@记者李明 报道事件",
    "user_123 转发评论"
  ]
}
```

### 输出结构

```json
{
  "status": "success",
  "report": {
    "event_info": { ... },
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
      "role_distribution": { ... },
      "high_risk_accounts": [ ... ]
    }
  }
}
```

---

## 三个模块的关系

```
事件分析 ──提取账号──> 画像推演 ──生成画像──> 画像库
                                                │
                                                ↓
                                    社交模拟 ←─加载画像
```

典型场景：
- 舆情监控：事件分析提取账号 → 画像推演识别高风险账号 → 重点监控
- 社交研究：画像推演生成用户 → 社交模拟预测网络演化 → 分析传播规律
- 事件预测：历史事件分析 → 社交模拟预测传播路径 → 风险预警

---

## 注意事项

1. 所有模块都依赖腾讯混元 LLM API，确保 `config.py` 中的 API key 有效
2. MySQL 连不上时会自动跳过，不影响核心功能测试
3. 社交模拟建议先用小参数（10 Agent、5 步、不用 LLM）跑通
4. 画像推演每个账号需要调用 6 次 LLM，注意 API 配额

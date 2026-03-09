# OASIS 社交模拟平台

## 系统概述
OASIS (Open Agent Social Interaction Simulations) 是一个基于 LLM 的大规模社交媒体模拟平台，能够模拟数百到数千个 AI Agent 在类似 Twitter/Reddit 的平台上进行真实的社交互动。

系统包含两大核心功能：
1. **账号画像推演** - 基于 LLM 的深度用户画像分析
2. **社交模拟** - 多 Agent 社交行为模拟和网络演化

## 核心功能

### 1. 账号画像推演
- **基础信息分析**: 提取真实姓名、性别、年龄、地域、职业等基础特征
- **身份深度分析**: 多维度身份识别、矛盾点检测、隐藏身份推断
- **行为模式预测**: 活跃时间、发帖频率、互动方式、情绪特征
- **社交关系推断**: 关注类型、粉丝画像、社交圈层、影响力评估
- **内容偏好分析**: 兴趣领域、消费习惯、创作倾向、价值观
- **风险评估**: 虚假信息、恶意行为、舆情风险、违规内容评估

### 2. 社交模拟
- **多 Agent 系统**: 支持数百到数千个 AI Agent 同时运行
- **13 种社交行为**: 发帖、评论、点赞、转发、关注、搜索等
- **动态社交网络**: 实时更新的关注关系和内容流
- **智能推荐系统**: 基于兴趣和热度的内容推荐
- **LLM + 规则混合**: 支持 LLM 决策和规则引擎两种模式
- **数据分析**: 完整的统计分析和可视化工具

## 技术架构
- Python 3.6+
- LLM API (腾讯混元)
- Flask API服务
- MySQL存储
- Redis缓存（可选）

## 快速开始

### 方式1: 社交模拟（推荐）
```bash
# 运行社交模拟
python3.6 oasis_simulation.py

# 交互式输入参数：
# - Agent 数量（默认 20）
# - 模拟步数（默认 10）
# - 是否使用 LLM 决策（默认否，使用规则引擎）

# 分析模拟结果
python3.6 analyze_simulation.py
```

### 方式2: 账号画像推演
```bash
# 使用示例数据
python3.6 oasis_main.py

# 使用自定义输入文件
python3.6 oasis_main.py input.json output.json
```

### 方式3: API服务
```bash
# 启动API服务
python3.6 api_server.py

# 服务将在 http://localhost:5001 启动
```

## API接口

### 1. 健康检查
```bash
GET /health
```

### 2. 单个账号分析
```bash
POST /profile/analyze?save=true

# 请求体
{
    "account_id": "dy_001",
    "name": "科技小王",
    "identity": "互联网从业者",
    "description": "985毕业，现在某大厂做产品经理",
    "verified_reason": "互联网公司产品经理"
}
```

### 3. 批量账号分析
```bash
POST /profile/batch?save=true

# 请求体
[
    {
        "account_id": "dy_001",
        "name": "科技小王",
        ...
    },
    {
        "account_id": "wb_002",
        "name": "李医生",
        ...
    }
]
```

### 4. 获取已保存画像
```bash
GET /profile/get/<account_id>
```

## 输入格式
```json
{
    "account_id": "账号ID（必填）",
    "name": "账号名称",
    "identity": "身份标签",
    "description": "自我描述",
    "verified_reason": "认证原因"
}
```

## 输出格式
```json
{
    "account_id": "账号ID",
    "status": "success",
    "profile": {
        "basic_info": {
            "data": {
                "real_name": "推断的真实姓名",
                "gender": "男/女/未知",
                "age_range": "25-35岁",
                "location": "地域特征",
                "occupation": "职业身份",
                "education": "教育背景",
                "social_class": "社会阶层",
                "confidence": 0.85
            }
        },
        "identity_analysis": {
            "data": {
                "primary_identities": ["主要身份"],
                "identity_confidence": {"身份": 0.9},
                "hidden_identities": ["潜在身份"]
            }
        },
        "behavior_prediction": {...},
        "social_inference": {...},
        "content_preference": {...},
        "risk_assessment": {...}
    }
}
```

## 推演维度说明

### 1. 基础信息分析
- 真实姓名推断（排除网名）
- 性别、年龄范围
- 地域特征
- 职业身份
- 教育背景
- 社会阶层

### 2. 身份深度分析
- 主要身份标签识别
- 身份可信度评估
- 身份矛盾点检测
- 潜在隐藏身份推断
- 身份演变趋势

### 3. 行为模式预测
- 活跃时间段
- 发帖频率
- 内容类型偏好
- 互动方式
- 情绪表达特征

### 4. 社交关系推断
- 可能关注的账号类型
- 粉丝群体特征
- 社交圈层
- 影响力评估

### 5. 内容偏好分析
- 兴趣领域
- 内容消费习惯
- 内容创作倾向
- 话题敏感度
- 价值观倾向

### 6. 风险评估
- 虚假信息传播风险
- 恶意行为风险
- 舆情风险
- 违规内容风险
- 账号真实性风险

## 配置说明

编辑 `config.py` 修改配置：

```python
# LLM API配置
LLM_CONFIG = {
    "url": "API地址",
    "api_key": "你的API密钥",
    "model": "模型名称"
}

# MySQL配置
MYSQL_CONFIG = {
    "host": "数据库地址",
    "port": 3306,
    "user": "用户名",
    "password": "密码",
    "database": "oasis_system"
}
```

## 项目结构
```
Oasis_system/
├── README.md                  # 项目说明
├── config.py                  # 配置文件
├── prompts.py                 # LLM提示词模板
├── llm_client.py              # LLM客户端
├── storage.py                 # 数据存储
│
├── profile_engine.py          # 画像推演引擎
├── oasis_main.py              # 画像推演主程序
├── api_server.py              # API服务
│
├── social_platform.py         # 社交平台环境
├── agent.py                   # AI Agent系统
├── recommendation.py          # 推荐系统
├── simulation_engine.py       # 模拟引擎
├── oasis_simulation.py        # 社交模拟主程序
├── analyze_simulation.py      # 数据分析工具
│
├── requirements.txt           # 依赖列表
├── Dockerfile                 # Docker配置
└── run.sh                     # 运行脚本
```

## 注意事项
1. 确保LLM API密钥配置正确
2. MySQL数据库需提前创建（表会自动创建）
3. 推演过程需要调用多次LLM API，请注意API配额
4. 建议使用Redis缓存减少重复计算

## 使用示例

### 社交模拟示例

```bash
# 1. 运行模拟（自动生成 Agent）
python3.6 oasis_simulation.py

# 输入参数示例：
# Agent 数量: 50
# 模拟步数: 20
# 使用 LLM: n  (使用规则引擎，速度快)

# 2. 分析结果
python3.6 analyze_simulation.py

# 输出包括：
# - 用户统计（总数、平均粉丝数等）
# - 帖子统计（总数、互动数据等）
# - 影响力排行榜
# - 热门内容
# - 网络分析（密度、互惠关注率）
```

### 使用自定义 Agent 画像

```python
# 创建 profiles.json
[
    {
        "account_id": "tech_blogger_001",
        "name": "科技小王",
        "identity": "科技博主",
        "interests": ["AI", "编程", "科技"],
        "personality": {"type": "外向", "activity": "高"},
        "description": "关注AI和前沿科技"
    },
    {
        "account_id": "doctor_li",
        "name": "李医生",
        "identity": "医生",
        "interests": ["医疗", "健康", "养生"],
        "personality": {"type": "内向", "activity": "中"},
        "description": "三甲医院医生，分享健康知识"
    }
]

# 运行模拟
python3.6 oasis_simulation.py profiles.json
```

### 画像推演示例

```bash
# 1. 使用示例数据测试
python3.6 oasis_main.py example_input.json test_output.json

# 2. 启动API服务
python3.6 api_server.py

# 3. 调用API
curl -X POST http://localhost:5001/profile/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "test_001",
    "name": "测试账号",
    "identity": "学生",
    "description": "大学生，喜欢编程"
  }'
```

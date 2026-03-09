# OASIS 使用指南

## 目录
1. [快速开始](#快速开始)
2. [社交模拟详解](#社交模拟详解)
3. [账号画像推演](#账号画像推演)
4. [高级功能](#高级功能)
5. [常见问题](#常见问题)

---

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 运行测试
python3 quick_test.py
```

### 2. 第一次运行

```bash
# 使用默认配置运行社交模拟
python3 oasis_simulation.py

# 按提示输入：
# - Agent 数量: 20
# - 模拟步数: 10
# - 使用 LLM: n (推荐先用规则引擎)
```

### 3. 查看结果

```bash
# 分析模拟数据
python3 analyze_simulation.py

# 查看生成的文件
# - oasis_simulation.db: SQLite 数据库
# - simulation_results.json: 模拟结果
# - analysis_report.json: 分析报告
```

---

## 社交模拟详解

### 核心概念

**Agent（智能体）**
- 每个 Agent 代表一个社交媒体用户
- 拥有独特的身份、兴趣、性格
- 可以自主决策和执行行为

**社交平台**
- 模拟 Twitter/Reddit 环境
- 支持帖子、评论、点赞、关注等功能
- 实时更新的社交网络

**推荐系统**
- 基于兴趣的内容推荐
- 基于热度的内容推荐
- 用户关注推荐

### 使用示例

#### 示例 1: 小规模测试（快速）

```bash
python3 oasis_simulation.py

# 输入参数：
Agent 数量: 10
模拟步数: 5
使用 LLM: n
```

**预期结果：**
- 运行时间: ~5秒
- 生成约 10-20 条帖子
- 产生若干互动行为

#### 示例 2: 中等规模模拟

```bash
python3 oasis_simulation.py

# 输入参数：
Agent 数量: 50
模拟步数: 20
使用 LLM: n
```

**预期结果：**
- 运行时间: ~30秒
- 生成约 50-100 条帖子
- 形成初步的社交网络

#### 示例 3: 使用自定义 Agent

创建 `my_agents.json`:

```json
[
    {
        "account_id": "tech_001",
        "name": "科技博主小王",
        "identity": "科技博主",
        "interests": ["AI", "编程", "科技"],
        "personality": {"type": "外向", "activity": "高"},
        "description": "关注前沿科技，分享技术见解"
    },
    {
        "account_id": "doctor_002",
        "name": "李医生",
        "identity": "医生",
        "interests": ["医疗", "健康"],
        "personality": {"type": "内向", "activity": "中"},
        "description": "三甲医院医生，健康科普"
    }
]
```

运行：
```bash
python3 oasis_simulation.py my_agents.json
```

### Agent 行为类型

系统支持 13 种社交行为：

| 行为 | 说明 | 触发条件 |
|------|------|----------|
| CREATE_POST | 发布新帖子 | 随机或 LLM 决策 |
| CREATE_COMMENT | 评论帖子 | 看到感兴趣的内容 |
| LIKE_POST | 点赞帖子 | 认同内容 |
| DISLIKE_POST | 点踩帖子 | 不认同内容 |
| REPOST | 转发帖子 | 想分享给粉丝 |
| FOLLOW | 关注用户 | 发现感兴趣的用户 |
| UNFOLLOW | 取消关注 | 不再感兴趣 |
| MUTE | 屏蔽用户 | 不想看到某用户 |
| SEARCH_POSTS | 搜索帖子 | 主动寻找内容 |
| SEARCH_USER | 搜索用户 | 寻找特定用户 |
| VIEW_FEED | 查看信息流 | 日常浏览 |
| VIEW_TRENDING | 查看热门 | 了解热点 |
| DO_NOTHING | 什么都不做 | 不活跃时段 |

### 决策模式

#### 1. 规则引擎模式（推荐）

```bash
使用 LLM: n
```

**特点：**
- 速度快，成本低
- 基于预设规则决策
- 适合大规模模拟

**决策逻辑：**
- 随机选择行为类型
- 根据上下文生成参数
- 简单但有效

#### 2. LLM 决策模式

```bash
使用 LLM: y
```

**特点：**
- 更智能，更真实
- 基于 Agent 画像决策
- 需要 LLM API 支持

**决策逻辑：**
- 分析当前环境
- 结合 Agent 性格和兴趣
- 生成符合人设的行为

---

## 账号画像推演

### 基本用法

```bash
# 使用示例数据
python3 oasis_main.py

# 使用自定义数据
python3 oasis_main.py input.json output.json
```

### 输入格式

```json
{
    "account_id": "user_001",
    "name": "科技小王",
    "identity": "互联网从业者",
    "description": "985毕业，现在某大厂做产品经理",
    "verified_reason": "互联网公司产品经理"
}
```

### 输出示例

```json
{
    "account_id": "user_001",
    "status": "success",
    "profile": {
        "basic_info": {
            "data": {
                "real_name": "王某某",
                "gender": "男",
                "age_range": "25-35岁",
                "location": "一线城市",
                "occupation": "产品经理",
                "confidence": 0.85
            }
        },
        "identity_analysis": {...},
        "behavior_prediction": {...},
        "social_inference": {...},
        "content_preference": {...},
        "risk_assessment": {...}
    }
}
```

---

## 高级功能

### 1. 数据分析

```python
from analyze_simulation import SimulationAnalyzer

analyzer = SimulationAnalyzer("oasis_simulation.db")

# 获取完整分析
analysis = analyzer.analyze_all()

# 打印报告
analyzer.print_report()

# 导出报告
analyzer.export_report("my_report.json")
```

### 2. 自定义模拟

```python
from simulation_engine import SimulationEngine
from social_platform import PlatformType

# 创建引擎
engine = SimulationEngine(
    db_path="custom_sim.db",
    platform_type=PlatformType.TWITTER,
    max_workers=20
)

# 加载 Agent
profiles = [...]  # 你的 Agent 画像
engine.load_agents(profiles)

# 运行模拟
engine.run_simulation(steps=50, use_llm=False)

# 导出数据
engine.export_data("results.json")
```

### 3. 访问平台数据

```python
from social_platform import SocialPlatform

platform = SocialPlatform("oasis_simulation.db")

# 获取用户信息
user = platform.get_user_info("user_001")

# 获取用户信息流
feed = platform.get_user_feed("user_001", limit=20)

# 获取热门帖子
trending = platform.get_trending_posts(limit=10)

# 搜索内容
results = platform.search_posts("AI")

# 获取统计数据
stats = platform.get_statistics()
```

### 4. API 服务

```bash
# 启动 API 服务
python3 api_server.py
```

**API 端点：**

```bash
# 健康检查
curl http://localhost:5001/health

# 单个账号分析
curl -X POST http://localhost:5001/profile/analyze \
  -H "Content-Type: application/json" \
  -d '{"account_id": "test", "name": "测试", "identity": "用户"}'

# 批量分析
curl -X POST http://localhost:5001/profile/batch \
  -H "Content-Type: application/json" \
  -d '[{"account_id": "test1", ...}, {"account_id": "test2", ...}]'

# 获取画像
curl http://localhost:5001/profile/get/test
```

---

## 常见问题

### Q1: 模拟运行很慢怎么办？

**A:** 
- 使用规则引擎模式（不使用 LLM）
- 减少 Agent 数量
- 减少模拟步数
- 检查数据库文件大小

### Q2: 如何增加模拟的真实性？

**A:**
- 使用 LLM 决策模式
- 提供详细的 Agent 画像
- 增加模拟步数
- 调整 Agent 的兴趣和性格分布

### Q3: 数据库文件太大怎么办？

**A:**
```bash
# 删除旧数据库
rm oasis_simulation.db

# 或在运行时选择删除
python3 oasis_simulation.py
# 提示时输入 y 删除旧数据库
```

### Q4: 如何导出可视化数据？

**A:**
```bash
# 运行分析工具
python3 analyze_simulation.py

# 生成的 analysis_report.json 包含：
# - 用户排行榜
# - 热门内容
# - 网络分析
# - 活动时间线
```

### Q5: LLM API 调用失败怎么办？

**A:**
- 检查 `config.py` 中的 API 配置
- 确认 API Key 是否有效
- 检查网络连接
- 使用规则引擎模式作为备选

### Q6: 如何模拟特定场景？

**A:**
```python
# 例如：模拟信息传播
# 1. 创建一个有影响力的 Agent
# 2. 让它发布特定内容
# 3. 观察其他 Agent 的反应

from simulation_engine import SimulationEngine

engine = SimulationEngine()
engine.load_agents(profiles)

# 手动让某个 Agent 发帖
platform = engine.platform
platform.create_post("influencer_001", "重要消息：...")

# 继续模拟
engine.run_simulation(steps=20)
```

---

## 性能参考

| Agent 数量 | 模拟步数 | 模式 | 预计时间 | 生成帖子数 |
|-----------|---------|------|---------|-----------|
| 10 | 5 | 规则 | ~5秒 | 10-20 |
| 20 | 10 | 规则 | ~10秒 | 30-50 |
| 50 | 20 | 规则 | ~30秒 | 100-200 |
| 100 | 50 | 规则 | ~2分钟 | 500-1000 |
| 20 | 10 | LLM | ~5分钟 | 30-50 |

---

## 下一步

1. 尝试不同规模的模拟
2. 自定义 Agent 画像
3. 分析社交网络演化
4. 研究信息传播模式
5. 探索群体行为特征

祝你使用愉快！🎉

# 账号画像系统 (User Profile System)

多平台账号画像分析系统，支持实时数据处理、身份识别、意图分析和画像存储。系统从 RocketMQ 消费多平台用户数据，经过 LLM 身份识别、布隆过滤器去重、身份标准化映射等处理后，将结构化画像数据写入 OpenSearch，供下游业务查询和分析。

## 核心架构

### 统一身份判断管线（推荐）

`unified_identity_pipeline.py` 是当前线上运行的主管线，**单消费组、单容器**即可处理全部身份判断任务：

```
RocketMQ (spider_data)
        │
        ▼
┌─────────────────────────────────────────────┐
│  UnifiedListener (单 consumer)               │
│  消费组: unified_identity_consumer_group     │
│                                              │
│  每条消息依次匹配 4 个任务的关键词:           │
│  ├── 外卖员 (外卖员/外卖小哥/送外卖...)      │
│  ├── 快递员 (#快递)                          │
│  ├── 货车司机 (开货车/大货车/货车司机...)     │
│  └── 网约车司机 (网约车/跑滴滴/滴滴司机...)  │
│                                              │
│  命中 → 分发到对应任务 Worker 队列            │
└──────────────────┬──────────────────────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   Worker×10   Worker×10  Worker×10  (每任务 10 线程)
        │          │          │
        ▼          ▼          ▼
   LLM 身份判断 → community_filter 过滤 → ES 入库
```

### 配置驱动

所有任务参数在 `pipeline/task_configs.json` 中配置，新增身份判断只需：
1. 在 `utils/opinin_extract.py` 写判断函数
2. 在 `task_configs.json` 加一段配置
3. 重新 build 部署

### community 过滤器

`utils/community_filter.py` 在 LLM 判断后自动过滤非目标人群：

- **名称/简介关键词过滤**：商家、影视、广告、餐饮、美容、房产、教育、律师、医疗、汽车等 10 类
- **认证过滤**：商家认证、公司、机构、博主、创作者、自媒体、达人等（个人认证放行）
- **白名单校验**：community 不在 `["外卖员", "网约车司机", "货车司机", "快递员"]` 中则清空

## 目录结构

```
user_profile/
├── config/                    # 统一配置模块
│   ├── settings.py           # 分层配置管理器
│   └── validator.py          # 配置验证
├── utils/                     # 公共工具
│   ├── community_filter.py   # ★ community 标签过滤器（新增）
│   ├── about_log.py          # 统一日志工厂
│   ├── bloom.py              # 布隆过滤器（Redis 去重）
│   ├── data_processor.py     # 数据处理
│   ├── mq_client.py          # MQ 客户端
│   ├── identity_mapper.py    # 身份映射
│   ├── path_resolver.py      # 路径解析器
│   ├── es_updata_new.py      # OpenSearch 更新（含 age 字段清洗）
│   ├── http_llm_factory.py   # LLM API 客户端
│   ├── opinin_extract.py     # 身份判断函数（外卖/快递/货车/网约车）
│   └── prompts.py            # 提示词模板
├── pipeline/                  # 核心数据管线
│   ├── unified_identity_pipeline.py  # ★ 统一身份判断管线（线上主服务）
│   ├── task_configs.json     # ★ 任务配置（关键词/过滤规则/线程数）
│   ├── draw_and_to_es.py     # 旧管线（已被 unified 替代）
│   ├── identity_juge.py      # 旧管线
│   ├── identity_juge_tomq.py # 旧管线
│   └── data_to_es.py         # 批量迁移：MySQL → ES
├── analysis/                  # 分析模块
├── enterprise/                # 企业画像
├── migration/                 # 数据迁移
├── tools/                     # 辅助工具
├── dockerfiles/               # Docker 构建文件
│   ├── Dockerfile_unified_identity  # ★ 统一管线（线上使用）
│   ├── Dockerfile_draw_and_to_es
│   ├── Dockerfile_identity_juge
│   └── Dockerfile_identity_juge_tomq
├── tests/                     # 测试
├── build.sh                   # Docker 构建脚本
├── requirements.txt           # 依赖管理（Python 3.6 兼容）
├── ca.cer                     # SSL 证书
└── final_stanterd.xlsx        # 身份映射表
```

## 快速开始

### 部署（Docker + K8s）

```bash
# 构建并推送镜像
cd user_profile
bash build.sh

# 镜像地址
zhxgharbor.istarshine.com/dflow/unified_identity:0.0.1
```

在 Kuboard/K8s 中部署：
- 镜像：`zhxgharbor.istarshine.com/dflow/unified_identity:0.0.1`
- 副本数：1（可扩到 N，受 topic queue 数量限制）
- 无需环境变量，启动即运行全部 4 个任务

### 本地开发

```bash
cd user_profile
pip3.6 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 运行统一管线
python3.6 pipeline/unified_identity_pipeline.py
```

## task_configs.json 配置说明

```json
{
    "waimai": {
        "name": "外卖员身份判断",
        "bloom_key": "identity_bloom_key",
        "matcher_keywords": ["外卖员", "外卖小哥", "送外卖", ...],
        "identity_func": "get_kind",
        "content_mode": "content_only",
        "filter_verified": false,
        "consumer_group": "user_graph_uniq_user",
        "worker_threads": 10,
        "log_name": "waimai_pipeline",
        "community_filter": {
            "enabled": true,
            "junk_categories": ["shop", "media", "ad", ...],
            "filter_merchant_verified": true,
            "keep_personal_verified": true,
            "allowed_communities": ["外卖员", "网约车司机", "货车司机", "快递员"]
        }
    }
}
```

| 字段 | 说明 |
|------|------|
| `matcher_keywords` | actrie 关键词，内容命中才进入身份判断 |
| `identity_func` | 对应 `opinin_extract.py` 中的判断函数名 |
| `content_mode` | `content_only`=只看内容，`concat_all`=内容+简介+认证拼接 |
| `filter_verified` | 是否过滤已认证用户（快递员任务需要） |
| `worker_threads` | 该任务的 worker 线程数 |
| `community_filter.junk_categories` | 启用的过滤类别 |
| `community_filter.allowed_communities` | community 白名单 |

### 新增身份判断任务

1. 在 `utils/opinin_extract.py` 写 `get_kind_xxx(txt)` 函数
2. 在 `unified_identity_pipeline.py` 的 `IDENTITY_FUNC_MAP` 注册
3. 在 `task_configs.json` 加配置段
4. `allowed_communities` 白名单加上新社区名
5. 重新 `bash build.sh` 部署

## community_filter 过滤规则

### 过滤类别（junk_categories）

| 类别 key | 关键词示例 |
|----------|-----------|
| `shop` | 店、厂、公司、有限、商贸、超市 |
| `media` | 影视、短剧、小说、电影、剧情 |
| `ad` | 招聘、加盟、代理、推广、引流 |
| `food` | 餐饮、美食、奶茶、火锅、饭店 |
| `beauty` | 美容、护肤、美甲、美发、减肥 |
| `realestate` | 房产、装修、家具、建材 |
| `edu` | 教育、培训、驾校、课程 |
| `lawyer` | 律师、法律、律所 |
| `medical` | 医院、医生、诊所 |
| `car` | 汽车、4s、车行、修车、二手车 |

### 认证过滤关键词

商家/机构类：商家认证、店铺账号、公司、机构、企业、组织、事业单位

大V/博主类：博主、创作者、自媒体、达人、领域、作家、乘风计划、优质、原创

**放行**：空认证、含"个人"字样的认证

## 系统依赖

| 依赖项 | 说明 |
|--------|------|
| RocketMQ | 消息队列（基础镜像预装客户端） |
| Redis | 布隆过滤器去重 |
| OpenSearch | 画像数据存储（media_* 索引） |
| 火山引擎 LLM | 身份判断 API |

## 注意事项

- `rocketmq` C++ 客户端已预装在基础镜像中，**不要**从 pip 安装
- RocketMQ C++ 客户端不支持同进程多 consumer，统一管线用单 consumer + 内部分发解决
- 可水平扩展副本数，但不能超过 topic 的 queue 数量
- LLM 偶尔返回格式不规范的 JSON，已有 try/except 兜底，不影响服务运行
- `age` 字段已做清洗（"30岁" → 30），兼容 ES integer mapping

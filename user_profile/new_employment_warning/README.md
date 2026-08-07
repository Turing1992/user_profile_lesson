# 预警账号身份识别

从**人工预警索引** `artificial_warning_push_*` 取账号，判断身份并回写 `media_*` 画像索引。
覆盖 20 个标准身份，三新身份写 `community`、其余身份写 `identity`。

原先消费 RocketMQ `spider_data` 的实时管线（`pipeline/unified_identity_pipeline.py`）**已下线**，
现在是两路并行：

| | 增量路 | 历史路 |
|---|---|---|
| 入口 | `daily_identity_job.py` | `backfill_identity_job.py` |
| 调度 | K8s CronJob 每天一次 | 手动 / 一次性 Job，可跑几十小时 |
| 范围 | 昨天一天 | 指定年份索引 + 日期区间（倒序） |
| 账号去重 | 当天内 | **跨天 + 跨运行**（Redis 布隆） |
| 断点 | 不需要 | 按天记录，中断可续 |
| 判断逻辑 | ← 完全共用，口径一致 → | |

两路共用同一个镜像，靠启动命令区分。判断、门槛、回写全部复用同一套代码，
所以不存在两路口径不一致的问题。

本目录其余脚本是早期的分析/抽样工具，只出 JSONL/Excel，不写库。

判断算法统一走**线上阿里云百炼 `qwen3.5-flash`**（`llm_client.py` → `utils/http_llm_factory`），
与线上实时管线共用同一模型和密钥。`config.py` 里的火山引擎豆包配置已停用，仅为兼容历史脚本保留。

---

## 每日批量任务：daily_identity_job.py

每天运行一次，把指定日期（默认昨天）预警账号的身份算出来并回写画像索引。
一次性作业，跑完即退出，不订阅 MQ、不常驻进程。

### 流程

```
artificial_warning_push_*（按 publishTime 取指定日期，按小时切 24 片）
   │  ES 侧先用 136 个身份别名 multi_match/phrase 收敛候选
   │  （一天约 22 万帖 → 候选帖 4 万 → 去重账号 1.6 万）
   ▼
[账号去重]  key = 归一 site_name|author_persona.id，每账号最多留 3 条帖
   ▼
[平台映射]  siteName → 标准 site_name + media_* 索引（media_index_mapper）
            映射不到的（论坛/校圈/电视节目等）跳过并计入统计
   ▼
[粗预筛]    actrie 身份别名匹配 + 官号排除（纯本地，零成本）
   ▼
[资料回补]  批量查 media_*，补回预警索引缺失的 description / verified_reason
            同一次查询结果复用于后续新旧账号判定，不重复查
   ▼
[严格预筛]  逐帖做本人身份直接信号校验，选出信噪比最高的一条帖
   ▼
[模型判断]  一次调用覆盖 20 个标准身份 + 证据接地校验
   ▼
[身份门槛]  每个身份过专属职业锚点门槛（identity_gates.py）
            三新四类再叠加 judge.py 的职业硬门槛
   ▼
[回写]      三新 → community（同时写 three_new_identity）
            其他 → identity；identity_standerd 统一由 final_stanterd.xlsx 映射
            已有账号只 update 身份字段；新账号按 media_* mapping 完整 index
   ▼
output/daily_identity_*.jsonl + .xlsx（运行汇总 / 身份分布 / 身份明细）
```

### 运行

```bash
# 在 user_profile 目录下

# 跑昨天全量并回写（生产默认）
python3 -m new_employment_warning.daily_identity_job

# 指定日期，只判断不写库（上线前建议先这样验证）
python3 -m new_employment_warning.daily_identity_job --date 2026-08-02 --dry-run

# 小样本验证
python3 -m new_employment_warning.daily_identity_job \
  --date 2026-08-02 --max-accounts 300 --max-judge 40 --dry-run
```

| 参数 | 说明 |
|------|------|
| `--date` | 目标日期 `yyyy-MM-dd`，默认昨天 |
| `--start` / `--end` | 自定义时间窗，优先于 `--date` |
| `--max-accounts` | 账号数上限；达到后立即停止翻页 |
| `--max-judge` | 模型调用次数上限 |
| `--workers` | 模型并发数，默认 `JOB_CONFIG.judge_workers`（16） |
| `--dry-run` | 只判断不写库 |
| `--output` | 报告输出路径（xlsx，同名 jsonl 为明细） |

`JOB_CONFIG` 里另有几个影响稳定性的参数：`window_hours`（时间分片粒度，默认 1）、
`page_size`（默认 300）、`es_timeout`（默认 300 秒）、`es_retries`（默认 2 次）。

### 身份专属硬门槛（identity_gates.py）

只靠模型 + 通用自述校验会把「沾边」账号放进画像，实测偏松的真实案例：
只写「劳动维权找我」的代理人被判律师、做升学咨询的中介被判教师、
账号名「AAA老鼠肉批发——张总」被判学生。

所以模型返回并通过证据接地后，**每个身份**还要再过一道确定性门槛（纯规则、零调用）：

| 检查 | 说明 |
|------|------|
| 商家/机构账号名 | 账号名含 批发/科技/传媒/有限/集团/基地/店/加盟 等，**对所有身份**一律否决 |
| 领域经营主体 | 如「工人」否决账号名含 工程/公司/劳务；「农民」否决 农资/种业/合作社 |
| `reject_any` | 同领域但不同角色的否决词，如教师否决 升学规划/招生咨询/美甲/驾校 |
| `require_any` | 必须命中职业锚点词：资格（执业律师/律师事务所/教师资格证）、场所（工地/车间/医院/学校）、工作动作（派件/接单/种地） |
| 歧义泛称配对 | 「农民工」「打工」「务工」单独出现不算，必须另有具体劳动场景词 |

三新四类在此之上再叠加 `judge.passes_new_employment_hard_gate`，通过条件三者之一：
账号名带职业标签、第一人称直接自述职业（「本人外卖骑手」）、职业词 + 第一人称从业动作。

被拦掉的记录会写进报告的**门槛拦截明细** sheet（含拦截原因、证据、简介），
方便反向复核门槛是否过严。新增标准身份时必须同步补门槛配置，
`tests` 里有守护测试会在漏配时失败。

收紧效果（2026-08-02，4000 账号 / 260 次模型调用）：

```
收紧前命中 89 条 → 收紧后 46 条，拦截 48 条
律师 26→12（保留的全部有「执业律师 / 律师事务所 / 主任律师」资格证据）
教师  8→3（保留的是「音乐教师资格证」「小学数学老师」「职业教师」）
老人  7→0（原命中多为「难道老年人就活该被坑吗」这类指代群体，非本人自述）
学生  6→2、家长 7→2、农民 13→9、工人 5→3
```

### 写入口径

| 判定身份 | 写入字段 | 说明 |
|---------|---------|------|
| 外卖员 / 快递员 / 网约车司机 / 货车司机 | `community` | 同时写 `three_new_identity` = 平台配送与运输从业者 |
| 其余 16 个标准身份 | `identity` | 家长/医护人员/教师/学生/老人/农民/牧民/工人/律师/公务员/事业单位工作人员/警察/退役军人/家政服务人员/餐饮从业者/维修人员 |
| 全部命中身份 | `identity_standerd` | 由 `final_stanterd.xlsx` 标准化，如 网约车司机→司机、外卖员→外卖骑手 |

- **已有账号**：只 `update` 上面这几个身份字段 + `update_time`，
  绝不覆盖爬虫侧维护的账号资料字段；
- **新账号**：按 `media_*` mapping 构造完整文档 `index`，
  字段名与类型对齐（`age` 为 integer、`followers_count` 为 long，空值不写）。

### 部署（K8s CronJob）

```bash
cd user_profile && bash build.sh
# 镜像：zhxgharbor.istarshine.com/dflow/warning_daily_identity:0.0.1
```

一次性作业，用 CronJob 调度，**不要**用 Deployment 常驻：

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: warning-daily-identity
spec:
  schedule: "30 3 * * *"          # 每天 03:30 跑前一天
  concurrencyPolicy: Forbid       # 上一次没跑完就跳过，避免重复写
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: warning-daily-identity
              image: zhxgharbor.istarshine.com/dflow/warning_daily_identity:0.0.1
              # 默认 CMD 即跑昨天全量；要试跑加 --dry-run
              # args: ["-m","new_employment_warning.daily_identity_job","--dry-run"]
```

### 实测数据（2026-08-02 全量，线上真实环境）

一天全量跑完约 **16 分钟**，模型调用 2339 次，可作为 CronJob 资源与超时的参考：

```
24 个时间窗 → 候选帖 41968（其中 OCR/ASR 派生文本跳过 20359）
  → 去重账号 16458（平台无对应画像索引跳过 117）
  → 粗预筛通过 16270（已有账号 15882 / 新账号 388，资料回补 9853 个字段）
  → 严格预筛通过 2339 → 全部送模型
  → 命中身份账号 849（三新职业硬门槛额外拦截 27）
  → 835 条 update + 14 条 insert，失败 0
耗时 940 秒
```

20 类标准身份全部有命中：

| 身份 | 账号数 | 身份 | 账号数 | 身份 | 账号数 |
|---|---|---|---|---|---|
| 律师 | 173 | 老人 | 34 | 网约车司机 | 5 |
| 农民 | 145 | 医护人员 | 34 | 公务员 | 4 |
| 家长 | 95 | 外卖员 | 23 | 牧民 | 3 |
| 教师 | 83 | 货车司机 | 15 | 快递员 | 3 |
| 学生 | 68 | 家政服务人员 | 13 | 警察 | 2 |
| 退役军人 | 67 | 维修人员 | 11 | 事业单位工作人员 | 1 |
| 工人 | 65 | 餐饮从业者 | 6 | | |

小样本真实写入核对：36 个账号 **36/36** 身份字段读回与预期完全一致
（另一批 88 个账号同样 88/88 一致）。

### 为什么要按时间分片

最初实现是在整天的时间窗里用 `search_after` 一路翻页，全量跑会 **ES 读超时失败**：
一天候选集 4 万+ 帖，深度分页越翻越慢；同时把「136 个别名 × 3 个字段」展开成
408 条 `match_phrase` 子句，单次查询解析打分开销过大。

现在做了两处改造：

- 按 `JOB_CONFIG.window_hours`（默认 1 小时）切成 24 片，每片只有一两千条、翻页很浅；
- 每个别名用一条 `multi_match` + `type: phrase` 跨三字段表达，子句数 408 → 136。

另外 ES 请求带 `es_timeout`（默认 300 秒）和 `es_retries`（默认 2 次）重试，
偶发超时不会让整个任务失败。

### 几个必须知道的数据事实

- **预警索引的 `author_persona` 没有 `description` 和 `verified_reason`**，
  只有 name/id/verified/verified_type/gender/ip_region/his_location/cpt_location。
  这两个字段对官号识别和身份判断很关键（简介写着"三甲医院儿科医师"这类），
  所以流程里专门有一步从 `media_*` 回补。
- **`siteName|author_persona.id` 与 `media_*` 的 `_id` 规则一致**，抽样命中 19~20/20，
  说明绝大多数预警账号已存在于画像索引，主路径是 update 而非 insert。
- **百度系（百度百家/有驾/好看视频/度小视）和 UC 系的 uid 跨子站通用**，
  同一账号在 `media_baidu` 里可能以另一个 `site_name` 存在。因此判断账号是否已存在
  分两步：先按 `site_name|uid` mget，未命中的再按 `uid` 兜底查一次，避免重复插入。
- **`publishTime` 存在未来日期的脏数据**，按日期取数时会体现在当天统计里。
- 时间字段只有 `publishTime`，没有入库时间，所以任务按发布时间划分当天，
  重跑同一天是幂等的（身份字段覆盖写）。

---

## 历史回溯：backfill_identity_job.py

把历史数据补算出来。与增量路共用全部判断逻辑，只在取数范围和运行策略上不同。

### 规模（实测）

```
预警索引 2020~2026 共 7 个，1.46 亿条帖
2025 单年：候选帖 1116 万 → 身份词候选唯一账号 528 万
2026 至今：候选帖  899 万 → 身份词候选唯一账号 404 万
```

按增量路实测的严格预筛通过率（约 14%）推算，2025+2026 两年约 **133 万次模型调用**。
所以回溯设计的重点全在控成本：

- **跨天 + 跨运行账号去重**：同一账号在历史上会反复出现，去重后 2025 年
  1116 万条候选帖只对应 528 万个账号。用 Redis 布隆过滤器
  （`BACKFILL_CONFIG.bloom_key`），多次运行、多个副本共享状态，重跑不重复消耗；
- **跳过已有身份**：`media_*` 里已经有 `identity` / `community` 的账号默认跳过
  （实测能跳掉约 40%），用 `--no-skip-existing` 可关闭；
- **日期倒序**：从最近往最早跑，中途停下时已完成的是价值最高的近期数据；
- **断点续跑**：按天记录，中断后原样重跑会跳过已完成日期（实测重跑耗时 0 秒）；
- **调用上限**：`--max-judge-total` 达到即停并保存断点，便于分批控制成本。

### 运行

```bash
# 1) 先小样本试跑，不写库
python3 -m new_employment_warning.backfill_identity_job \
  --index artificial_warning_push_2026 \
  --start-date 2026-07-27 --end-date 2026-07-30 \
  --max-accounts-per-day 400 --max-judge-per-day 10 \
  --window-hours 24 --dry-run

# 2) 正式回溯 2026（可随时 Ctrl+C，重跑自动续）
python3 -m new_employment_warning.backfill_identity_job \
  --index artificial_warning_push_2026 \
  --start-date 2026-01-01 --end-date 2026-12-31 \
  --window-hours 6 --workers 24

# 3) 分批控成本：本次只跑 5 万次模型调用就停
python3 -m new_employment_warning.backfill_identity_job \
  --index artificial_warning_push_2025 \
  --start-date 2025-01-01 --end-date 2025-12-31 \
  --max-judge-total 50000
```

| 参数 | 说明 |
|------|------|
| `--index` | 源索引，按年切换（`artificial_warning_push_2025` 等） |
| `--start-date` / `--end-date` | 日期区间，实际从 end 倒序跑到 start |
| `--max-judge-total` | 本次运行模型调用总上限，达到即停（断点已存，可续） |
| `--max-judge-per-day` | 单日模型调用上限 |
| `--max-accounts-per-day` | 单日收集账号上限。**会提前停止扫描**，跑得快但会漏账号；追求全量覆盖时不要设 |
| `--window-hours` | 时间分片粒度，回溯建议 6 或 24（默认 1，窗口查询次数太多） |
| `--no-skip-existing` | 不跳过已有身份的账号，全部重算 |
| `--no-dedup` | 关闭跨天去重（不推荐，会重复消耗调用） |
| `--bloom-key` | 去重 Redis key；**换算法口径要整体重算时换一个** |
| `--checkpoint` | 断点文件路径 |
| `--dry-run` | 只判断不写库 |

### 耗时预期

瓶颈不在模型而在 ES 扫描：即使 `--max-judge-per-day` 设得很小，
默认也要把当天全部候选帖扫完才能确定哪些是新账号。实测单日全量扫描 5~8 分钟，
一年约 30~48 小时**光扫描**。所以回溯要么接受长跑（配断点分批），
要么用 `--max-accounts-per-day` 牺牲部分覆盖换速度。

建议做法：用一次性 Job 跑，配合 `--max-judge-total` 分几批，
每批跑完看一眼 `output/backfill/` 里的明细再继续。

### K8s 一次性 Job

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: warning-backfill-2026
spec:
  backoffLimit: 0            # 失败不自动重试，避免重复写；断点续跑靠手动重建
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: backfill
          image: zhxgharbor.istarshine.com/dflow/warning_daily_identity:0.0.2
          args:
            - "-m"
            - "new_employment_warning.backfill_identity_job"
            - "--index=artificial_warning_push_2026"
            - "--start-date=2026-01-01"
            - "--end-date=2026-12-31"
            - "--window-hours=6"
            - "--workers=24"
```

断点文件在容器内 `output/backfill/`，Pod 销毁即丢。**要跨 Pod 续跑必须挂 PVC**，
否则重建 Job 会从头再跑一遍（账号级去重仍然生效，靠 Redis 布隆兜底，
所以不会重复消耗模型调用，只会重复扫描 ES）。

---

## 早期分析脚本（只出报表，不写库）

以下脚本是需求前期做算法验证和分布统计用的，保留备查。
它们**不回写 `media_*`**，输出都在 `output/`。

### scan.py 数据流（只判三新四类，不写库）

```
artificial_warning_push_2026
   │  _source: url / content / title / siteName / author_persona{name,id,...}
   ▼
[抽取]  平台=siteName  账号id=author_persona.id  name=author_persona.name
   ▼
[去重]  key = "平台|id"，同一账号只判断一次
   ▼
[判断]  输入 = 标题 + 正文 + 账号名  →  qwen3.5-flash（合并四类严格规则）
        + community_filter 兜底过滤（商家/机构/影视小说等）
   ▼
[命中]  identity2 ∈ {外卖员,网约车司机,货车司机,快递员}
        解析 target_index：siteName → media_*（复用 es_updata_new 映射）
   ▼
output/hits_*.jsonl   ← 供后续写入 media_* 使用
```

### 三新判断算法说明（证据接地版，judge.py）

- 在 `utils/opinin_extract.py` 四类判断（promts3~6）规则基础上重写，合并为**单次**
  大模型调用；模型：线上阿里云百炼 `qwen3.5-flash`（经 `llm_client.py`）。
- **核心原则：只认「直接证据」，禁止情境推断。** 判定为四类之一必须能原文引用一条：
  - A 本人自述职业身份（"我是外卖员/我跑滴滴/我是货车司机"）
  - B 本人自述从业工作行为（"我跑了30单""我拉了一车货没收到运费"）
  - C 账号名/话题标签带明确职业标签且内容不矛盾（"#外卖员 #货运"）
- **明确排除**：仅有情境线索（堵车/塌方/开了一路车/压车/加运费）、交通工具≠职业
  （骑电动车/开车）、消费者、他人、新闻小说短剧、广告招聘。
- **三重兜底防误判/幻觉**：
  1. 正文超 200 字直接判非目标（多为新闻长文，省一次调用）
  2. `evidence` 证据接地校验：证据句必须真实出现在原文（最长公共子串≥4），
     否则视为模型编造，判"其他"（防止 LLM 幻觉出原文没有的证据）
  3. `utils/community_filter.CommunityFilter` 过滤商家/机构认证账号
- 输出新增 `evidence`（证据原文）字段，便于人工快速核对每条判定的依据。

## 输出字段（hits_*.jsonl，每行一条）

| 字段 | 说明 |
|------|------|
| `id` | `平台\|uid`，与 `media_*` 索引 `_id` 规则一致 |
| `platform` | siteName，如「抖音」 |
| `uid` | author_persona.id |
| `name` | 账号名 |
| `url` | 命中帖文 url |
| `identity` | 固定「平台配送与运输从业者」 |
| `community` | 外卖员 / 网约车司机 / 货车司机 / 快递员 |
| `evidence` | 支撑判定的原文证据句（已做接地校验） |
| `log` | 大模型判断原因 |
| `target_index` | 目标 `media_*` 索引；`null` 表示 siteName 无对应索引 |

## 运行

```bash
# 在 user_profile 目录下

# 小样本验证（推荐先跑）
python3 -m new_employment_warning.scan --max-docs 500

# 全量扫描 2026 预警索引
python3 -m new_employment_warning.scan

# 换年份 / 指定输出
WARNING_SOURCE_INDEX=artificial_warning_push_2025 python3 -m new_employment_warning.scan --output /tmp/hits.jsonl

# 单独自测判断算法
python3 -m new_employment_warning.judge
```

## 配置（`config.py`）

- `SOURCE_INDEX`：源预警索引（默认 `artificial_warning_push_2026`，可用环境变量 `WARNING_SOURCE_INDEX` 覆盖）
- `JOB_CONFIG`：**每日批量任务参数**（页大小 / 每账号帖数 / 正文上限 / 并发 / 上限）
- `SCAN_CONFIG.batch_size / judge_workers / max_docs / skip_text_over`：早期 scan 脚本的参数
- `SITENAME_TO_MEDIA_INDEX`：早期的 siteName → media_* 映射（**只做精确匹配**，
  带栏目后缀的平台名会漏。每日任务用的是 `media_index_mapper.py`，
  支持后缀截断与别名，并以 `media_*` 里真实存在的 `site_name` 取值为准）
- `LLM_API_KEY / LLM_API_URL / LLM_MODEL / LLM_TIMEOUT`：**已停用**的火山引擎豆包配置，
  仅为兼容历史脚本保留；实际调用参数见 `utils/http_llm_factory.py`

## 待办（后续）

- [x] `media_*` 写入/更新逻辑 → 已由 `daily_identity_job.py` + `media_writer.py` 实现
- [ ] 大规模跑批时的断点续跑（当前单次运行内存去重，重跑同一天是幂等的）
- [ ] 教师判定的边界收敛：升学中介、招生咨询类"老师"仍可能被判为教师
      （与 `media_*` 既有口径一致，暂未收紧）


## 通用身份扩展（20 个标准身份）

`general_judge.py` 提供 18 个业务组、20 个标准身份的判断：家长、医护人员、教师、学生、
老人、农民、牧民、工人、律师、公务员、事业单位工作人员、警察、退役军人、外卖员、快递员、
网约车司机、货车司机、家政服务人员、餐饮从业者、维修人员。

它同时被两个入口使用：

- `daily_identity_job.py`：每日批量任务，**会回写 `media_*`**；
- `collect_general_identities.py`：限量抽样导出，只出 Excel 供人工复核，不写库。

通用判断算法采用以下保护措施：

- 模型调用前要求账号资料有明确身份，或正文存在「第一人称 + 身份」直接表述；
- 模型返回后再做标准标签白名单、证据原文接地和确定性规则校验；
- 明确机构/官方账号直接排除（平台认证类型 + 机构名后缀 + 认证说明）；
- 第一人称自述识别排除三类干扰：指向他人（"我朋友是医生"）、
  反问质问（"难道老年人就活该被坑吗"）、比喻贬称（"你拿我当送外卖的"）；
- prompt 明确泛称归类：「打工人」「上班族」「搬砖」不算身份；
  「农民工」按实际工作判工人或农民，不一律判农民。

`collect_general_identities.py` 额外采用限量随机查询（`size=300`、
`terminate_after=50000`、不用 scroll），只输出 JSONL 和带人工复核列的 Excel：

```bash
# 在 user_profile 目录下运行；默认全部业务组，每组目标5个账号
python3 -m new_employment_warning.collect_general_identities

# 先验证宝妈/家长、医护和教师，每组5个账号
python3 -m new_employment_warning.collect_general_identities \
  --groups 家长,医护人员,教师 --per-group 5

# 指定结果文件；同名 JSONL 会保存检查点，重复执行可断点续跑
python3 -m new_employment_warning.collect_general_identities \
  --output new_employment_warning/output/通用身份预警复核.xlsx
```

Excel 包含 `运行汇总`、`类别统计`、`身份明细`，明细预留 `人工复核`、
`是否建议入库`、`复核备注` 三列。该脚本本身不写库，用于抽查算法表现。


## 按时间窗口统计账号唯一身份分布

`time_unique_identity_distribution.py` 用于统计指定时间段内预警账号的唯一主身份分布。
账号按 `siteName|author_persona.id` 去重，全部身份词进入同一个候选池，再按账号键哈希分区抽样；
每个账号最多调用一次模型。若模型识别出多个身份，按照“当前具体职业优先、社会角色其次、
年龄身份最后”的固定优先级选择唯一主身份；未通过证据校验的账号归为“其他/无明确身份”。
官号过滤在模型调用前执行：优先匹配已校准的平台认证类型，并结合认证说明和已认证账号的
机构型名称判断。命中政府、公安、交警、检察、法院、消防、政务发布等官号/机构账号时，
不调用模型且不计入任何个人身份；认证状态本身不会被直接当作机构，避免误删认证个人。

```bash
python3 -m new_employment_warning.time_unique_identity_distribution \
  --start '2026-07-20 00:00:00' \
  --end '2026-07-27 23:59:59' \
  --output new_employment_warning/output/预警账号唯一身份分布_20260720_至今.xlsx
```

该统计不使用 scroll、不逐条扫描全部帖子、不更新 `media_*`。最终每个账号只属于一个身份，
所有身份的估算账号数之和严格等于时间窗口内的唯一账号总数。


### 按日期输出唯一身份数量

```bash
python3 -m new_employment_warning.daily_unique_identity_distribution \
  --start-date 2026-07-20 --end-date 2026-07-27 \
  --output new_employment_warning/output/预警账号唯一身份按日期分布_20260720_至今.xlsx
```

每天独立按 `平台|账号ID` 去重，同一天一个账号只保留一个主身份。跨日期重复活跃的账号会分别
计入对应日期。输出包含日期身份长表、数量透视表、占比透视表和每日抽样明细。

# 身份自动识别系统

基于LLM的用户身份自动识别和分析系统，支持从OpenSearch数据源获取数据，使用自定义提示词进行身份识别，并生成Excel分析报告。

## 功能特性

- **Web界面管理**: 提供友好的Web界面创建和管理识别任务
- **自定义提示词**: 支持自定义LLM提示词，默认提供网约车司机识别模板
- **数据源集成**: 从OpenSearch中根据关键词搜索相关用户发帖数据
- **并行处理**: 支持多线程并行处理，提高处理效率
- **结果导出**: 自动生成包含识别结果和统计信息的Excel报告
- **任务管理**: 完整的任务生命周期管理（创建中→测试中→创建完成）

## 系统架构

```
identity_auto_get/
├── api.py              # Flask API服务
├── database.py         # 数据库操作
├── data_processor.py   # 数据处理和并行执行
├── run.py             # 启动脚本
├── requirements.txt   # 依赖包
├── templates/         # Web模板
│   └── index.html
├── static/           # 静态资源
│   └── app.js
└── results/          # 结果文件存储
```

## 安装部署

### 1. 环境要求

- Python 3.6+
- MySQL 数据库
- OpenSearch/Elasticsearch (可选)

### 2. 安装依赖

```bash
cd identity_auto_get
pip install -r requirements.txt
```

### 3. 配置数据库

确保 `utils/config.py` 中的 `sql_config` 配置正确：

```python
sql_config = {
    "host": "192.168.19.65",
    "user": "buser", 
    "password": "p3jnmja3",
    "database": "user_profile"
}
```

### 4. 启动系统

```bash
python run.py
```

系统将在 http://localhost:5000 启动Web界面。

## 使用说明

### 1. 创建识别任务

1. 访问Web界面
2. 填写任务信息：
   - **匹配关键词**: 用于搜索数据的关键词（如：网约车,滴滴,司机）
   - **身份名称**: 要识别的身份类型（如：网约车司机）
   - **创建人**: 任务创建者姓名
   - **提示词**: 可选，留空使用默认网约车司机识别提示词

3. 点击"创建并开始处理"

### 2. 监控任务进度

- 任务状态会实时更新：创建中 → 测试中 → 创建完成
- 页面每30秒自动刷新任务状态
- 可点击"查看详情"查看任务完整信息

### 3. 下载结果

任务完成后，点击"下载结果"获取Excel分析报告，包含：
- **身份识别结果**: 每条数据的识别结果和判断原因
- **统计信息**: 识别成功率、身份分布等统计数据

## API接口

### 创建任务
```
POST /api/tasks
Content-Type: application/json

{
    "match_keywords": "网约车,滴滴",
    "identity_name": "网约车司机", 
    "creator": "张三",
    "prompt_text": "自定义提示词(可选)"
}
```

### 获取任务列表
```
GET /api/tasks?creator=张三
```

### 获取任务详情
```
GET /api/tasks/{task_id}
```

### 下载结果文件
```
GET /api/tasks/{task_id}/download
```

## 数据库表结构

```sql
CREATE TABLE identity_auto_table (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prompt_text TEXT NOT NULL COMMENT '提示词',
    match_keywords VARCHAR(500) NOT NULL COMMENT '匹配关键词', 
    identity_name VARCHAR(200) NOT NULL COMMENT '身份名称',
    task_status ENUM('创建中', '测试中', '创建完成') DEFAULT '创建中',
    creator VARCHAR(100) NOT NULL COMMENT '创建人',
    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    result_file_path VARCHAR(500) COMMENT '结果文件路径'
);
```

## 技术栈

- **后端**: Flask + MySQL + OpenSearch
- **前端**: Bootstrap 5 + Vanilla JavaScript  
- **数据处理**: Pandas + OpenPyXL
- **LLM集成**: 基于现有的 `utils.opinin_extract.identity_auto` 函数
- **并发处理**: ThreadPoolExecutor

## 注意事项

1. **LLM配置**: 确保 `utils/opinin_extract.py` 中的LLM API配置正确
2. **数据源**: 系统会优先从OpenSearch获取数据，失败时使用模拟数据
3. **并发限制**: 默认使用10个并发线程，可根据服务器性能调整
4. **文件存储**: 结果文件存储在 `results/` 目录下
5. **日志记录**: 系统日志记录在 `identity_auto_system.log` 文件中

## 故障排除

### 常见问题

1. **数据库连接失败**: 检查 `utils/config.py` 中的数据库配置
2. **OpenSearch连接失败**: 检查 `config/config.py` 中的ES配置，系统会自动降级到模拟数据
3. **LLM调用失败**: 检查 `utils/opinin_extract.py` 中的API配置和网络连接
4. **端口占用**: 修改 `run.py` 中的端口配置

### 日志查看

```bash
tail -f identity_auto_system.log
```

## 扩展开发

系统采用模块化设计，可以轻松扩展：

- **数据源**: 修改 `data_processor.py` 中的 `data_get` 方法
- **识别逻辑**: 修改 `utils/opinin_extract.py` 中的 `identity_auto` 函数
- **前端界面**: 修改 `templates/index.html` 和 `static/app.js`
- **API接口**: 在 `api.py` 中添加新的路由
# 意图识别系统 (Intent Recognition System)

基于MCP的意图识别系统，用于分析特定事件的参与账号群体。

## 功能特性

- **需求拆解**: 将输入需求自动拆解为三元组 (主体-谓词-客体)
- **关键词检索**: 基于三元组关键词在数据库中进行检索
- **账号聚合**: 输出参与事件评论的特定账号集合
- **MCP集成**: 使用Model Context Protocol进行模型交互

## 系统架构

```
输入事件 → 三元组拆解 → 关键词提取 → 数据库检索 → 账号聚合 → 结果输出
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动MCP服务器
python mcp_server.py

# 运行意图识别
python intent_analyzer.py
```
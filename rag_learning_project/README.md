# RAG 学习项目 - 智能文档问答系统

这是一个完整的RAG（Retrieval-Augmented Generation）学习项目，通过构建一个智能文档问答系统来深入理解RAG的工作原理。

## 🎯 项目目标

通过这个项目，你将学会：
- RAG的核心概念和工作流程
- 文档处理和分块策略
- 向量化和相似度检索
- 提示工程和上下文增强
- 完整的RAG系统架构

## 🏗️ 系统架构

```
用户问题 → 向量化 → 相似度检索 → 上下文增强 → LLM生成 → 答案返回
    ↑                    ↓
文档库 → 分块 → 向量化 → 向量数据库
```

## 📁 项目结构

```
rag_learning_project/
├── app.py                 # 主应用程序
├── rag_system.py         # RAG核心系统
├── document_processor.py # 文档处理模块
├── vector_store.py       # 向量存储模块
├── llm_client.py         # LLM客户端
├── templates/
│   └── index.html        # Web界面
├── documents/            # 文档存储目录
├── vector_db/           # 向量数据库目录
├── requirements.txt     # 依赖包
└── README.md           # 说明文档
```

## 🚀 快速开始

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 运行应用：
```bash
python app.py
```

3. 访问 http://localhost:5000 开始使用

## 📚 学习路径

1. **理解RAG概念** - 阅读代码注释和文档
2. **上传文档** - 体验文档处理和向量化过程
3. **提问测试** - 观察检索和生成过程
4. **调试分析** - 查看中间结果和日志
5. **参数调优** - 尝试不同的配置参数
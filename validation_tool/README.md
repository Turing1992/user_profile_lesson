# OpenSearch 数据验证工具

这是一个用于快速验证 OpenSearch 数据的 Web 工具，可以帮助人工验证查询结果的准确性。

## 功能特性

- **UID 查询**: 在 media_* 索引中查询指定 UID
- **结果展示**: 显示查询到的 community 字段和相关信息
- **人工验证**: 提供"正确"和"错误"按钮进行人工判断
- **统计功能**: 
  - 自动记录总查询数、正确数、错误数
  - 计算召回率（正确数/总查询数）
  - 计算准确率（正确数/(正确数+错误数)）
  - 重置功能
- **实时更新**: 统计数据实时更新显示

## 文件结构

```
validation_tool/
├── validation_app.py      # Flask 后端服务器
├── templates/
│   └── index.html        # 前端页面
├── requirements.txt      # Python 依赖包
├── run.sh               # 启动脚本
├── README.md            # 说明文档
└── ca.cer              # SSL 证书文件（需要复制）
```

## 部署步骤

1. **复制 SSL 证书**
   ```bash
   cp ../ca.cer ./ca.cer
   ```

2. **运行启动脚本**
   ```bash
   chmod +x run.sh
   ./run.sh
   ```

3. **访问工具**
   打开浏览器访问: `http://localhost:5000`

## 使用流程

1. 在输入框中输入 UID
2. 点击"查询"按钮
3. 查看返回的 community 字段结果
4. 根据结果准确性点击"正确"或"错误"按钮
5. 查看下方统计信息，包括召回率和准确率
6. 可以随时重置统计数据重新开始

## 配置说明

OpenSearch 连接配置在 `validation_app.py` 中：

```python
opensearch_config = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": 'ca.cer',
    "timeout": 30
}
```

## 数据存储

- 统计数据保存在 `validation_stats.json` 文件中
- 重启服务后数据不会丢失
- 可以通过"重置"按钮清空所有统计数据

## 技术栈

- **后端**: Flask + OpenSearch Python Client
- **前端**: HTML + CSS + JavaScript
- **数据存储**: JSON 文件

## 注意事项

- 确保 `ca.cer` 证书文件存在于工具目录中
- 服务默认运行在 5000 端口
- 查询结果限制显示前 10 条记录
- 支持 Enter 键快速查询
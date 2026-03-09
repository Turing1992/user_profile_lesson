#!/bin/bash

# 数据验证工具启动脚本

echo "正在启动数据验证工具..."

# 检查Python版本
python_cmd="python3"
if command -v python3.6 &> /dev/null; then
    python_cmd="python3.6"
elif command -v python3 &> /dev/null; then
    python_cmd="python3"
else
    echo "错误: 未找到Python3"
    exit 1
fi

echo "使用Python命令: $python_cmd"

# 安装依赖
echo "安装依赖包..."
$python_cmd -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 检查ca.cer文件是否存在
if [ ! -f "ca.cer" ]; then
    echo "警告: ca.cer 文件不存在，请确保SSL证书文件在当前目录"
fi

# 启动服务
echo "启动验证服务器..."
echo "访问地址: http://localhost:5000"
echo "按 Ctrl+C 停止服务"

$python_cmd validation_app.py
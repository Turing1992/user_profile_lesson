#!/bin/bash
# Oasis系统运行脚本

echo "======================================"
echo "Oasis 账号画像推演系统"
echo "======================================"

# 检查Python版本
if ! command -v python3.6 &> /dev/null; then
    echo "错误: 未找到 python3.6，请先安装"
    exit 1
fi

# 安装依赖
echo "检查依赖..."
pip3.6 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 创建日志目录
mkdir -p logs

# 运行系统
if [ $# -eq 0 ]; then
    echo "使用示例数据运行..."
    python3.6 oasis_main.py example_input.json
elif [ $# -eq 1 ]; then
    echo "使用输入文件: $1"
    python3.6 oasis_main.py "$1"
elif [ $# -eq 2 ]; then
    echo "使用输入文件: $1, 输出文件: $2"
    python3.6 oasis_main.py "$1" "$2"
else
    echo "用法: ./run.sh [输入文件.json] [输出文件.json]"
    exit 1
fi

echo "======================================"
echo "运行完成"
echo "======================================"

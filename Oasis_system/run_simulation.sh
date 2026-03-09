#!/bin/bash
# OASIS 社交模拟快速启动脚本

echo "================================"
echo "OASIS 社交模拟平台"
echo "================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3"
    exit 1
fi

# 安装依赖（如果需要）
if [ "$1" == "install" ]; then
    echo "安装依赖..."
    pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
    echo "依赖安装完成"
    echo ""
fi

# 运行模拟
echo "启动社交模拟..."
python3 oasis_simulation.py

# 分析结果
if [ -f "oasis_simulation.db" ]; then
    echo ""
    echo "================================"
    echo "分析模拟结果..."
    echo "================================"
    python3 analyze_simulation.py
fi

echo ""
echo "完成！"

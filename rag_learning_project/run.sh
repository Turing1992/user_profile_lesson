#!/bin/bash

# RAG学习项目启动脚本

echo "🚀 启动RAG学习项目..."

# 检查Python版本
python_cmd="python3"
if command -v python3.6 &> /dev/null; then
    python_cmd="python3.6"
elif command -v python3 &> /dev/null; then
    python_cmd="python3"
else
    echo "❌ 错误: 未找到Python3"
    exit 1
fi

echo "✅ 使用Python命令: $python_cmd"

# 创建必要的目录
mkdir -p documents
mkdir -p vector_db
mkdir -p test_documents

echo "📁 创建项目目录完成"

# 安装依赖
echo "📦 安装依赖包..."
$python_cmd -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

if [ $? -ne 0 ]; then
    echo "❌ 依赖安装失败，请检查网络连接"
    exit 1
fi

echo "✅ 依赖安装完成"

# 创建示例文档
echo "📄 创建示例文档..."
cat > test_documents/ai_introduction.txt << 'EOF'
人工智能技术概述

人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。人工智能研究的一个主要目标是使机器能够胜任一些通常需要人类智能才能完成的复杂工作。

机器学习基础
机器学习（Machine Learning，ML）是人工智能的一个重要分支。机器学习算法通过分析大量数据来识别模式，并使用这些模式来做出预测或决策，而无需明确编程。机器学习可以分为监督学习、无监督学习和强化学习三大类。

监督学习使用标记的训练数据来学习输入和输出之间的映射关系。常见的监督学习算法包括线性回归、决策树、支持向量机和神经网络等。

无监督学习处理没有标签的数据，目标是发现数据中的隐藏模式。聚类分析和降维是无监督学习的典型应用。

强化学习通过与环境的交互来学习最优策略，广泛应用于游戏AI、机器人控制等领域。

深度学习技术
深度学习（Deep Learning）是机器学习的一个子集，它使用人工神经网络来模拟人脑的工作方式。深度学习网络包含多个隐藏层，能够学习数据的复杂表示。

卷积神经网络（CNN）特别适合处理图像数据，在图像识别、计算机视觉等领域取得了突破性进展。

循环神经网络（RNN）和长短期记忆网络（LSTM）擅长处理序列数据，广泛应用于自然语言处理、语音识别等任务。

Transformer架构的出现革命性地改变了自然语言处理领域，GPT、BERT等大型语言模型都基于这一架构。

自然语言处理应用
自然语言处理（Natural Language Processing，NLP）是人工智能的另一个重要分支，它致力于让计算机理解、解释和生成人类语言。

NLP技术被广泛应用于：
- 搜索引擎：理解用户查询意图，提供相关结果
- 机器翻译：实现不同语言之间的自动翻译
- 聊天机器人：与用户进行自然语言对话
- 文本分析：情感分析、主题提取、文档摘要等
- 语音助手：语音识别和语音合成

人工智能的发展前景
随着计算能力的提升和数据量的增长，人工智能技术正在快速发展。未来AI将在更多领域发挥重要作用，包括医疗诊断、自动驾驶、智能制造、金融服务等。

同时，AI的发展也带来了一些挑战，如算法偏见、隐私保护、就业影响等问题需要我们认真对待和解决。
EOF

echo "✅ 示例文档创建完成"

# 启动应用
echo ""
echo "🌟 RAG学习系统即将启动..."
echo "📖 访问地址: http://localhost:5000"
echo "📚 建议学习流程:"
echo "   1. 上传示例文档或自己的文档"
echo "   2. 观察文档处理过程"
echo "   3. 尝试提问并查看回答"
echo "   4. 分析检索结果和生成过程"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 启动Flask应用
$python_cmd app.py
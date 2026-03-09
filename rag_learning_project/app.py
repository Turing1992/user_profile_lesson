#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RAG学习项目 - Flask Web应用
提供完整的RAG系统Web界面，包括文档上传、问答交互等功能
"""

import os
import time
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from rag_system import RAGSystem

# 创建Flask应用
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# 配置上传目录
UPLOAD_FOLDER = 'documents'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 初始化RAG系统
print("🚀 启动RAG学习系统...")
rag_system = RAGSystem(
    chunk_size=500,
    chunk_overlap=50,
    vector_model="all-MiniLM-L6-v2",
    llm_model="gpt-3.5-turbo"
    # 注意：这里没有配置API密钥，系统将使用模拟模式
    # 如果要使用真实的LLM，请添加：
    # api_key="your-openai-api-key"
)

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    文档上传接口
    处理用户上传的文档，进行RAG处理
    """
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有选择文件'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'})
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': '不支持的文件格式'})
        
        # 保存文件
        filename = secure_filename(file.filename)
        timestamp = str(int(time.time()))
        filename = f"{timestamp}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        print(f"\n📁 收到文件上传: {file.filename}")
        
        # 使用RAG系统处理文档
        result = rag_system.add_documents([file_path])
        
        if result['processed_files'] > 0:
            processed_info = result['processed_details'][0]
            return jsonify({
                'success': True,
                'filename': file.filename,
                'chunks': processed_info['chunks'],
                'message': f'文档处理成功，生成了 {processed_info["chunks"]} 个文本块'
            })
        else:
            # 删除失败的文件
            if os.path.exists(file_path):
                os.remove(file_path)
            
            error_msg = result['failed_details'][0]['error'] if result['failed_details'] else '未知错误'
            return jsonify({
                'success': False,
                'error': f'文档处理失败: {error_msg}'
            })
    
    except Exception as e:
        print(f"❌ 文件上传处理失败: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/query', methods=['POST'])
def query():
    """
    问答查询接口
    处理用户问题，返回RAG生成的答案
    """
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({'success': False, 'error': '问题不能为空'})
        
        print(f"\n❓ 收到用户问题: {question}")
        
        # 使用RAG系统查询
        result = rag_system.query(
            question=question,
            top_k=5,
            return_sources=True
        )
        
        # 格式化响应
        response = {
            'success': True,
            'question': result['question'],
            'answer': result['answer'],
            'sources': result.get('sources', []),
            'timing': {
                'retrieval_time': f"{result.get('retrieval_time', 0):.2f}",
                'generation_time': f"{result.get('generation_time', 0):.2f}",
                'total_time': f"{result.get('total_time', 0):.2f}"
            },
            'retrieved_docs_count': result.get('retrieved_docs_count', 0)
        }
        
        print(f"✅ 问答完成，耗时: {result.get('total_time', 0):.2f}s")
        
        return jsonify(response)
    
    except Exception as e:
        print(f"❌ 问答处理失败: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/stats', methods=['GET'])
def get_stats():
    """
    获取系统统计信息
    """
    try:
        stats = rag_system.get_system_stats()
        
        # 计算文档总数和文本块总数
        vector_stats = stats.get('vector_store_stats', {})
        total_documents = vector_stats.get('total_documents', 0)
        
        # 简单估算文本块数（实际应该从系统中获取准确数据）
        estimated_chunks = total_documents * 3  # 假设每个文档平均3个块
        
        return jsonify({
            'success': True,
            'total_documents': len(os.listdir(UPLOAD_FOLDER)) if os.path.exists(UPLOAD_FOLDER) else 0,
            'total_chunks': total_documents,  # 这里是向量数量，相当于文本块数
            'vector_dimension': vector_stats.get('vector_dimension', 0),
            'system_status': stats.get('status', 'unknown'),
            'model_info': {
                'vector_model': stats['system_config']['vector_model'],
                'llm_model': stats['system_config']['llm_model']
            }
        })
    
    except Exception as e:
        print(f"❌ 获取统计信息失败: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/clear', methods=['POST'])
def clear_knowledge_base():
    """
    清空知识库
    """
    try:
        # 清空RAG系统
        rag_system.clear_knowledge_base()
        
        # 删除上传的文件
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        
        print("🗑️ 知识库已清空")
        
        return jsonify({
            'success': True,
            'message': '知识库已清空'
        })
    
    except Exception as e:
        print(f"❌ 清空知识库失败: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health_check():
    """
    健康检查接口
    """
    try:
        stats = rag_system.get_system_stats()
        return jsonify({
            'status': 'healthy',
            'system_status': stats.get('status', 'unknown'),
            'total_documents': stats['vector_store_stats'].get('total_documents', 0),
            'timestamp': time.time()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }), 500

@app.errorhandler(413)
def too_large(e):
    """文件过大错误处理"""
    return jsonify({'success': False, 'error': '文件过大，请选择小于16MB的文件'}), 413

@app.errorhandler(500)
def internal_error(e):
    """服务器内部错误处理"""
    return jsonify({'success': False, 'error': '服务器内部错误'}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🎉 RAG学习系统启动成功！")
    print("📖 这是一个完整的RAG系统实现，包含：")
    print("   - 文档处理和分块")
    print("   - 向量化和相似度检索")
    print("   - 上下文增强生成")
    print("   - 完整的Web界面")
    print("\n🌐 访问地址: http://localhost:5000")
    print("📚 使用说明:")
    print("   1. 上传PDF、Word或文本文档")
    print("   2. 等待文档处理完成")
    print("   3. 输入问题开始对话")
    print("   4. 观察RAG的工作过程")
    print("\n💡 学习要点:")
    print("   - 观察文档如何被分块处理")
    print("   - 理解向量检索的相似度匹配")
    print("   - 体验上下文如何增强生成质量")
    print("   - 分析不同参数对结果的影响")
    print("="*60)
    
    # 启动Flask应用
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )
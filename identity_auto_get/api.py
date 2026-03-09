#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from flask_cors import CORS
import asyncio
import threading
import logging
import os
from datetime import datetime

# 导入自定义模块
from database import IdentityAutoDatabase
from data_processor import DataProcessor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, 
           template_folder='templates',
           static_folder='static')
CORS(app)  # 允许跨域请求

# 初始化组件
db = IdentityAutoDatabase()
processor = DataProcessor()

# 默认的网约车司机识别提示词
DEFAULT_PROMPT = """我想让你扮演网约车身份判断专家，我会给你输入一个账号的发帖的贴文，你帮我从文章中判断出他的身份
判断要求为：1，如果是广告则不做判断
2，如果是描述他人跑网约车的不算
3，如果贴文是新闻类型或者小说，短剧，则不做判断
4，注意区分乘坐网约车的和跑网约车的，如果是乘坐网约车的人怎不做判断
5，优先判断称自己是跑网约车的，跑滴滴的发文，不要一看到网约车就下结论
6，一定是描述发帖人自己跑网约车，只要出现名字，第三人称，引号中的我是xxx，都不算
7，出现"我跑网约车XXXX"这类表达要注意是否是小说
8，文本长度超过200字都不是网约车司机

5，输出格式为：
    {
    "identity":"平台配送与运输从业者",
    "identity2":"网约车司机",
    "log":"判断原因"
    }

请只返回判断的分类名称，信息如下："""

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """静态文件服务"""
    return send_from_directory('static', filename)

@app.route('/api/tasks', methods=['POST'])
def create_task():
    """创建新的身份识别任务"""
    try:
        data = request.get_json()
        
        # 验证必需字段
        required_fields = ['match_keywords', 'identity_name', 'creator']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'缺少必需字段: {field}'
                }), 400
        
        # 使用提供的提示词或默认提示词
        prompt_text = data.get('prompt_text', DEFAULT_PROMPT)
        match_keywords = data.get('match_keywords')
        identity_name = data.get('identity_name')
        creator = data.get('creator')
        
        # 插入任务到数据库
        task_id = db.insert_task(prompt_text, match_keywords, identity_name, creator)
        
        # 异步开始处理任务
        def process_task_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    processor.process_data_parallel(task_id, prompt_text, match_keywords)
                )
            except Exception as e:
                logger.error(f"Error in async task processing: {e}")
                db.update_task_status(task_id, "创建完成", f"处理失败: {str(e)}")
        
        # 在后台线程中运行异步任务
        thread = threading.Thread(target=process_task_async)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': '任务创建成功，正在后台处理',
            'task_id': task_id
        })
        
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return jsonify({
            'success': False,
            'message': f'创建任务失败: {str(e)}'
        }), 500

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """获取任务列表"""
    try:
        creator = request.args.get('creator')
        tasks = db.get_all_tasks(creator)
        
        # 转换日期格式
        for task in tasks:
            if task.get('created_time'):
                task['created_time'] = task['created_time'].strftime('%Y-%m-%d %H:%M:%S')
            if task.get('updated_time'):
                task['updated_time'] = task['updated_time'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({
            'success': True,
            'data': tasks
        })
        
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        return jsonify({
            'success': False,
            'message': f'获取任务列表失败: {str(e)}'
        }), 500

@app.route('/api/tasks/<int:task_id>', methods=['GET'])
def get_task(task_id):
    """获取单个任务详情"""
    try:
        task = db.get_task_by_id(task_id)
        
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404
        
        # 转换日期格式
        if task.get('created_time'):
            task['created_time'] = task['created_time'].strftime('%Y-%m-%d %H:%M:%S')
        if task.get('updated_time'):
            task['updated_time'] = task['updated_time'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({
            'success': True,
            'data': task
        })
        
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {e}")
        return jsonify({
            'success': False,
            'message': f'获取任务详情失败: {str(e)}'
        }), 500

@app.route('/api/tasks/<int:task_id>/download', methods=['GET'])
def download_result(task_id):
    """下载任务结果文件"""
    try:
        task = db.get_task_by_id(task_id)
        
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404
        
        result_file_path = task.get('result_file_path')
        if not result_file_path or not os.path.exists(result_file_path):
            return jsonify({
                'success': False,
                'message': '结果文件不存在'
            }), 404
        
        return send_file(
            result_file_path,
            as_attachment=True,
            download_name=f"identity_analysis_task_{task_id}.xlsx"
        )
        
    except Exception as e:
        logger.error(f"Error downloading result for task {task_id}: {e}")
        return jsonify({
            'success': False,
            'message': f'下载失败: {str(e)}'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'success': True,
        'message': 'API服务正常运行',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': '接口不存在'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': '服务器内部错误'
    }), 500

if __name__ == '__main__':
    # 初始化数据库表
    try:
        db.create_table()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        exit(1)
    
    # 创建结果目录
    os.makedirs('identity_auto_get/results', exist_ok=True)
    
    # 启动Flask应用
    app.run(host='0.0.0.0', port=5000, debug=True)
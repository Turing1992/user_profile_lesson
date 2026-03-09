# -*- coding: utf-8 -*-
"""
Oasis系统API服务
提供HTTP接口进行画像推演
"""
from flask import Flask, request, jsonify
import json
from profile_engine import ProfileEngine
from storage import ProfileStorage

app = Flask(__name__)
engine = ProfileEngine()
storage = ProfileStorage()


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({"status": "ok", "service": "Oasis Profile System"})


@app.route('/profile/analyze', methods=['POST'])
def analyze_profile():
    """
    分析单个账号画像
    
    请求体:
    {
        "account_id": "账号ID",
        "name": "账号名称",
        "identity": "身份标签",
        "description": "自我描述",
        "verified_reason": "认证原因"
    }
    """
    try:
        account_data = request.json
        
        # 参数校验
        if not account_data or "account_id" not in account_data:
            return jsonify({
                "status": "error",
                "message": "缺少必要参数 account_id"
            }), 400
        
        # 执行分析
        result = engine.generate_full_profile(account_data)
        
        # 保存到数据库（可选）
        if request.args.get('save') == 'true':
            storage.save_profile(result)
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/profile/batch', methods=['POST'])
def batch_analyze():
    """
    批量分析账号画像
    
    请求体:
    [
        {
            "account_id": "账号ID1",
            "name": "账号名称1",
            ...
        },
        {
            "account_id": "账号ID2",
            "name": "账号名称2",
            ...
        }
    ]
    """
    try:
        account_list = request.json
        
        if not isinstance(account_list, list):
            return jsonify({
                "status": "error",
                "message": "请求体必须是数组"
            }), 400
        
        results = []
        for account_data in account_list:
            try:
                result = engine.generate_full_profile(account_data)
                results.append(result)
                
                # 保存到数据库（可选）
                if request.args.get('save') == 'true':
                    storage.save_profile(result)
            except Exception as e:
                results.append({
                    "account_id": account_data.get("account_id"),
                    "status": "failed",
                    "error": str(e)
                })
        
        return jsonify({
            "status": "success",
            "total": len(account_list),
            "results": results
        })
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/profile/get/<account_id>', methods=['GET'])
def get_profile(account_id):
    """获取已保存的画像数据"""
    try:
        result = storage.get_profile(account_id)
        
        if result:
            return jsonify({
                "status": "success",
                "data": result
            })
        else:
            return jsonify({
                "status": "error",
                "message": "未找到该账号的画像数据"
            }), 404
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == '__main__':
    # 初始化数据表
    storage.init_table()
    
    # 启动服务
    app.run(host='0.0.0.0', port=5001, debug=True)

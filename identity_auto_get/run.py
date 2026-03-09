#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
身份自动识别系统启动脚本
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('identity_auto_system.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def check_dependencies():
    """检查依赖是否安装"""
    required_packages = [
        'flask', 'flask_cors', 'mysql.connector',
        'pandas', 'openpyxl', 'opensearchpy', 'requests', 'loguru'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            if package == 'mysql.connector':
                import mysql.connector
            elif package == 'flask_cors':
                import flask_cors
            elif package == 'opensearchpy':
                import opensearchpy
            else:
                __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.error(f"Missing required packages: {missing_packages}")
        logger.error("Please install them using: pip install -r requirements.txt")
        return False
    
    return True

def setup_directories():
    """创建必要的目录"""
    directories = [
        'results',
        'logs',
        'templates',
        'static'
    ]
    
    for directory in directories:
        dir_path = Path(__file__).parent / directory
        dir_path.mkdir(exist_ok=True)
        logger.info(f"Directory ensured: {dir_path}")

def main():
    """主函数"""
    logger.info("Starting Identity Auto Recognition System...")
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 创建目录
    setup_directories()
    
    # 导入并启动应用
    try:
        from api import app, db
        
        # 初始化数据库
        logger.info("Initializing database...")

        db.create_table()
        
        # 启动Flask应用
        logger.info("Starting Flask application...")
        logger.info("Access the web interface at: http://localhost:5000")
        
        app.run(
            host='0.0.0.0',
            port=5080,
            debug=False,  # 生产环境关闭debug
            threaded=True
        )
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

try:
    import mysql.connector
except ImportError:
    print("Warning: mysql-connector-python not installed. Please install it with: pip install mysql-connector-python")
    mysql = None
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

# 导入配置
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.config import sql_config

logger = logging.getLogger(__name__)

class IdentityAutoDatabase:
    def __init__(self):
        self.config = sql_config
    
    def get_connection(self):
        """获取数据库连接"""
        return mysql.connector.connect(**self.config)
    
    def create_table(self):
        """创建identity_auto_table表"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS identity_auto_table (
            id INT AUTO_INCREMENT PRIMARY KEY,
            prompt_text TEXT NOT NULL COMMENT '提示词',
            match_keywords VARCHAR(500) NOT NULL COMMENT '匹配关键词',
            identity_name VARCHAR(200) NOT NULL COMMENT '身份名称',
            task_status ENUM('创建中', '测试中', '创建完成') DEFAULT '创建中' COMMENT '任务状态',
            creator VARCHAR(100) NOT NULL COMMENT '创建人',
            created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            result_file_path VARCHAR(500) COMMENT '结果文件路径',
            INDEX idx_task_status (task_status),
            INDEX idx_creator (creator),
            INDEX idx_created_time (created_time)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='身份自动识别任务表';
        """
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
            conn.commit()
            logger.info("Table identity_auto_table created successfully")
        except Exception as e:
            logger.error(f"Error creating table: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def insert_task(self, prompt_text: str, match_keywords: str, identity_name: str, creator: str) -> int:
        """插入新任务"""
        insert_sql = """
        INSERT INTO identity_auto_table (prompt_text, match_keywords, identity_name, creator, task_status)
        VALUES (%s, %s, %s, %s, '创建中')
        """
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(insert_sql, (prompt_text, match_keywords, identity_name, creator))
            conn.commit()
            task_id = cursor.lastrowid
            logger.info(f"Task inserted successfully with ID: {task_id}")
            return task_id
        except Exception as e:
            logger.error(f"Error inserting task: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def update_task_status(self, task_id: int, status: str, result_file_path: str = None):
        """更新任务状态"""
        if result_file_path:
            update_sql = """
            UPDATE identity_auto_table 
            SET task_status = %s, result_file_path = %s, updated_time = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            params = (status, result_file_path, task_id)
        else:
            update_sql = """
            UPDATE identity_auto_table 
            SET task_status = %s, updated_time = CURRENT_TIMESTAMP
            WHERE id = %s
            """
            params = (status, task_id)
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(update_sql, params)
            conn.commit()
            logger.info(f"Task {task_id} status updated to {status}")
        except Exception as e:
            logger.error(f"Error updating task status: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取任务"""
        select_sql = """
        SELECT id, prompt_text, match_keywords, identity_name, task_status, 
               creator, created_time, updated_time, result_file_path
        FROM identity_auto_table 
        WHERE id = %s
        """
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(select_sql, (task_id,))
            result = cursor.fetchone()
            return result
        except Exception as e:
            logger.error(f"Error getting task by ID: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def get_all_tasks(self, creator: str = None) -> List[Dict[str, Any]]:
        """获取所有任务"""
        if creator:
            select_sql = """
            SELECT id, prompt_text, match_keywords, identity_name, task_status, 
                   creator, created_time, updated_time, result_file_path
            FROM identity_auto_table 
            WHERE creator = %s
            ORDER BY created_time DESC
            """
            params = (creator,)
        else:
            select_sql = """
            SELECT id, prompt_text, match_keywords, identity_name, task_status, 
                   creator, created_time, updated_time, result_file_path
            FROM identity_auto_table 
            ORDER BY created_time DESC
            """
            params = ()
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(select_sql, params)
            results = cursor.fetchall()
            return results
        except Exception as e:
            logger.error(f"Error getting all tasks: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

if __name__ == "__main__":
    # 测试数据库连接和表创建
    db = IdentityAutoDatabase()
    db.create_table()
    print("Database setup completed!")
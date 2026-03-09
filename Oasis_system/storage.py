# -*- coding: utf-8 -*-
"""
数据存储模块
"""
import pymysql
import json
from config import MYSQL_CONFIG


class ProfileStorage:
    """画像数据存储"""
    
    def __init__(self):
        self.config = MYSQL_CONFIG
    
    def get_connection(self):
        """获取数据库连接"""
        return pymysql.connect(
            host=self.config["host"],
            port=self.config["port"],
            user=self.config["user"],
            password=self.config["password"],
            database=self.config["database"],
            charset=self.config["charset"],
            cursorclass=pymysql.cursors.DictCursor
        )
    
    def init_table(self):
        """初始化数据表"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # 创建画像结果表
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS oasis_profiles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id VARCHAR(255) NOT NULL UNIQUE,
                    account_name VARCHAR(255),
                    identity VARCHAR(255),
                    basic_info JSON,
                    identity_analysis JSON,
                    behavior_prediction JSON,
                    social_inference JSON,
                    content_preference JSON,
                    risk_assessment JSON,
                    full_profile JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_account_id (account_id),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
                cursor.execute(create_table_sql)
            conn.commit()
            print("数据表初始化成功")
        except Exception as e:
            print(f"数据表初始化失败: {e}")
        finally:
            conn.close()
    
    def save_profile(self, profile_data):
        """
        保存画像数据
        
        Args:
            profile_data: 画像数据字典
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                profile = profile_data.get("profile", {})
                
                sql = """
                INSERT INTO oasis_profiles 
                (account_id, account_name, identity, basic_info, identity_analysis, 
                 behavior_prediction, social_inference, content_preference, 
                 risk_assessment, full_profile)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                account_name = VALUES(account_name),
                identity = VALUES(identity),
                basic_info = VALUES(basic_info),
                identity_analysis = VALUES(identity_analysis),
                behavior_prediction = VALUES(behavior_prediction),
                social_inference = VALUES(social_inference),
                content_preference = VALUES(content_preference),
                risk_assessment = VALUES(risk_assessment),
                full_profile = VALUES(full_profile)
                """
                
                cursor.execute(sql, (
                    profile_data.get("account_id"),
                    profile_data.get("account_data", {}).get("name"),
                    profile_data.get("account_data", {}).get("identity"),
                    json.dumps(profile.get("basic_info", {}), ensure_ascii=False),
                    json.dumps(profile.get("identity_analysis", {}), ensure_ascii=False),
                    json.dumps(profile.get("behavior_prediction", {}), ensure_ascii=False),
                    json.dumps(profile.get("social_inference", {}), ensure_ascii=False),
                    json.dumps(profile.get("content_preference", {}), ensure_ascii=False),
                    json.dumps(profile.get("risk_assessment", {}), ensure_ascii=False),
                    json.dumps(profile_data, ensure_ascii=False)
                ))
            conn.commit()
        except Exception as e:
            print(f"保存画像数据失败: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_profile(self, account_id):
        """
        获取画像数据
        
        Args:
            account_id: 账号ID
        
        Returns:
            dict: 画像数据
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM oasis_profiles WHERE account_id = %s"
                cursor.execute(sql, (account_id,))
                result = cursor.fetchone()
                return result
        finally:
            conn.close()
    
    def batch_save_profiles(self, profiles):
        """
        批量保存画像数据
        
        Args:
            profiles: 画像数据列表
        """
        for profile in profiles:
            if profile.get("status") == "success":
                self.save_profile(profile)

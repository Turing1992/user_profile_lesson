# -*- coding: utf-8 -*-
"""
画像推演引擎
"""
import json
from llm_client import LLMClient
from platform_adapter import PlatformAdapter, PLATFORM_CONTEXT
from prompts import (
    BASIC_INFO_PROMPT,
    IDENTITY_ANALYSIS_PROMPT,
    BEHAVIOR_PREDICTION_PROMPT,
    SOCIAL_INFERENCE_PROMPT,
    CONTENT_PREFERENCE_PROMPT,
    RISK_ASSESSMENT_PROMPT
)


class ProfileEngine:
    """账号画像推演引擎"""
    
    def __init__(self):
        self.llm_client = LLMClient()
    
    def _get_platform_info(self, account_data):
        """获取平台相关信息，用于填充 prompt"""
        platform = account_data.get("platform", "")
        ctx = PLATFORM_CONTEXT.get(platform, {})
        platform_name = ctx.get("name", "未知平台")
        platform_features = "；".join(ctx.get("features", [])[:4]) if ctx else "通用社交平台"
        platform_summary = account_data.get("platform_summary", "无")
        return platform_name, platform_features, platform_summary
    
    def analyze_basic_info(self, account_data):
        """
        基础信息分析
        
        Args:
            account_data: 账号数据字典
        
        Returns:
            dict: 基础信息分析结果
        """
        platform_name, platform_features, platform_summary = self._get_platform_info(account_data)
        
        # 使用增强描述（包含平台数据）
        enriched_desc = PlatformAdapter.build_enriched_description(account_data) if account_data.get("platform") else account_data.get("description", "")
        
        prompt = BASIC_INFO_PROMPT.format(
            name=account_data.get("name", ""),
            identity=account_data.get("identity", ""),
            description=enriched_desc,
            verified_reason=account_data.get("verified_reason", ""),
            platform_name=platform_name,
            platform_features=platform_features,
            platform_summary=platform_summary
        )
        
        result, response_id, raw_response = self.llm_client.call(prompt)
        return {
            "data": result,
            "response_id": response_id,
            "raw_response": raw_response
        }
    
    def analyze_identity(self, account_data, basic_info):
        """
        身份深度分析
        
        Args:
            account_data: 账号数据
            basic_info: 基础信息分析结果
        
        Returns:
            dict: 身份分析结果
        """
        prompt = IDENTITY_ANALYSIS_PROMPT.format(
            name=account_data.get("name", ""),
            identity=account_data.get("identity", ""),
            description=account_data.get("description", ""),
            basic_info=json.dumps(basic_info, ensure_ascii=False)
        )
        
        result, response_id, raw_response = self.llm_client.call(prompt)
        return {
            "data": result,
            "response_id": response_id,
            "raw_response": raw_response
        }
    
    def predict_behavior(self, account_data, identity_analysis):
        """
        行为模式预测
        
        Args:
            account_data: 账号数据
            identity_analysis: 身份分析结果
        
        Returns:
            dict: 行为预测结果
        """
        prompt = BEHAVIOR_PREDICTION_PROMPT.format(
            account_info=json.dumps(account_data, ensure_ascii=False),
            identity_analysis=json.dumps(identity_analysis, ensure_ascii=False)
        )
        
        result, response_id, raw_response = self.llm_client.call(prompt)
        return {
            "data": result,
            "response_id": response_id,
            "raw_response": raw_response
        }
    
    def infer_social(self, account_data, identity_analysis, behavior_prediction):
        """
        社交关系推断
        
        Args:
            account_data: 账号数据
            identity_analysis: 身份分析结果
            behavior_prediction: 行为预测结果
        
        Returns:
            dict: 社交推断结果
        """
        prompt = SOCIAL_INFERENCE_PROMPT.format(
            account_info=json.dumps(account_data, ensure_ascii=False),
            identity_analysis=json.dumps(identity_analysis, ensure_ascii=False),
            behavior_prediction=json.dumps(behavior_prediction, ensure_ascii=False)
        )
        
        result, response_id, raw_response = self.llm_client.call(prompt)
        return {
            "data": result,
            "response_id": response_id,
            "raw_response": raw_response
        }
    
    def analyze_content_preference(self, account_data, identity_analysis):
        """
        内容偏好分析
        
        Args:
            account_data: 账号数据
            identity_analysis: 身份分析结果
        
        Returns:
            dict: 内容偏好分析结果
        """
        prompt = CONTENT_PREFERENCE_PROMPT.format(
            account_info=json.dumps(account_data, ensure_ascii=False),
            identity_analysis=json.dumps(identity_analysis, ensure_ascii=False)
        )
        
        result, response_id, raw_response = self.llm_client.call(prompt)
        return {
            "data": result,
            "response_id": response_id,
            "raw_response": raw_response
        }
    
    def assess_risk(self, full_profile):
        """
        风险评估
        
        Args:
            full_profile: 完整画像数据
        
        Returns:
            dict: 风险评估结果
        """
        prompt = RISK_ASSESSMENT_PROMPT.format(
            full_profile=json.dumps(full_profile, ensure_ascii=False, indent=2)
        )
        
        result, response_id, raw_response = self.llm_client.call(prompt)
        return {
            "data": result,
            "response_id": response_id,
            "raw_response": raw_response
        }
    
    def generate_full_profile(self, account_data, platform=None):
        """
        生成完整画像
        
        Args:
            account_data: 账号数据
            platform: 平台标识 (weibo/douyin)，如果数据中已有则可不传
        
        Returns:
            dict: 完整画像结果
        """
        # 平台数据标准化
        platform = platform or account_data.get("platform")
        if platform and platform in ("weibo", "douyin"):
            account_data = PlatformAdapter.normalize(account_data, platform)
        
        print(f"开始分析账号: {account_data.get('account_id', 'unknown')} [平台: {account_data.get('platform', '通用')}]")
        
        # 1. 基础信息分析
        print("  [1/6] 基础信息分析...")
        basic_info = self.analyze_basic_info(account_data)
        
        # 2. 身份分析
        print("  [2/6] 身份深度分析...")
        identity_analysis = self.analyze_identity(account_data, basic_info.get("data", {}))
        
        # 3. 行为预测
        print("  [3/6] 行为模式预测...")
        behavior_prediction = self.predict_behavior(
            account_data, 
            identity_analysis.get("data", {})
        )
        
        # 4. 社交推断
        print("  [4/6] 社交关系推断...")
        social_inference = self.infer_social(
            account_data,
            identity_analysis.get("data", {}),
            behavior_prediction.get("data", {})
        )
        
        # 5. 内容偏好
        print("  [5/6] 内容偏好分析...")
        content_preference = self.analyze_content_preference(
            account_data,
            identity_analysis.get("data", {})
        )
        
        # 6. 风险评估
        print("  [6/6] 风险评估...")
        full_profile_data = {
            "account_data": account_data,
            "basic_info": basic_info.get("data", {}),
            "identity_analysis": identity_analysis.get("data", {}),
            "behavior_prediction": behavior_prediction.get("data", {}),
            "social_inference": social_inference.get("data", {}),
            "content_preference": content_preference.get("data", {})
        }
        risk_assessment = self.assess_risk(full_profile_data)
        
        # 组装完整结果
        result = {
            "account_id": account_data.get("account_id"),
            "platform": account_data.get("platform", "unknown"),
            "profile": {
                "basic_info": basic_info,
                "identity_analysis": identity_analysis,
                "behavior_prediction": behavior_prediction,
                "social_inference": social_inference,
                "content_preference": content_preference,
                "risk_assessment": risk_assessment
            },
            "status": "success"
        }
        
        # 保留平台原始数据
        if account_data.get("platform_data"):
            result["platform_data"] = account_data["platform_data"]
        
        print(f"账号分析完成: {account_data.get('account_id', 'unknown')}\n")
        return result

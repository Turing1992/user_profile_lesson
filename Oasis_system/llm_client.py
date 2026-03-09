# -*- coding: utf-8 -*-
"""
LLM客户端封装
"""
import time
import json
import requests
import traceback
from config import LLM_CONFIG


class LLMClient:
    """LLM API客户端"""
    
    def __init__(self):
        self.url = LLM_CONFIG["url"]
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_CONFIG['api_key']}"
        }
        self.model = LLM_CONFIG["model"]
        self.temperature = LLM_CONFIG["temperature"]
        self.top_p = LLM_CONFIG["top_p"]
    
    def call(self, prompt, max_retries=3, retry_delay=4):
        """
        调用LLM API
        
        Args:
            prompt: 提示词
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        
        Returns:
            tuple: (result_dict, response_id, raw_response)
        """
        retries = max_retries
        
        while retries > 0:
            try:
                data = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "enable_enhancement": False
                }
                
                response = requests.post(
                    self.url, 
                    headers=self.headers, 
                    data=json.dumps(data),
                    timeout=60
                )
                
                if response.status_code == 200:
                    response_json = response.json()
                    response_id = response_json.get("id", "")
                    response_content = response_json["choices"][0]["message"]["content"]
                    
                    # 尝试解析JSON
                    try:
                        # 提取JSON部分
                        if "```json" in response_content:
                            json_str = response_content.split("```json")[1].split("```")[0].strip()
                        elif "```" in response_content:
                            json_str = response_content.split("```")[1].split("```")[0].strip()
                        else:
                            json_str = response_content.strip()
                        
                        result = json.loads(json_str)
                        return result, response_id, response_content
                    except json.JSONDecodeError as e:
                        print(f"JSON解析失败: {e}")
                        print(f"原始响应: {response_content}")
                        return {}, response_id, response_content
                else:
                    print(f"请求失败，状态码: {response.status_code}")
                    print(f"响应内容: {response.text}")
                    time.sleep(retry_delay)
                    retries -= 1
                    continue
                    
            except Exception as e:
                print(f"调用异常: {traceback.format_exc()}")
                time.sleep(retry_delay)
                retries -= 1
                continue
        
        return {}, "", ""
    
    def batch_call(self, prompts, max_retries=3):
        """
        批量调用LLM API
        
        Args:
            prompts: 提示词列表
            max_retries: 最大重试次数
        
        Returns:
            list: 结果列表
        """
        results = []
        for prompt in prompts:
            result, response_id, raw_response = self.call(prompt, max_retries)
            results.append({
                "result": result,
                "response_id": response_id,
                "raw_response": raw_response
            })
        return results

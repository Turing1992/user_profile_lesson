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
                        
                        result = self._robust_json_parse(json_str)
                        if result is not None:
                            return result, response_id, response_content
                        
                        # 如果提取的部分解析失败，尝试从整个响应中找JSON
                        result = self._extract_json_from_text(response_content)
                        if result is not None:
                            return result, response_id, response_content
                        
                        print(f"JSON解析失败，原始响应: {response_content[:200]}")
                        return {}, response_id, response_content
                    except Exception as e:
                        print(f"JSON解析异常: {e}")
                        print(f"原始响应: {response_content[:200]}")
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

    @staticmethod
    def _robust_json_parse(text):
        """增强的JSON解析，处理LLM常见的格式问题"""
        import re
        if not text or not text.strip():
            return None
        text = text.strip()
        # 1. 直接尝试
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 2. 去掉JS风格注释 (// ... 和 /* ... */)
        cleaned = re.sub(r'//[^\n]*', '', text)
        cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # 3. 去掉尾逗号 (,] 或 ,})
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # 4. 修复单引号
        try:
            return json.loads(cleaned.replace("'", '"'))
        except json.JSONDecodeError:
            pass
        return None

    @staticmethod
    def _extract_json_from_text(text):
        """从文本中提取第一个完整的JSON对象"""
        # 找第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            result = LLMClient._robust_json_parse(candidate)
            if result is not None:
                return result
        # 尝试找数组
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            result = LLMClient._robust_json_parse(candidate)
            if result is not None:
                return result
        return None

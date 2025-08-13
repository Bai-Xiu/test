import time
import json
import os
from datetime import datetime
from openai import OpenAI

class DeepSeekAPI:
    def __init__(self, api_key, sensitive_processor=None):
        self.api_key = api_key
        self.sensitive_processor = sensitive_processor  # 添加敏感词处理器
        # 官方示例的客户端初始化
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )

    def _log_api_interaction(self, prompt, response, replace_count=None):
        """仅在终端显示日志，不写入文件"""
        try:
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "prompt_length": len(prompt),
                "response_status": "success" if response else "error",
                "response_length": len(response.choices[0].message.content) if response else 0,
                "replace_count": replace_count if replace_count else {}
            }
            # 仅在终端打印日志信息
            print("\nAPI交互日志:")
            print(f"时间: {log_data['timestamp']}")
            print(f"请求长度: {log_data['prompt_length']} 字符")
            print(f"响应状态: {log_data['response_status']}")
            print(f"响应长度: {log_data['response_length']} 字符")
            print(f"敏感词替换计数: {log_data['replace_count']}")
        except Exception as e:
            print(f"API日志记录失败: {str(e)}")

    def completions_create(self, model="deepseek-reasoner", prompt=None, max_tokens=5000, temperature=0.3, retry=3):
        if not prompt:
            raise ValueError("prompt不能为空")

        # 敏感词替换
        replace_count = None
        processed_prompt = prompt
        if self.sensitive_processor:

            processed_prompt, replace_count = self.sensitive_processor.replace_sensitive_words(prompt)

            # 显示处理后的请求

        attempt = 0
        while attempt < retry:
            try:
                # 完全对齐官方示例的参数结构
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system",
                         "content": "你是专业的信息安全日志分析专家，根据用户要求解决日志分析问题。"},
                        {"role": "user", "content": processed_prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False
                )

                # 记录API交互日志
                self._log_api_interaction(processed_prompt, response, replace_count)

                # 敏感词还原
                if self.sensitive_processor and response.choices[0].message.content:
                    response.choices[0].message.content = self.sensitive_processor.restore_sensitive_words(
                        response.choices[0].message.content
                    )

                return response
            except Exception as e:
                attempt += 1
                error_msg = f"API调用出错 (尝试 {attempt}/{retry}): {str(e)}"
                print(error_msg)

                # 记录错误日志
                self._log_api_interaction(processed_prompt, None, replace_count)

                if attempt < retry:
                    time.sleep(2)
        raise Exception(f"API调用失败，已达到最大重试次数 ({retry}次)")
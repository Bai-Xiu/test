import time
import re  # 新增：用于处理提示词


class OpenAIStub:
    """OpenAI客户端的占位类，当未安装openai库时使用"""

    def __init__(self, *args, **kwargs):
        pass

    class Chat:
        @staticmethod
        def completions_create(*args, **kwargs):
            class DummyResponse:
                @staticmethod
                def choices():
                    class DummyChoice:
                        message = type('', (), {'content': '演示模式下的响应'})()

                    return [DummyChoice()]

            return DummyResponse()


# 尝试导入真实的OpenAI客户端
try:
    from openai import OpenAI
except ImportError:
    OpenAI = OpenAIStub


class DeepSeekAPI:
    def __init__(self, api_key, sensitive_manager=None):
        self.api_key = api_key
        self.sensitive_manager = sensitive_manager  # 敏感信息管理器
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        # 新增：替换词说明提示（告知AI替换词的存在和处理方式）
        self.privacy_note = """
注意：文本中包含形如[PROTECTED_xxxx_xxxx]的标记，这些是隐私保护替换词，用于替代敏感信息。
- 请忽略这些标记的具体格式，将其视为一个完整的语义单元处理
- 分析时无需关注标记的内部结构，仅需根据上下文理解其在文本中的作用
- 生成结果时保持这些标记的原样，不要修改或解析它们
"""

    def completions_create(self, model="deepseek-reasoner", prompt=None, max_tokens=5000, temperature=0.3, retry=3):
        if not prompt:
            raise ValueError("prompt不能为空")

        # 1. 替换敏感信息前先处理提示词，添加隐私说明
        full_prompt = f"{self.privacy_note}\n\n用户实际请求：{prompt}"

        # 2. 替换敏感信息
        original_prompt = full_prompt
        if self.sensitive_manager:
            full_prompt = self.sensitive_manager.replace_sensitive_info(full_prompt)

        attempt = 0
        while attempt < retry:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是专业的信息安全日志分析专家，擅长处理带隐私保护标记的文本"},
                        {"role": "user", "content": full_prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False
                )

                # 3. 还原敏感信息
                if self.sensitive_manager and response.choices[0].message.content:
                    response.choices[0].message.content = self.sensitive_manager.restore_sensitive_info(
                        response.choices[0].message.content
                    )

                return response
            except Exception as e:
                attempt += 1
                print(f"API调用出错 (尝试 {attempt}/{retry}): {str(e)}")
                if attempt < retry:
                    time.sleep(2)
        raise Exception(f"API调用失败，已达到最大重试次数 ({retry}次)")
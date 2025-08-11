import time


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
        self.sensitive_manager = sensitive_manager  # 添加敏感信息管理器
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )

    def completions_create(self, model="deepseek-reasoner", prompt=None, max_tokens=5000, temperature=0.3, retry=3):
        if not prompt:
            raise ValueError("prompt不能为空")

        # 发送前替换敏感信息
        original_prompt = prompt
        if self.sensitive_manager:
            prompt = self.sensitive_manager.replace_sensitive_info(prompt)

        attempt = 0
        while attempt < retry:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是专业的信息安全日志分析专家"},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False
                )

                # 接收后还原敏感信息
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
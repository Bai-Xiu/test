import os
import pandas as pd
import json
from utils.helpers import get_file_list, sanitize_filename
from core.api_client import DeepSeekAPI
from core.file_processors import (
    CsvFileProcessor, ExcelFileProcessor,
    JsonFileProcessor, TxtFileProcessor
)


class LogAIProcessor:
    def __init__(self, config, sensitive_manager=None):
        self.config = config
        self.api_key = config.get("api_key", "")
        self.sensitive_manager = sensitive_manager

        # 区分默认目录和当前目录
        self.default_data_dir = config.get("data_dir", "")  # 持久化的默认目录
        self.current_data_dir = self.default_data_dir  # 当前工作目录（临时）

        self.default_save_dir = config.get("save_dir", "")  # 持久化的默认目录
        self.current_save_dir = self.default_save_dir  # 当前工作目录（临时）

        self.verbose = config.get("verbose_logging", False)
        self.supported_encodings = ['utf-8', 'gbk', 'gb2312', 'ansi', 'utf-16', 'utf-16-le']

        # 初始化API客户端
        self.client = DeepSeekAPI(api_key=self.api_key, sensitive_manager=sensitive_manager) if self.api_key else None

        # 存储当前选择的文件和数据
        self.current_files = None
        self.current_data = None

        # 初始化文件处理器（核心扩展点：添加新类型只需在这里注册）
        self.file_processors = [
            CsvFileProcessor(),
            ExcelFileProcessor(),
            JsonFileProcessor(),
            TxtFileProcessor()
        ]

        # 构建扩展名到处理器的映射
        self.extension_map = {}
        for processor in self.file_processors:
            for ext in processor.get_supported_extensions():
                self.extension_map[ext.lower()] = processor

    def set_default_data_dir(self, new_dir):
        if new_dir:
            self.default_data_dir = new_dir
            self.config.set("data_dir", new_dir)

    def set_current_data_dir(self, new_dir):
        if new_dir:
            self.current_data_dir = new_dir

    def set_default_save_dir(self, new_dir):
        if new_dir:
            self.default_save_dir = new_dir
            self.config.set("save_dir", new_dir)

    def set_current_save_dir(self, new_dir):
        if new_dir:
            self.current_save_dir = new_dir

    def get_file_list(self):
        """获取当前数据目录中的文件列表"""
        if not self.current_data_dir or not os.path.exists(self.current_data_dir):
            return []
        return get_file_list(self.current_data_dir)

    def load_data_files(self, file_names):
        """从当前数据目录加载文件"""
        if not self.current_data_dir or not os.path.exists(self.current_data_dir):
            raise ValueError("当前数据目录未设置或不存在")

        return self._load_file_data(file_names)

    def _load_file_data(self, file_names):
        """从当前数据目录读取文件数据"""
        if self.current_data and set(file_names) == set(self.current_data.keys()):
            return self.current_data

        data_dict = {}
        for file_name in file_names:
            safe_file = sanitize_filename(file_name)
            full_path = os.path.join(self.current_data_dir, safe_file)

            if not os.path.exists(full_path):
                raise FileNotFoundError(f"文件不存在: {full_path}")

            # 获取文件扩展名
            _, ext = os.path.splitext(full_path)
            ext = ext.lower()

            # 检查是否支持该类型
            if ext not in self.extension_map:
                supported_exts = ", ".join(self.extension_map.keys())
                raise ValueError(
                    f"不支持的文件格式: {ext}。支持的格式: {supported_exts}"
                )

            # 使用对应的处理器读取文件
            try:
                processor = self.extension_map[ext]
                df = processor.read_file(
                    full_path,
                    encodings=self.supported_encodings
                )
                data_dict[safe_file] = df
            except Exception as e:
                raise RuntimeError(f"读取文件 {safe_file} 失败: {str(e)}")

        self.current_data = data_dict
        return data_dict

    def generate_processing_code(self, user_request, file_names):
        """生成完整可执行代码"""
        if not self.client:
            # 默认代码：直接返回所有数据
            return """import pandas as pd
    result_table = pd.concat(data_dict.values(), ignore_index=True)
    summary = f'共{len(result_table)}条记录'"""

        data_dict = self._load_file_data(file_names)

        # 准备文件元数据（新增：对元数据中的样本进行敏感词替换）
        file_info = {}
        for filename, df in data_dict.items():
            # 处理样本数据中的敏感信息
            raw_sample = df.head(2).to_dict(orient='records')
            processed_sample = raw_sample

            if self.sensitive_manager:
                # 序列化后替换敏感词
                sample_str = json.dumps(raw_sample, ensure_ascii=False)
                processed_sample_str = self.sensitive_manager.replace_sensitive_info(sample_str)
                processed_sample = json.loads(processed_sample_str)

            file_info[filename] = {
                "columns": df.columns.tolist(),
                "sample": processed_sample  # 使用处理后的样本
            }

        prompt = f"""根据用户请求编写完整的Python处理代码:
    用户需求: {user_request}
    数据信息: {json.dumps(file_info, ensure_ascii=False)}

    说明：
    重要提示：返回的内容只能是可直接执行的代码，绝对不要有任何其他说明，保证返回的内容可以直接执行
    1. 已存在变量data_dict（文件名到DataFrame的字典），可直接使用
    2. 必须导入所需的库（如pandas）
    3. 必须定义两个变量：
       - result_table：处理后的DataFrame结果（必须存在）
       - summary：字符串类型的总结
    4. 不要包含任何函数定义，直接编写可执行代码
    5. 不需要return语句，只需确保定义了上述两个变量
    6. 处理日志时，务必将包含类似"低/中/高"等含中文的字符串的列显式转换为字符串类型
    7. 处理日志时，对于确定同义的表头信息，建议使用统一的名称，并对内容进行整合"""

        response = self.client.completions_create(
            model='deepseek-reasoner',
            prompt=prompt,
            max_tokens=5000,
            temperature=0.3
        )

        code_block = response.choices[0].message.content.strip()
        return code_block

    def direct_answer(self, user_request, file_names):
        """直接回答模式：生成日志总结，不返回表格数据，确保所有内容经过敏感词处理"""
        data_dict = self._load_file_data(file_names)

        # 收集文件详细信息（包含敏感词处理）
        file_details = []
        for filename, df in data_dict.items():
            # 处理数据样本中的敏感信息
            raw_sample = df.head(min(3, len(df))).to_dict(orient='records')
            processed_sample = raw_sample

            if self.sensitive_manager:
                # 序列化后替换敏感词，再反序列化回字典
                sample_str = json.dumps(raw_sample, ensure_ascii=False, default=str)
                processed_sample_str = self.sensitive_manager.replace_sensitive_info(sample_str)
                processed_sample = json.loads(processed_sample_str)

            # 基础信息
            details = {
                "文件名": filename,
                "记录数": len(df),
                "列名": df.columns.tolist(),
                "数据类型分布": {col: str(df[col].dtype) for col in df.columns},
                "数据样本": processed_sample  # 使用处理后的样本
            }

            # 数值列统计（无需脱敏，数值本身不涉及敏感信息）
            numeric_stats = {}
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    numeric_stats[col] = {
                        "平均值": df[col].mean(),
                        "最小值": df[col].min(),
                        "最大值": df[col].max(),
                        "非空值数量": df[col].count()
                    }
            if numeric_stats:
                details["数值列统计"] = numeric_stats

            file_details.append(details)

        # 处理用户请求中的敏感信息
        processed_request = user_request
        if self.sensitive_manager and user_request:
            processed_request = self.sensitive_manager.replace_sensitive_info(user_request)

        # 构建提示词（使用处理后的请求和文件详情）
        prompt = f"""基于以下日志文件的详细信息，回答用户问题并生成总结:
        文件详情: {json.dumps(file_details, ensure_ascii=False, default=str)}
        用户问题: {processed_request}

        回答要求:
        1. 深入分析日志数据特征、潜在规律和关键信息
        2. 直接给出自然语言总结，不生成任何表格或结构化数据
        3. 内容具体有针对性，避免泛泛而谈
        4. 涉及统计信息时自然体现关键数值
        5. 用简洁易懂的中文表达"""

        # 调用API（API客户端会进行二次全局校验）
        response = self.client.completions_create(
            model='deepseek-reasoner',
            prompt=prompt,
            max_tokens=2000,
            temperature=0.6
        )

        # 还原响应中的敏感信息（如果需要展示原始内容）
        summary = response.choices[0].message.content.strip()
        if self.sensitive_manager:
            summary = self.sensitive_manager.restore_sensitive_info(summary)

        return {"summary": summary}
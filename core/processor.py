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
    def __init__(self, config):
        self.config = config
        self.api_key = config.get("api_key", "")

        # 添加敏感词处理器
        from core.sensitive_processor import SensitiveWordProcessor
        self.sensitive_processor = SensitiveWordProcessor(config)

        # 区分默认目录和当前目录
        self.default_data_dir = config.get("data_dir", "")  # 持久化的默认目录
        self.current_data_dir = self.default_data_dir  # 当前工作目录（临时）

        self.default_save_dir = config.get("save_dir", "")  # 持久化的默认目录
        self.current_save_dir = self.default_save_dir  # 当前工作目录（临时）

        self.verbose = config.get("verbose_logging", False)
        self.supported_encodings = ['utf-8', 'gbk', 'gb2312', 'ansi', 'utf-16', 'utf-16-le']

        # 初始化API客户端，传入敏感词处理器
        self.client = DeepSeekAPI(api_key=self.api_key,
                                  sensitive_processor=self.sensitive_processor) if self.api_key else None

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

    def process_and_anonymize_files(self, file_names, output_dir):
        """处理并去敏文件"""
        if not file_names:
            raise ValueError("未选择文件")

        if not output_dir or not os.path.exists(output_dir):
            raise ValueError("无效的输出目录")

        data_dict = self._load_file_data(file_names)
        results = {}

        for filename, df in data_dict.items():
            # 对DataFrame中的文本进行去敏处理
            anonymized_df = self._anonymize_dataframe(df)

            # 保存去敏后的文件
            base_name = os.path.splitext(filename)[0]
            ext = os.path.splitext(filename)[1]
            output_path = os.path.join(
                output_dir,
                f"{base_name}_anonymized{ext}"
            )

            # 根据文件类型保存
            _, ext = os.path.splitext(filename)
            if ext.lower() in ['.csv']:
                anonymized_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            elif ext.lower() in ['.xlsx', '.xls']:
                anonymized_df.to_excel(output_path, index=False)
            elif ext.lower() in ['.json']:
                anonymized_df.to_json(output_path, orient='records', force_ascii=False)
            else:  # 文本文件
                content = "\n".join(anonymized_df.iloc[:, 0].astype(str).tolist())
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)

            results[filename] = output_path

        return results

    def _anonymize_dataframe(self, df):
        """对DataFrame进行去敏处理"""
        df_copy = df.copy()

        # 对每一列进行处理
        for col in df_copy.columns:
            # 处理字符串类型的列
            if df_copy[col].dtype == 'object':
                df_copy[col] = df_copy[col].apply(
                    lambda x: self._anonymize_text(str(x)) if pd.notna(x) else x
                )

        return df_copy

    def _anonymize_text(self, text):
        """对文本进行去敏处理"""
        if not text or not isinstance(text, str):
            return text

        # 使用敏感词处理器进行替换
        anonymized_text, _ = self.sensitive_processor.replace_sensitive_words(text)
        return anonymized_text

    def generate_processing_code(self, user_request, file_names):
        """生成完整可执行代码，而非函数内部逻辑"""
        if not self.client:
            # 默认代码：直接返回所有数据
            return """import pandas as pd
    result_table = pd.concat(data_dict.values(), ignore_index=True)
    summary = f'共{len(result_table)}条记录'"""

        data_dict = self._load_file_data(file_names)

        # 准备文件元数据
        file_info = {}
        for filename, df in data_dict.items():
            file_info[filename] = {
                "columns": df.columns.tolist(),
                "sample": df.head(2).to_dict(orient='records')
            }

        prompt = f"""根据用户请求编写完整的Python处理代码:
用户需求: {user_request}
数据信息: {json.dumps(file_info, ensure_ascii=False)}

说明：
重要提示：返回的内容只能是可直接执行的代码，绝对不要有任何其他说明，保证返回的内容可以直接执行
0. 使用变量或函数时先进行定义，确保代码可以直接执行
1. 已存在变量data_dict（文件名到DataFrame的字典），可直接使用
2. 必须导入所需的库（如pandas）
3. 必须定义两个变量：
   - result_table：处理后的DataFrame结果（必须存在）
   - summary：字符串类型的总结，根据用户要求，可以包含：
     * 关键分析结论（如统计数量、趋势、异常点等）
     * 数据中发现的规律总结
     * 针对问题的解决方案或建议
     * 其他用户要求但无法被作为代码执行的信息
     禁止使用默认值，必须根据分析结果生成具体内容
4. 不要包含任何函数定义，直接编写可执行代码
5. 不需要return语句，只需确保定义了上述两个变量
6. 处理日志时，务必将包含类似"低/中/高"等含中文的字符串的列显式转换为字符串类型（如df['level'] = df['level'].astype(str)）
7. 对于时间/日期类型的列（如包含timestamp、datetime的列），必须显式转换为字符串类型（如df['time'] = df['time'].astype(str)），确保导出格式正确
8. 处理日志时，对于确定同义的表头信息，建议使用统一的名称，并对内容进行整合"""

        response = self.client.completions_create(
            model='deepseek-reasoner',
            prompt=prompt,
            max_tokens=5000,
            temperature=0.3
        )

        code_block = response.choices[0].message.content.strip()

        return code_block

    def direct_answer(self, user_request, file_names):
        """直接回答模式：生成日志总结，不返回表格数据"""
        data_dict = self._load_file_data(file_names)

        # 收集文件详细信息
        file_details = []
        for filename, df in data_dict.items():
            # 基础信息
            details = {
                "文件名": filename,
                "记录数": len(df),
                "列名": df.columns.tolist(),
                "数据类型分布": {col: str(df[col].dtype) for col in df.columns},
                "数据样本": df.head(min(3, len(df))).to_dict(orient='records')  # 最多3行样本
            }

            # 数值列统计
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

        # 构建提示词
        prompt = f"""基于以下日志文件的详细信息，回答用户问题并生成总结:
    文件详情: {json.dumps(file_details, ensure_ascii=False, default=str)}
    用户问题: {user_request}

    回答要求:
    1. 深入分析日志数据特征、潜在规律和关键信息
    2. 直接给出自然语言总结，不生成任何表格或结构化数据
    3. 内容具体有针对性，避免泛泛而谈
    4. 涉及统计信息时自然体现关键数值
    5. 用简洁易懂的中文表达"""

        # 调用API
        response = self.client.completions_create(
            model='deepseek-reasoner',
            prompt=prompt,
            max_tokens=5000,
            temperature=0.6
        )


        return {"summary": response.choices[0].message.content.strip()}

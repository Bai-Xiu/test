import re
import pandas as pd
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal


class AnalysisThread(QThread):
    update_signal = pyqtSignal(str)
    complete_signal = pyqtSignal(dict)

    def __init__(self, processor, file_paths, request, mode):
        super().__init__()
        self.processor = processor
        self.file_paths = file_paths
        self.request = request
        self.mode = mode

    def run(self):
        try:
            self.update_signal.emit("正在进行分析...")

            # 新增：对用户请求进行敏感词替换
            sanitized_request = self.processor.sensitive_manager.replace_sensitive_info(
                self.request) if self.processor.sensitive_manager else self.request

            if self.mode == "1":
                # 代码处理模式
                code_block = self.processor.generate_processing_code(sanitized_request, self.file_paths)
                self.update_signal.emit("代码生成完成，开始执行...")

                # 清理代码块
                cleaned_code = self.clean_code_block(code_block)

                # 执行清理后的代码
                result = self.execute_cleaned_code(cleaned_code)
            else:
                # 直接回答模式
                result = self.processor.direct_answer(sanitized_request, self.file_paths)

            self.complete_signal.emit({"status": "success", "result": result})
        except Exception as e:
            self.complete_signal.emit({"status": "error", "message": str(e)})

    def clean_code_block(self, code_block):
        """清理代码块，移除三重反引号和语言标识"""
        if not code_block:
            return ""

        cleaned = re.sub(r'^```[\w]*', '', code_block, flags=re.MULTILINE)
        cleaned = re.sub(r'```$', '', cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    def execute_cleaned_code(self, cleaned_code):
        # 准备数据字典
        data_dict = self.processor.load_data_files(self.file_paths)

        # 对数据框中的敏感信息进行替换（确保处理空值和非字符串类型）
        if self.processor.sensitive_manager:
            cleaned_data_dict = {}
            for filename, df in data_dict.items():
                # 复制数据框避免修改原始数据
                cleaned_df = df.copy()
                # 对字符串列进行敏感信息替换
                for col in cleaned_df.select_dtypes(include=['object']).columns:
                    cleaned_df[col] = cleaned_df[col].apply(
                        lambda x: self.processor.sensitive_manager.replace_sensitive_info(str(x))
                        if pd.notna(x) else x
                    )
                cleaned_data_dict[filename] = cleaned_df
            data_dict = cleaned_data_dict

        # 构建完整执行代码
        full_code = f"{cleaned_code}\n"

        # 执行代码
        local_vars = {
            'data_dict': data_dict,
            'pd': pd,
            'np': np
        }
        try:
            exec(full_code, globals(), local_vars)

            # 结果还原 - 确保处理空值
            if "result_table" in local_vars and isinstance(local_vars["result_table"], pd.DataFrame):
                result_table = local_vars["result_table"]
                # 对结果表格中的字符串列进行敏感信息还原
                if self.processor.sensitive_manager:
                    for col in result_table.select_dtypes(include=['object']).columns:
                        result_table[col] = result_table[col].apply(
                            lambda x: self.processor.sensitive_manager.restore_sensitive_info(str(x))
                            if pd.notna(x) else x
                        )
                local_vars["result_table"] = result_table

            # 提取结果
            result_table = local_vars.get('result_table')
            summary = local_vars.get('summary', '分析完成但未生成总结')

            return {"result_table": result_table, "summary": summary}
        except Exception as e:
            return {
                "summary": f"代码执行错误: {str(e)}\n\n执行的代码:\n{full_code}"
            }
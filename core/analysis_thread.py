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
            if self.mode == "1":
                # 代码处理模式
                code_block = self.processor.generate_processing_code(self.request, self.file_paths)
                self.update_signal.emit("代码生成完成，开始执行...")

                # 清理代码块，移除三重反引号和语言标识
                cleaned_code = self.clean_code_block(code_block)  # 修复方法名引用

                # 执行清理后的代码
                result = self.execute_cleaned_code(cleaned_code)
            else:
                # 直接回答模式
                result = self.processor.direct_answer(self.request, self.file_paths)

            self.complete_signal.emit({"status": "success", "result": result})
        except Exception as e:
            self.complete_signal.emit({"status": "error", "message": str(e)})

    def clean_code_block(self, code_block):  # 修复方法名定义
        """清理代码块，移除三重反引号和语言标识"""
        if not code_block:
            return ""

        # 移除代码块中的三重反引号和可能的语言标识（如```python）
        cleaned = re.sub(r'^```[\w]*', '', code_block, flags=re.MULTILINE)
        cleaned = re.sub(r'```$', '', cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    def execute_cleaned_code(self, cleaned_code):  # 修复方法名
        """执行完整代码（无包装函数）"""
        # 准备数据字典
        data_dict = self.processor.load_data_files(self.file_paths)

        # 构建完整执行代码（修复缩进问题）
        full_code = f"{cleaned_code}\n"  # 不添加额外缩进

        # 执行代码
        local_vars = {
            'data_dict': data_dict,
            'pd': pd,
            'np': np
        }
        try:
            exec(full_code, globals(), local_vars)

            # 提取结果
            result_table = local_vars.get('result_table')
            summary = local_vars.get('summary', '分析完成但未生成总结')

            return {"result_table": result_table, "summary": summary}
        except Exception as e:
            return {
                "summary": f"代码执行错误: {str(e)}\n\n执行的代码:\n{full_code}"
            }

import os
import pandas as pd
import json
import uuid
import hashlib  # 新增：用于生成更安全的替换标识


class SensitiveInfoManager:
    def __init__(self, config):
        self.config = config
        self.sensitive_map = {}  # 敏感词映射表: {敏感词: 替换词}
        self.reverse_map = {}  # 反向映射表: {替换词: 敏感词}
        self.sensitive_file = os.path.join(os.path.dirname(__file__), '../config/sensitive_words.json')

        # 确保配置目录存在
        os.makedirs(os.path.dirname(self.sensitive_file), exist_ok=True)
        self.load_sensitive_words()

    def load_sensitive_words(self):
        """加载敏感词映射表"""
        try:
            if os.path.exists(self.sensitive_file):
                with open(self.sensitive_file, 'r', encoding='utf-8') as f:
                    self.sensitive_map = json.load(f)
                self.reverse_map = {v: k for k, v in self.sensitive_map.items()}
                return True
        except Exception as e:
            print(f"加载敏感词失败: {str(e)}")
        return False

    def save_sensitive_words(self):
        """保存敏感词映射表"""
        try:
            with open(self.sensitive_file, 'w', encoding='utf-8') as f:
                json.dump(self.sensitive_map, f, ensure_ascii=False, indent=2)
            self.reverse_map = {v: k for k, v in self.sensitive_map.items()}
            return True
        except Exception as e:
            print(f"保存敏感词失败: {str(e)}")
            return False

    def replace_sensitive_info(self, text):
        """替换文本中的敏感信息"""
        for sensitive, replacement in self.sensitive_map.items():
            text = text.replace(sensitive, replacement)
        return text

    def restore_sensitive_info(self, text):
        """还原文本中的敏感信息"""
        for replacement, sensitive in self.reverse_map.items():
            text = text.replace(replacement, sensitive)
        return text

    def add_sensitive_word(self, sensitive, replacement=None):
        """添加敏感词及其替换词，自动生成高安全性替换词"""
        if not sensitive:
            return False

        # 优化：生成不可猜测的替换词（结合哈希和UUID）
        if not replacement:
            # 生成敏感词的哈希摘要（避免相同敏感词生成不同替换词）
            sensitive_hash = hashlib.sha256(sensitive.encode()).hexdigest()[:8]
            # 附加UUID确保唯一性
            unique_id = uuid.uuid4().hex[:8]
            replacement = f"[PROTECTED_{sensitive_hash}_{unique_id}]"

        self.sensitive_map[sensitive] = replacement
        self.reverse_map[replacement] = sensitive
        return True

    def remove_sensitive_word(self, sensitive):
        """移除敏感词"""
        if sensitive in self.sensitive_map:
            replacement = self.sensitive_map.pop(sensitive)
            self.reverse_map.pop(replacement, None)
            return True
        return False

    def import_from_csv(self, file_path):
        """从CSV文件导入敏感词表（需包含sensitive和replacement列）"""
        try:
            df = pd.read_csv(file_path)
            if 'sensitive' not in df.columns:
                return False, "CSV文件必须包含'sensitive'列"

            count = 0
            existing_sensitive = set(self.sensitive_map.keys())  # 已存在的敏感词集合

            for _, row in df.iterrows():
                sensitive = str(row['sensitive']).strip()
                if not sensitive:
                    continue  # 跳过空敏感词

                # 检查是否已存在
                if sensitive in existing_sensitive:
                    continue  # 去重处理，不导入重复项

                replacement = str(row.get('replacement', '')).strip() if 'replacement' in df.columns else None
                if self.add_sensitive_word(sensitive, replacement):
                    count += 1
                    existing_sensitive.add(sensitive)  # 添加到已存在集合，避免后续重复

            self.save_sensitive_words()
            return True, f"成功导入 {count} 条新敏感词"
        except Exception as e:
            return False, f"导入失败: {str(e)}"

    def get_all_sensitive_words(self):
        """获取所有敏感词列表"""
        return [(k, v) for k, v in self.sensitive_map.items()]

    # 新增：验证替换-还原流程的完整性
    def verify_integrity(self, test_text):
        """验证敏感词替换和还原是否完全可逆"""
        replaced = self.replace_sensitive_info(test_text)
        restored = self.restore_sensitive_info(replaced)
        return restored == test_text
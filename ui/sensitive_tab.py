from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QFileDialog, QLineEdit,
                             QGroupBox, QHeaderView, QDialog, QFormLayout)
from PyQt5.QtCore import Qt
from utils.helpers import show_info_message, show_error_message


class SensitiveTab(QWidget):
    def __init__(self, sensitive_manager, parent=None):
        super().__init__(parent)
        self.sensitive_manager = sensitive_manager
        self.parent = parent
        self.init_ui()
        self.refresh_table()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 导入按钮
        import_layout = QHBoxLayout()
        self.import_btn = QPushButton("导入敏感词表 (CSV)")
        self.import_btn.clicked.connect(self.import_sensitive_words)
        import_layout.addWidget(self.import_btn)
        import_layout.addStretch()

        # 添加敏感词
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("敏感词:"))
        self.sensitive_input = QLineEdit()
        add_layout.addWidget(self.sensitive_input)

        add_layout.addWidget(QLabel("替换词:"))
        self.replacement_input = QLineEdit()
        add_layout.addWidget(self.replacement_input)

        self.add_btn = QPushButton("添加")
        self.add_btn.clicked.connect(self.add_sensitive_word)
        add_layout.addWidget(self.add_btn)

        # 敏感词表格
        table_group = QGroupBox("敏感词列表")
        table_layout = QVBoxLayout(table_group)

        self.sensitive_table = QTableWidget()
        self.sensitive_table.setColumnCount(2)
        self.sensitive_table.setHorizontalHeaderLabels(["敏感词", "替换词"])
        self.sensitive_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sensitive_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sensitive_table.setSelectionBehavior(QTableWidget.SelectRows)

        table_layout.addWidget(self.sensitive_table)

        # 表格操作按钮
        table_btn_layout = QHBoxLayout()
        self.edit_btn = QPushButton("编辑选中项")
        self.edit_btn.clicked.connect(self.edit_selected)
        table_btn_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("删除选中项")
        self.delete_btn.clicked.connect(self.delete_selected)
        table_btn_layout.addWidget(self.delete_btn)

        table_btn_layout.addStretch()

        # 保存按钮
        self.save_btn = QPushButton("保存更改")
        self.save_btn.clicked.connect(self.save_changes)
        table_btn_layout.addWidget(self.save_btn)

        # 组装布局
        layout.addLayout(import_layout)
        layout.addLayout(add_layout)
        layout.addWidget(table_group)
        layout.addLayout(table_btn_layout)

    def refresh_table(self):
        """刷新表格数据"""
        sensitive_words = self.sensitive_manager.get_all_sensitive_words()
        self.sensitive_table.setRowCount(len(sensitive_words))

        for row, (sensitive, replacement) in enumerate(sensitive_words):
            self.sensitive_table.setItem(row, 0, QTableWidgetItem(sensitive))
            self.sensitive_table.setItem(row, 1, QTableWidgetItem(replacement))

    def import_sensitive_words(self):
        """导入敏感词表"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择CSV文件", "", "CSV文件 (*.csv)"
        )

        if file_path:
            success, message = self.sensitive_manager.import_from_csv(file_path)
            if success:
                show_info_message(self, "导入成功", message)
                self.refresh_table()
            else:
                show_error_message(self, "导入失败", message)

    def add_sensitive_word(self):
        """添加敏感词"""
        sensitive = self.sensitive_input.text().strip()
        replacement = self.replacement_input.text().strip() or None

        if not sensitive:
            show_error_message(self, "输入错误", "敏感词不能为空")
            return

        if self.sensitive_manager.add_sensitive_word(sensitive, replacement):
            show_info_message(self, "添加成功", f"已添加敏感词: {sensitive}")
            self.sensitive_input.clear()
            self.replacement_input.clear()
            self.refresh_table()
        else:
            show_error_message(self, "添加失败", "无法添加敏感词，请检查输入")

    def edit_selected(self):
        """编辑选中的敏感词"""
        selected_rows = set(item.row() for item in self.sensitive_table.selectedItems())
        if len(selected_rows) != 1:
            show_info_message(self, "提示", "请选择一行进行编辑")
            return

        row = list(selected_rows)[0]
        original_sensitive = self.sensitive_table.item(row, 0).text()
        original_replacement = self.sensitive_table.item(row, 1).text()

        # 创建编辑对话框，移除问号按钮
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑敏感词")
        # 关键修改：移除窗口的上下文帮助按钮（问号按钮）
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        form_layout = QFormLayout(dialog)

        sensitive_edit = QLineEdit(original_sensitive)
        replacement_edit = QLineEdit(original_replacement)

        form_layout.addRow("敏感词:", sensitive_edit)
        form_layout.addRow("替换词:", replacement_edit)

        # 对话框按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        form_layout.addRow(btn_layout)

        if dialog.exec_() == QDialog.Accepted:
            new_sensitive = sensitive_edit.text().strip()
            new_replacement = replacement_edit.text().strip()

            if not new_sensitive:
                show_error_message(self, "输入错误", "敏感词不能为空")
                return

            # 更新敏感词
            self.sensitive_manager.remove_sensitive_word(original_sensitive)
            if self.sensitive_manager.add_sensitive_word(new_sensitive, new_replacement):
                show_info_message(self, "编辑成功", "敏感词已更新")
                self.refresh_table()

    def delete_selected(self):
        """删除选中的敏感词"""
        selected_rows = set(item.row() for item in self.sensitive_table.selectedItems())
        if not selected_rows:
            show_info_message(self, "提示", "请选择要删除的行")
            return

        # 按行号从大到小删除
        for row in sorted(selected_rows, reverse=True):
            sensitive = self.sensitive_table.item(row, 0).text()
            self.sensitive_manager.remove_sensitive_word(sensitive)

        show_info_message(self, "删除成功", f"已删除 {len(selected_rows)} 条敏感词")
        self.refresh_table()

    def save_changes(self):
        """保存更改"""
        if self.sensitive_manager.save_sensitive_words():
            show_info_message(self, "保存成功", "敏感词已保存")
        else:
            show_error_message(self, "保存失败", "无法保存敏感词")
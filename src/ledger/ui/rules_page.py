from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ledger.services.attribution import CorrectionRule, attribute_projects
from ledger.services.balance_trace import trace_project_balance
from ledger.storage.repository import LedgerRepository

PAGE_STYLE = """
QWidget { background: #ffffff; color: #1a1a1a; }
QLabel#title {
    font-size: 18px;
    font-weight: bold;
    color: #0078d4;
    padding: 8px 0;
}
QLabel#section {
    font-size: 13px;
    font-weight: bold;
    color: #005a9e;
    margin-top: 8px;
}
QLabel#status_ok { color: #107c10; font-size: 13px; }
QLabel#status_err { color: #d83b01; font-size: 13px; }
QLineEdit {
    background: #ffffff;
    border: 1px solid #d1d1d1;
    border-radius: 2px;
    padding: 6px 10px;
    color: #1a1a1a;
    font-size: 13px;
}
QLineEdit:focus { border-color: #0078d4; }
QPushButton {
    background: #ffffff;
    border: 1px solid #d1d1d1;
    border-radius: 2px;
    padding: 6px 16px;
    color: #1a1a1a;
    font-size: 13px;
}
QPushButton:hover { background: #f3f3f3; border-color: #b0b0b0; }
QPushButton#primary {
    background: #0078d4;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#primary:hover { background: #106ebe; }
QPushButton#danger {
    background: #ffffff;
    color: #d83b01;
    border: 1px solid #d83b01;
}
QPushButton#danger:hover { background: #fdf3f0; }
QListWidget {
    background: #ffffff;
    border: 1px solid #d1d1d1;
    border-radius: 0px;
    color: #1a1a1a;
    font-size: 13px;
}
QListWidget::item { padding: 8px 12px; }
QListWidget::item:selected { background: #cce4f7; color: #1a1a1a; }
QListWidget::item:alternate { background: #f9f9f9; }
"""


class RulesPage(QWidget):
    def __init__(self, repo: LedgerRepository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setStyleSheet(PAGE_STYLE)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(12)

        title = QLabel("关键词规则管理")
        title.setObjectName("title")
        root.addWidget(title)

        # 输入区
        section1 = QLabel("新增规则")
        section1.setObjectName("section")
        root.addWidget(section1)

        form = QFormLayout()
        form.setSpacing(10)

        self.match_input = QLineEdit()
        self.match_input.setPlaceholderText("摘要中包含的关键词或原始摘要")
        self.match_input.setMinimumWidth(420)
        form.addRow("匹配关键词：", self.match_input)

        self.project_input = QLineEdit()
        self.project_input.setPlaceholderText("归入的主项目名称")
        form.addRow("项目名称：", self.project_input)

        root.addLayout(form)

        # 保存按钮
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("保存规则")
        self.save_btn.setObjectName("primary")
        self.save_btn.setFixedWidth(120)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 状态
        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        # 已保存规则列表
        section2 = QLabel("已保存的规则")
        section2.setObjectName("section")
        root.addWidget(section2)

        self.rules_list = QListWidget()
        self.rules_list.setAlternatingRowColors(True)
        root.addWidget(self.rules_list)

        # 删除按钮
        del_row = QHBoxLayout()
        self.delete_btn = QPushButton("删除选中规则")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.setFixedWidth(140)
        del_row.addWidget(self.delete_btn)
        del_row.addStretch()
        root.addLayout(del_row)

        self.save_btn.clicked.connect(self._save_rule)
        self.delete_btn.clicked.connect(self._delete_rule)

    def refresh_rules(self) -> None:
        self.rules_list.clear()
        rows = self.repo.load_rows()
        rules = self.repo.load_rules()
        # 归并分组
        groups = attribute_projects(rows, rules)
        # 计算每个主项目的借贷合计和配平状态
        project_stats = {}
        for group in groups:
            trace = trace_project_balance(group.rows)
            debit = sum(line.original_amount for line in trace.lines if line.direction == "借")
            credit = sum(line.original_amount for line in trace.lines if line.direction == "贷")
            diff = debit - credit
            if abs(diff) < 0.01:
                status = f"借: {debit:,.2f}  贷: {credit:,.2f}  ✓已配平"
            else:
                if diff > 0:
                    status = f"借: {debit:,.2f}  贷: {credit:,.2f}  差额: {abs(diff):,.2f}(借)"
                else:
                    status = f"借: {debit:,.2f}  贷: {credit:,.2f}  差额: {abs(diff):,.2f}(贷)"
            project_stats[group.project_name] = status
        for rule in rules:
            status = project_stats.get(rule.project_name, "无数据")
            item = QListWidgetItem(
                f"「{rule.match_text}」  →  {rule.project_name}    {status}"
            )
            item.setData(Qt.UserRole, (rule.match_text, rule.project_name))
            self.rules_list.addItem(item)

    def save_current_rule(self) -> None:
        self._save_rule()

    def remove_rule_at(self, index: int) -> None:
        item = self.rules_list.item(index)
        if item:
            match_text, project_name = item.data(Qt.UserRole)
            self.repo.delete_rule(match_text, project_name)
            self.refresh_rules()

    def _save_rule(self) -> None:
        match_text = self.match_input.text().strip()
        project_name = self.project_input.text().strip()

        if not match_text or not project_name:
            self.status_label.setObjectName("status_err")
            self.status_label.setText("✗ 请填写匹配关键词和项目名称")
            self._refresh_style()
            return

        rule = CorrectionRule(match_text=match_text, project_name=project_name)
        self.repo.save_rule(rule)
        self.match_input.clear()
        self.project_input.clear()
        self.status_label.setObjectName("status_ok")
        self.status_label.setText(
            f"✓ 已保存规则：命中「{match_text}」的摘要将归入「{project_name}」，刷新分析后生效"
        )
        self._refresh_style()
        self.refresh_rules()

    def _delete_rule(self) -> None:
        item = self.rules_list.currentItem()
        if not item:
            return
        match_text, project_name = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除规则「{match_text}」→「{project_name}」？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.repo.delete_rule(match_text, project_name)
            self.status_label.setObjectName("status_ok")
            self.status_label.setText(f"✓ 已取消规则「{match_text}」，刷新分析后生效")
            self._refresh_style()
            self.refresh_rules()

    def _refresh_style(self) -> None:
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

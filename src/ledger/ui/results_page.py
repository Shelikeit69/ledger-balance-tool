from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QDialog,
    QCheckBox,
    QScrollArea,
    QDialogButtonBox,
)

from ledger.services.attribution import CorrectionRule, attribute_projects
from ledger.services.balance_trace import ProjectTrace, trace_project_balance
from ledger.services.exporter import export_summary
from ledger.services.ai_suggester import suggest_rules
from ledger.storage.repository import LedgerRepository

def _install_copy_shortcut(table: QTableWidget) -> None:
    """为表格绑定 Ctrl+C，按行列顺序复制选中单元格文字。"""
    shortcut = QShortcut(QKeySequence.StandardKey.Copy, table)
    shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)

    def _copy() -> None:
        selected = table.selectedItems()
        if not selected:
            return
        cell_map: dict[int, dict[int, str]] = {}
        for item in selected:
            cell_map.setdefault(item.row(), {})[item.column()] = item.text()
        lines = [
            "\t".join(cell_map[r][c] for c in sorted(cell_map[r]))
            for r in sorted(cell_map)
        ]
        QApplication.clipboard().setText("\n".join(lines))

    shortcut.activated.connect(_copy)


PAGE_STYLE = """
QWidget { background: #ffffff; color: #1a1a1a; }
QLabel#title {
    font-size: 18px;
    font-weight: bold;
    color: #0078d4;
    padding: 8px 0;
}
QLabel#summary_bar {
    background: #f0f6ff;
    border: 1px solid #c7e0f4;
    border-radius: 2px;
    padding: 10px 16px;
    font-size: 13px;
    color: #1a1a1a;
}
QLabel#status_ok { color: #107c10; font-size: 13px; }
QLabel#status_err { color: #d83b01; font-size: 13px; }
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
QPushButton#ai_btn {
    background: #0078d4;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#ai_btn:hover { background: #106ebe; }
QTableWidget {
    background: #ffffff;
    border: 1px solid #d1d1d1;
    border-radius: 0px;
    gridline-color: #e5e5e5;
    font-size: 13px;
    color: #1a1a1a;
}
QTableWidget::item { padding: 6px 10px; }
QTableWidget::item:selected { background: #cce4f7; color: #1a1a1a; }
QHeaderView::section {
    background: #f3f3f3;
    color: #1a1a1a;
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid #d1d1d1;
    border-right: 1px solid #e5e5e5;
    font-weight: bold;
}
"""


class ResultsPage(QWidget):
    def __init__(self, repo: LedgerRepository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self._items: list[tuple] = []
        self.setStyleSheet(PAGE_STYLE)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(12)

        title = QLabel("配平结果")
        title.setObjectName("title")
        root.addWidget(title)

        # 汇总栏
        self.summary_bar = QLabel("尚未加载数据")
        self.summary_bar.setObjectName("summary_bar")
        root.addWidget(self.summary_bar)

        # 按钮行
        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.ai_btn = QPushButton("AI 分析")
        self.ai_btn.setObjectName("ai_btn")
        self.export_btn = QPushButton("导出 Excel")
        self.export_btn.setObjectName("primary")

        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.ai_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 状态
        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        # 结果表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "项目名称", "挂账金额", "方向", "剩余记录数", "状态汇总"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        _install_copy_shortcut(self.table)
        root.addWidget(self.table)

        self.refresh_btn.clicked.connect(self.refresh_results)
        self.ai_btn.clicked.connect(self._run_ai_analysis)
        self.export_btn.clicked.connect(self._export)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

    def refresh_results(self) -> None:
        rows = self.repo.load_rows()
        rules = self.repo.load_rules()

        if not rows:
            self.summary_bar.setText("暂无数据，请先导入账目文件")
            self.table.setRowCount(0)
            return

        groups = attribute_projects(rows, rules)
        self._items = []
        for group in groups:
            trace = trace_project_balance(group.rows, rules=rules)
            self._items.append((group, trace))

        # 只显示有挂账的项目
        outstanding = [(g, t) for g, t in self._items if t.outstanding_amount > 0]

        total_outstanding = sum(t.outstanding_amount for _, t in outstanding)
        self.summary_bar.setText(
            f"共 {len(rows)} 条记录　|　"
            f"未配平项目：{len(outstanding)} 个　|　"
            f"总挂账金额：{total_outstanding:,.2f}"
        )

        self.table.setRowCount(len(outstanding))
        for row_idx, (group, trace) in enumerate(outstanding):
            from ledger.services.balance_trace import (
                remaining_trace_lines,
                trace_status_summary,
            )
            self.table.setItem(row_idx, 0, QTableWidgetItem(group.project_name))
            self.table.setItem(row_idx, 1, QTableWidgetItem(f"{trace.outstanding_amount:,.2f}"))
            self.table.setItem(row_idx, 2, QTableWidgetItem(trace.outstanding_direction))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(len(remaining_trace_lines(trace)))))
            self.table.setItem(row_idx, 4, QTableWidgetItem(trace_status_summary(trace)))

        self.status_label.setText("")

    def row_count(self) -> int:
        return self.table.rowCount()

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        outstanding = [(g, t) for g, t in self._items if t.outstanding_amount > 0]
        if row < 0 or row >= len(outstanding):
            return
        group, trace = outstanding[row]
        _ProjectDetailDialog(group.project_name, trace, self).exec()

    def _run_ai_analysis(self) -> None:
        api_key = self.repo.load_setting("minimax_api_key")
        if not api_key:
            QMessageBox.warning(self, "缺少 API Key", "请先在「设置」页填写 MiniMax API Key")
            return

        outstanding_groups = [g for g, t in self._items if t.outstanding_amount > 0]
        if not outstanding_groups:
            QMessageBox.information(self, "无需分析", "当前没有未配平的项目")
            return

        self.status_label.setObjectName("status_ok")
        self.status_label.setText("AI 分析中，请稍候...")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        QApplication_processEvents()

        try:
            model = self.repo.load_setting("minimax_model") or "MiniMax-Text-01"
            outstanding_traces = [t for _, t in self._items if t.outstanding_amount > 0]
            suggestions = suggest_rules(outstanding_groups, api_key, model, traces=outstanding_traces)
        except Exception as e:
            self.status_label.setObjectName("status_err")
            self.status_label.setText(f"✗ AI 分析失败：{e}")
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            return

        if not suggestions:
            self.status_label.setText("✓ AI 分析完成，未发现可归并的项目")
            return

        # 弹出确认对话框
        confirmed = _AISuggestionDialog(suggestions, self).exec_and_get()
        if confirmed:
            for rule in confirmed:
                self.repo.save_rule(rule)
            self.status_label.setObjectName("status_ok")
            self.status_label.setText(f"✓ 已保存 {len(confirmed)} 条 AI 建议规则，正在刷新...")
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            self.refresh_results()
        else:
            self.status_label.setText("已取消 AI 建议")

    def _export(self) -> None:
        if not self._items:
            QMessageBox.warning(self, "无数据", "请先刷新结果再导出")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "导出配平报告", "配平报告.xlsx", "Excel 文件 (*.xlsx)"
        )
        if not path:
            return

        try:
            export_summary(self._items, Path(path))
            self.status_label.setObjectName("status_ok")
            self.status_label.setText(f"✓ 已导出：{path}")
        except Exception as e:
            self.status_label.setObjectName("status_err")
            self.status_label.setText(f"✗ 导出失败：{e}")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


_DETAIL_STYLE = """
    QDialog { background: #ffffff; color: #1a1a1a; }
    QLabel { color: #1a1a1a; }
    QLabel#detail_title {
        font-size: 15px; font-weight: bold; color: #0078d4; padding: 4px 0;
    }
    QTableWidget {
        background: #ffffff;
        border: 1px solid #d1d1d1;
        gridline-color: #e5e5e5;
        font-size: 13px;
        color: #1a1a1a;
    }
    QTableWidget::item { padding: 5px 8px; }
    QTableWidget::item:selected { background: #cce4f7; color: #1a1a1a; }
    QHeaderView::section {
        background: #f3f3f3;
        color: #1a1a1a;
        padding: 5px 8px;
        border: none;
        border-bottom: 1px solid #d1d1d1;
        border-right: 1px solid #e5e5e5;
        font-weight: bold;
    }
    QPushButton {
        background: #ffffff; border: 1px solid #d1d1d1;
        border-radius: 2px; padding: 6px 16px; color: #1a1a1a;
    }
    QPushButton:hover { background: #f3f3f3; }
"""

_STATUS_ZH = {
    "uncleared": "未清",
    "partially_cleared": "部分冲平",
    "cleared": "已清",
}


class _ProjectDetailDialog(QDialog):
    def __init__(self, project_name: str, trace, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"明细 — {project_name}")
        self.setMinimumSize(900, 500)
        self.setStyleSheet(_DETAIL_STYLE)
        self._build_ui(project_name, trace)

    def _build_ui(self, project_name: str, trace) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        title = QLabel(f"{project_name}")
        title.setObjectName("detail_title")
        root.addWidget(title)

        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "凭证字号", "日期", "摘要", "借方金额", "贷方金额",
            "方向", "剩余金额", "状态",
        ])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectItems)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        _install_copy_shortcut(table)

        from ledger.services.importer import NormalizedLedgerRow
        lines = trace.lines
        table.setRowCount(len(lines))
        for i, line in enumerate(lines):
            date_str = line.posted_date.isoformat() if line.posted_date else ""
            table.setItem(i, 0, QTableWidgetItem(line.voucher_no))
            table.setItem(i, 1, QTableWidgetItem(date_str))
            table.setItem(i, 2, QTableWidgetItem(line.summary))
            # 借贷金额：根据方向判断填入哪列
            if line.direction == "借":
                table.setItem(i, 3, QTableWidgetItem(f"{line.original_amount:,.2f}"))
                table.setItem(i, 4, QTableWidgetItem(""))
            else:
                table.setItem(i, 3, QTableWidgetItem(""))
                table.setItem(i, 4, QTableWidgetItem(f"{line.original_amount:,.2f}"))
            table.setItem(i, 5, QTableWidgetItem(line.direction))
            table.setItem(i, 6, QTableWidgetItem(f"{line.remaining_amount:,.2f}"))
            table.setItem(i, 7, QTableWidgetItem(_STATUS_ZH.get(line.status, line.status)))

        root.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


def QApplication_processEvents():
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()


class _AISuggestionDialog(QDialog):
    def __init__(self, suggestions: list[CorrectionRule], parent=None) -> None:
        super().__init__(parent)
        self.suggestions = suggestions
        self.checkboxes: list[QCheckBox] = []
        self.setWindowTitle("AI 建议规则")
        self.setMinimumWidth(600)
        self.setStyleSheet("""
            QDialog { background: #ffffff; color: #1a1a1a; }
            QLabel { color: #1a1a1a; }
            QCheckBox { color: #1a1a1a; font-size: 13px; padding: 4px 0; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QPushButton {
                background: #ffffff; border: 1px solid #d1d1d1;
                border-radius: 2px; padding: 6px 16px; color: #1a1a1a;
            }
            QPushButton:hover { background: #f3f3f3; }
        """)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(24, 20, 24, 20)

        root.addWidget(QLabel(f"AI 发现 {len(self.suggestions)} 条可能的归并建议，请勾选要保存的规则："))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(400)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(4)

        for rule in self.suggestions:
            cb = QCheckBox(f"「{rule.match_text}」  →  {rule.project_name}")
            cb.setChecked(True)
            cb.setProperty("rule", rule)
            inner_layout.addWidget(cb)
            self.checkboxes.append(cb)

        scroll.setWidget(inner)
        root.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def exec_and_get(self) -> list[CorrectionRule] | None:
        if self.exec() == QDialog.Accepted:
            return [
                cb.property("rule")
                for cb in self.checkboxes
                if cb.isChecked()
            ]
        return None

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ledger.services.ai_suggester import AiMatchSuggestion, analyze_candidate_pairs
from ledger.services.exporter import export_workbook
from ledger.services.matching_engine import CandidatePair, cancel_match, confirm_match, generate_ai_candidates, run_matching_cycle
from ledger.storage.repository import EntryRecord, LedgerRepository, MatchRecord

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
}
QLabel#status_ok { color: #107c10; font-size: 13px; }
QLabel#status_err { color: #d83b01; font-size: 13px; }
QPushButton {
    background: #ffffff;
    border: 1px solid #d1d1d1;
    border-radius: 2px;
    padding: 6px 14px;
    color: #1a1a1a;
    font-size: 13px;
}
QPushButton#primary {
    background: #0078d4;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #d1d1d1;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 12px;
}
QTableWidget {
    background: #ffffff;
    border: 1px solid #d1d1d1;
    gridline-color: #e5e5e5;
    font-size: 12px;
}
QHeaderView::section {
    background: #f3f3f3;
    padding: 6px 8px;
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
        self.entries: list[EntryRecord] = []
        self.matches: list[MatchRecord] = []
        self.pending_candidates: list[CandidatePair] = []
        self.ai_suggestions: list[AiMatchSuggestion] = []
        self.setStyleSheet(PAGE_STYLE)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("分录配平结果")
        title.setObjectName("title")
        root.addWidget(title)

        self.summary_bar = QLabel("暂无数据，请先导入账目文件")
        self.summary_bar.setObjectName("summary_bar")
        root.addWidget(self.summary_bar)

        toolbar = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.auto_match_btn = QPushButton("自动匹配")
        self.auto_match_btn.setObjectName("primary")
        self.ai_btn = QPushButton("AI 分析候选")
        self.manual_btn = QPushButton("手工匹配选中项")
        self.cancel_btn = QPushButton("取消选中匹配")
        self.export_btn = QPushButton("导出 Excel")
        self.only_unmatched_checkbox = QCheckBox("只看 remaining_amount > 0")
        self.only_unmatched_checkbox.setChecked(True)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.auto_match_btn)
        toolbar.addWidget(self.ai_btn)
        toolbar.addWidget(self.manual_btn)
        toolbar.addWidget(self.cancel_btn)
        toolbar.addWidget(self.export_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.only_unmatched_checkbox)
        root.addLayout(toolbar)

        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_entries_panel())
        splitter.addWidget(self._build_candidates_panel())
        splitter.addWidget(self._build_matches_panel())
        splitter.setSizes([560, 440, 440])
        root.addWidget(splitter, 1)

        self.refresh_btn.clicked.connect(self.refresh_results)
        self.auto_match_btn.clicked.connect(self._run_auto_matching)
        self.ai_btn.clicked.connect(self._run_ai_analysis)
        self.manual_btn.clicked.connect(self._confirm_manual_match)
        self.cancel_btn.clicked.connect(self._cancel_selected_match)
        self.export_btn.clicked.connect(self._export)
        self.only_unmatched_checkbox.toggled.connect(self.refresh_results)

    def _build_entries_panel(self) -> QWidget:
        box = QGroupBox("左栏：分录状态")
        layout = QVBoxLayout(box)
        self.entries_table = QTableWidget()
        self.entries_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.entries_table.setSelectionMode(QTableWidget.MultiSelection)
        self.entries_table.setColumnCount(8)
        self.entries_table.setHorizontalHeaderLabels(
            ["ID", "摘要", "借方", "贷方", "原始", "已匹配", "剩余", "状态"]
        )
        self.entries_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.entries_table.verticalHeader().setVisible(False)
        layout.addWidget(self.entries_table)
        return box

    def _build_candidates_panel(self) -> QWidget:
        box = QGroupBox("中栏：候选匹配建议")
        layout = QVBoxLayout(box)
        self.candidates_table = QTableWidget()
        self.candidates_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.candidates_table.setColumnCount(6)
        self.candidates_table.setHorizontalHeaderLabels(
            ["来源", "模式", "借方分录", "贷方分录", "金额", "原因"]
        )
        self.candidates_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.candidates_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.candidates_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.candidates_table.verticalHeader().setVisible(False)
        layout.addWidget(self.candidates_table)

        confirm_row = QHBoxLayout()
        self.confirm_candidate_btn = QPushButton("确认选中建议")
        confirm_row.addWidget(self.confirm_candidate_btn)
        confirm_row.addStretch()
        layout.addLayout(confirm_row)
        self.confirm_candidate_btn.clicked.connect(self._confirm_selected_candidate)
        return box

    def _build_matches_panel(self) -> QWidget:
        box = QGroupBox("右栏：已匹配记录")
        layout = QVBoxLayout(box)
        self.matches_table = QTableWidget()
        self.matches_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.matches_table.setColumnCount(5)
        self.matches_table.setHorizontalHeaderLabels(["匹配ID", "类型", "模式", "金额", "原因"])
        self.matches_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.matches_table.verticalHeader().setVisible(False)
        layout.addWidget(self.matches_table)

        self.match_detail_label = QLabel("选择一条匹配记录后，可用上方按钮取消。")
        self.match_detail_label.setWordWrap(True)
        layout.addWidget(self.match_detail_label)
        return box

    def refresh_results(self) -> None:
        only_unmatched = self.only_unmatched_checkbox.isChecked()
        self.entries = self.repo.list_entries(
            row_type="entry",
            only_unmatched=only_unmatched,
            sort_by_remaining_desc=True,
        )
        self.matches = self.repo.list_match_records()
        self.pending_candidates = generate_ai_candidates(self.repo)
        self.ai_suggestions = []

        total_entries = self.repo.count_entries(row_type="entry")
        outstanding_entries = self.repo.list_entries(row_type="entry", only_unmatched=True)
        total_remaining = sum((entry.remaining_amount for entry in outstanding_entries), Decimal("0.00"))
        self.summary_bar.setText(
            f"entry 总数：{total_entries}  |  未配平：{len(outstanding_entries)}  |  挂账总额：{total_remaining:,.2f}  |  已匹配记录：{len(self.matches)}"
        )

        self._render_entries_table()
        self._render_candidates_table()
        self._render_matches_table()
        self.status_label.setText("")

    def _render_entries_table(self) -> None:
        self.entries_table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            self.entries_table.setItem(row, 0, QTableWidgetItem(str(entry.id)))
            self.entries_table.setItem(row, 1, QTableWidgetItem(entry.summary))
            self.entries_table.setItem(row, 2, QTableWidgetItem(f"{entry.debit_amount:,.2f}"))
            self.entries_table.setItem(row, 3, QTableWidgetItem(f"{entry.credit_amount:,.2f}"))
            self.entries_table.setItem(row, 4, QTableWidgetItem(f"{entry.original_amount:,.2f}"))
            self.entries_table.setItem(row, 5, QTableWidgetItem(f"{entry.matched_amount:,.2f}"))
            self.entries_table.setItem(row, 6, QTableWidgetItem(f"{entry.remaining_amount:,.2f}"))
            self.entries_table.setItem(row, 7, QTableWidgetItem(entry.status))

    def _render_candidates_table(self) -> None:
        rows: list[tuple[str, str, str, str, str, str]] = []
        for candidate in self.pending_candidates:
            rows.append(
                (
                    "自动候选",
                    candidate.match_mode,
                    ", ".join(str(entry.id) for entry in candidate.debit_entries),
                    ", ".join(str(entry.id) for entry in candidate.credit_entries),
                    f"{candidate.matched_amount:,.2f}",
                    candidate.reason,
                )
            )
        for suggestion in self.ai_suggestions:
            rows.append(
                (
                    "AI 建议" if suggestion.recommended else "AI 不建议",
                    suggestion.match_mode,
                    ", ".join(str(entry_id) for entry_id in suggestion.debit_entry_ids),
                    ", ".join(str(entry_id) for entry_id in suggestion.credit_entry_ids),
                    f"{suggestion.matched_amount:,.2f}",
                    suggestion.reason,
                )
            )

        self.candidates_table.setRowCount(len(rows))
        for row_index, row_values in enumerate(rows):
            for column, value in enumerate(row_values):
                self.candidates_table.setItem(row_index, column, QTableWidgetItem(value))

    def _render_matches_table(self) -> None:
        self.matches_table.setRowCount(len(self.matches))
        for row, match in enumerate(self.matches):
            self.matches_table.setItem(row, 0, QTableWidgetItem(str(match.id)))
            self.matches_table.setItem(row, 1, QTableWidgetItem(match.match_type))
            self.matches_table.setItem(row, 2, QTableWidgetItem(match.match_mode))
            self.matches_table.setItem(row, 3, QTableWidgetItem(f"{match.matched_amount:,.2f}"))
            self.matches_table.setItem(row, 4, QTableWidgetItem(match.reason))
        if self.matches:
            latest = self.matches[0]
            self.match_detail_label.setText(
                "最新匹配涉及："
                + ", ".join(f"{link.role}:{link.entry_id}/{link.used_amount:,.2f}" for link in latest.links)
            )
        else:
            self.match_detail_label.setText("暂无匹配记录。")

    def _run_auto_matching(self) -> None:
        created = run_matching_cycle(self.repo)
        self.status_label.setObjectName("status_ok")
        self.status_label.setText(f"✓ 自动匹配完成，本轮新增 {created} 条匹配记录")
        _refresh_style(self.status_label)
        self.refresh_results()

    def _run_ai_analysis(self) -> None:
        api_key = self.repo.load_setting("minimax_api_key")
        if not api_key:
            QMessageBox.warning(self, "缺少 API Key", "请先在“设置”页填写 MiniMax API Key")
            return
        if not self.pending_candidates:
            QMessageBox.information(self, "无候选", "当前没有可供 AI 判断的金额候选")
            return

        candidate_pairs = [
            (candidate.debit_entries, candidate.credit_entries, candidate.matched_amount)
            for candidate in self.pending_candidates
        ]
        model = self.repo.load_setting("minimax_model")

        QApplication.processEvents()
        try:
            self.ai_suggestions = analyze_candidate_pairs(candidate_pairs, api_key=api_key, model=model or "")
        except Exception as exc:
            self.status_label.setObjectName("status_err")
            self.status_label.setText(f"✗ AI 分析失败：{exc}")
            _refresh_style(self.status_label)
            return

        self.status_label.setObjectName("status_ok")
        self.status_label.setText(f"✓ AI 分析完成，返回 {len(self.ai_suggestions)} 条建议")
        _refresh_style(self.status_label)
        self._render_candidates_table()

    def _confirm_selected_candidate(self) -> None:
        row = self.candidates_table.currentRow()
        if row < 0:
            return
        source = self.candidates_table.item(row, 0).text()
        debit_ids = [int(item) for item in self.candidates_table.item(row, 2).text().split(", ") if item]
        credit_ids = [int(item) for item in self.candidates_table.item(row, 3).text().split(", ") if item]
        matched_amount = Decimal(self.candidates_table.item(row, 4).text().replace(",", ""))
        reason = self.candidates_table.item(row, 5).text()

        debit_entries = self.repo.get_entries(debit_ids)
        credit_entries = self.repo.get_entries(credit_ids)
        match_type = "ai_confirmed" if source.startswith("AI") else "manual"
        match_mode = self.candidates_table.item(row, 1).text()

        confirm_match(
            self.repo,
            debit_entries=debit_entries,
            credit_entries=credit_entries,
            matched_amount=matched_amount,
            match_mode=match_mode,
            reason=reason,
            created_by="user",
            match_type=match_type,
        )
        self.status_label.setObjectName("status_ok")
        self.status_label.setText("✓ 已确认选中建议")
        _refresh_style(self.status_label)
        self.refresh_results()

    def _confirm_manual_match(self) -> None:
        selected_rows = sorted({index.row() for index in self.entries_table.selectionModel().selectedRows()})
        if not selected_rows:
            QMessageBox.information(self, "未选择分录", "请先在左栏选择至少两条分录")
            return

        selected_entries = [self.entries[row] for row in selected_rows]
        debit_entries = [entry for entry in selected_entries if entry.amount_side == "debit"]
        credit_entries = [entry for entry in selected_entries if entry.amount_side == "credit"]
        if not debit_entries or not credit_entries:
            QMessageBox.warning(self, "选择无效", "手工匹配必须同时包含借方和贷方分录")
            return

        debit_total = sum((entry.remaining_amount for entry in debit_entries), Decimal("0.00"))
        credit_total = sum((entry.remaining_amount for entry in credit_entries), Decimal("0.00"))
        matched_amount = min(debit_total, credit_total)
        if matched_amount <= Decimal("0.00"):
            QMessageBox.warning(self, "无可匹配金额", "所选分录没有可用的 remaining_amount")
            return

        match_mode = f"{len(debit_entries)}:{len(credit_entries)}"
        confirm_match(
            self.repo,
            debit_entries=debit_entries,
            credit_entries=credit_entries,
            matched_amount=matched_amount,
            match_mode=match_mode,
            reason="用户手工确认匹配",
            created_by="user",
            match_type="manual",
        )
        self.status_label.setObjectName("status_ok")
        self.status_label.setText("✓ 已完成手工匹配")
        _refresh_style(self.status_label)
        self.refresh_results()

    def _cancel_selected_match(self) -> None:
        row = self.matches_table.currentRow()
        if row < 0:
            return
        match_id = int(self.matches_table.item(row, 0).text())
        reply = QMessageBox.question(
            self,
            "确认取消",
            f"确定取消匹配记录 #{match_id}？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            cancel_match(self.repo, match_id)
            self.status_label.setObjectName("status_ok")
            self.status_label.setText(f"✓ 已取消匹配 #{match_id}")
            _refresh_style(self.status_label)
            self.refresh_results()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出分录配平报告",
            "分录配平报告.xlsx",
            "Excel 文件 (*.xlsx)",
        )
        if not path:
            return
        export_workbook(self.repo.list_entries(row_type="entry"), self.repo.list_match_records(), Path(path))
        self.status_label.setObjectName("status_ok")
        self.status_label.setText(f"✓ 已导出：{path}")
        _refresh_style(self.status_label)


def _refresh_style(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ledger.services.importer import import_paths
from ledger.services.matching_engine import run_matching_cycle
from ledger.storage.repository import LedgerRepository

PAGE_STYLE = """
QWidget { background: #ffffff; color: #1a1a1a; }
QLabel#title {
    font-size: 18px;
    font-weight: bold;
    color: #0078d4;
    padding: 8px 0;
}
QLabel#drop_zone {
    border: 2px dashed #b0b0b0;
    border-radius: 4px;
    color: #605e5c;
    font-size: 14px;
    padding: 60px 40px;
    qproperty-alignment: AlignCenter;
    background: #fafafa;
}
QLabel#status { color: #107c10; font-size: 13px; }
QLabel#error  { color: #d83b01; font-size: 13px; }
QLabel#hint   { color: #605e5c; font-size: 12px; }
QPushButton {
    background: #0078d4;
    color: #ffffff;
    border: none;
    border-radius: 2px;
    padding: 8px 24px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton:hover { background: #106ebe; }
"""


class ImportPage(QWidget):
    def __init__(self, repo: LedgerRepository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setStyleSheet(PAGE_STYLE)
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(16)

        title = QLabel("导入账目文件")
        title.setObjectName("title")
        root.addWidget(title)

        hint = QLabel("支持格式：.xlsx（工作表名须为「明细分类账」）、.csv。导入后会初始化 remaining_amount 并执行自动匹配。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.drop_label = QLabel("将账目文件拖拽到此处\n\n或点击下方按钮选择文件")
        self.drop_label.setObjectName("drop_zone")
        self.drop_label.setMinimumHeight(200)
        root.addWidget(self.drop_label)

        self.select_btn = QPushButton("选择文件")
        self.select_btn.setFixedWidth(160)
        root.addWidget(self.select_btn, alignment=Qt.AlignLeft)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        root.addStretch()
        self.select_btn.clicked.connect(self._select_file)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        self._do_import(paths)

    def _select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择账目文件",
            "",
            "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;所有文件 (*)",
        )
        if file_path:
            self._do_import([Path(file_path)])

    def _do_import(self, paths: list[Path]) -> None:
        self.status_label.setObjectName("status")
        self.status_label.setText("导入中...")
        _refresh_style(self.status_label)

        result = import_paths(paths)
        if result.file_errors:
            self.status_label.setObjectName("error")
            self.status_label.setText("✗ 导入失败：\n" + "\n".join(error.message for error in result.file_errors))
            _refresh_style(self.status_label)
            return

        if not result.rows:
            self.status_label.setObjectName("error")
            self.status_label.setText("✗ 未读取到任何数据，请检查文件格式")
            _refresh_style(self.status_label)
            return

        self.repo.replace_entries(result.rows)
        match_count = run_matching_cycle(self.repo)
        entry_count = self.repo.count_entries(row_type="entry")

        self.status_label.setObjectName("status")
        self.status_label.setText(
            f"✓ 导入成功：共 {result.records_imported} 行，其中 entry {entry_count} 行；自动生成 {match_count} 条匹配记录"
        )
        _refresh_style(self.status_label)

        reply = QMessageBox.question(
            self,
            "导入完成",
            "导入与自动匹配已完成，是否立即查看结果？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes and hasattr(self.parent(), "navigate_to_results"):
            self.parent().navigate_to_results()


def _refresh_style(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)

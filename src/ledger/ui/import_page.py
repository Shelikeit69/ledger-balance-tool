from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ledger.services.importer import import_paths
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
QLabel#drop_zone:hover { border-color: #0078d4; color: #1a1a1a; background: #f0f6ff; }
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
QPushButton#secondary {
    background: #ffffff;
    color: #1a1a1a;
    border: 1px solid #d1d1d1;
    font-weight: normal;
}
QPushButton#secondary:hover { background: #f3f3f3; }
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

        hint = QLabel("支持格式：.xlsx（工作表名须为「明细分类账」）、.csv")
        hint.setObjectName("hint")
        root.addWidget(hint)

        # 拖拽区域
        self.drop_label = QLabel("将 Excel 文件拖拽到此处\n\n或点击下方按钮选择文件")
        self.drop_label.setObjectName("drop_zone")
        self.drop_label.setMinimumHeight(200)
        root.addWidget(self.drop_label)

        # 按钮行
        self.select_btn = QPushButton("选择文件")
        self.select_btn.setFixedWidth(160)
        root.addWidget(self.select_btn, alignment=Qt.AlignLeft)

        # 状态
        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        root.addStretch()

        self.select_btn.clicked.connect(self._select_file)

    # ── 拖拽支持 ───────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_label.setStyleSheet(
                "border: 2px dashed #cba6f7; border-radius: 12px;"
                "color: #cdd6f4; font-size: 14px; padding: 60px 40px;"
            )

    def dragLeaveEvent(self, event) -> None:
        self.drop_label.setStyleSheet("")

    def dropEvent(self, event) -> None:
        self.drop_label.setStyleSheet("")
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        self._do_import(paths)

    # ── 文件选择 ───────────────────────────────────────

    def _select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择账目文件",
            "",
            "Excel 文件 (*.xlsx);;CSV 文件 (*.csv);;所有文件 (*)",
        )
        if file_path:
            self._do_import([Path(file_path)])

    # ── 导入逻辑 ───────────────────────────────────────

    def _do_import(self, paths: list[Path]) -> None:
        self.status_label.setObjectName("status")
        self.status_label.setText("导入中...")

        result = import_paths(paths)

        if result.file_errors:
            msgs = [e.message for e in result.file_errors]
            self.status_label.setObjectName("error")
            self.status_label.setText("✗ 导入失败：\n" + "\n".join(msgs))
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            return

        if not result.rows:
            self.status_label.setObjectName("error")
            self.status_label.setText("✗ 未读取到任何数据，请检查文件格式")
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            return

        # 清空旧数据，写入新数据
        self.repo.clear_rows()
        self.repo.save_rows(result.rows)

        self.status_label.setObjectName("status")
        self.status_label.setText(
            f"✓ 导入成功：共 {result.records_imported} 条记录\n"
            f"文件：{', '.join(str(p.name) for p in paths)}"
        )
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

        # 提示跳转结果页
        reply = QMessageBox.question(
            self,
            "导入完成",
            f"成功导入 {result.records_imported} 条记录，是否立即查看配平结果？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if hasattr(self.parent(), "navigate_to_results"):
                self.parent().navigate_to_results()

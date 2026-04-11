from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from ledger.config import AppConfig
from ledger.storage.repository import LedgerRepository
from ledger.ui.import_page import ImportPage
from ledger.ui.results_page import ResultsPage
from ledger.ui.settings_page import SettingsPage

NAV_ITEMS = [
    ("导入", 0),
    ("结果", 1),
    ("设置", 2),
]

NAV_STYLE = """
QListWidget {
    background: #f3f3f3;
    border: none;
    border-right: 1px solid #d1d1d1;
    color: #1a1a1a;
    font-size: 14px;
    padding-top: 4px;
}
QListWidget::item {
    padding: 12px 16px;
}
QListWidget::item:selected {
    background: #e5f1fb;
    color: #003b73;
    border-left: 3px solid #0078d4;
}
QListWidget::item:hover:!selected {
    background: #e9e9e9;
}
"""

WINDOW_STYLE = """
QMainWindow, QWidget#central {
    background: #ffffff;
    color: #1a1a1a;
}
"""


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.repo = LedgerRepository(config.data_dir / "ledger.db")

        self.setWindowTitle("账目配平工具")
        self.resize(1100, 700)
        self.setStyleSheet(WINDOW_STYLE)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧导航
        self.nav = QListWidget()
        self.nav.setStyleSheet(NAV_STYLE)
        self.nav.setFixedWidth(160)
        self.nav.setFocusPolicy(Qt.NoFocus)
        for label, _ in NAV_ITEMS:
            self.nav.addItem(QListWidgetItem(label))

        # 右侧页面栈
        self.stack = QStackedWidget()

        self.import_page = ImportPage(self.repo, self)
        self.results_page = ResultsPage(self.repo, self)
        self.settings_page = SettingsPage(self.repo, self)

        self.stack.addWidget(self.import_page)
        self.stack.addWidget(self.results_page)
        self.stack.addWidget(self.settings_page)

        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)

        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.nav.setCurrentRow(0)

    def _on_nav_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.results_page.refresh_results()

    def navigate_to_results(self) -> None:
        self.nav.setCurrentRow(1)


def main() -> None:
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    data_dir = Path.home() / ".ledger-balance-tool"
    data_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig(data_dir=data_dir)
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())

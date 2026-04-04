from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ledger.config import AI_API_BASE, AI_DEFAULT_MODEL
from ledger.storage.repository import LedgerRepository

PAGE_STYLE = """
QWidget { background: #ffffff; color: #1a1a1a; }
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
QLabel#title {
    font-size: 18px;
    font-weight: bold;
    color: #0078d4;
    padding: 8px 0;
}
QLabel#hint { color: #605e5c; font-size: 12px; }
QLabel#status_ok { color: #107c10; }
QLabel#status_err { color: #d83b01; }
"""


class SettingsPage(QWidget):
    def __init__(self, repo: LedgerRepository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setStyleSheet(PAGE_STYLE)
        self._build_ui()
        self._load_saved()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(20)

        title = QLabel("设置")
        title.setObjectName("title")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AlignRight
        )

        # API Key
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("输入 MiniMax API Key")
        self.api_key_input.setMinimumWidth(380)
        form.addRow("API Key：", self.api_key_input)

        # 模型
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText(AI_DEFAULT_MODEL)
        form.addRow("模型：", self.model_input)

        root.addLayout(form)

        hint = QLabel(f"接口地址：{AI_API_BASE}/text/chatcompletion_v2")
        hint.setObjectName("hint")
        root.addWidget(hint)

        # 按钮行
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("primary")
        self.test_btn = QPushButton("测试连接")
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 状态
        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        root.addStretch()

        self.save_btn.clicked.connect(self._save)
        self.test_btn.clicked.connect(self._test_connection)

    def _load_saved(self) -> None:
        key = self.repo.load_setting("minimax_api_key")
        model = self.repo.load_setting("minimax_model")
        if key:
            self.api_key_input.setText(key)
        if model:
            self.model_input.setText(model)

    def _save(self) -> None:
        key = self.api_key_input.text().strip()
        model = self.model_input.text().strip() or AI_DEFAULT_MODEL
        self.repo.save_setting("minimax_api_key", key)
        self.repo.save_setting("minimax_model", model)
        self.status_label.setObjectName("status_ok")
        self.status_label.setText("✓ 已保存")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _test_connection(self) -> None:
        import httpx
        key = self.api_key_input.text().strip()
        model = self.model_input.text().strip() or AI_DEFAULT_MODEL
        if not key:
            self.status_label.setObjectName("status_err")
            self.status_label.setText("✗ 请先输入 API Key")
            return
        self.status_label.setText("连接中...")
        try:
            from ledger.services.ai_suggester import _call_minimax
            _call_minimax("请回复 OK", key, model)
            self.status_label.setObjectName("status_ok")
            self.status_label.setText("✓ 连接成功")
        except Exception as e:
            self.status_label.setObjectName("status_err")
            self.status_label.setText(f"✗ 连接失败：{e}")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def get_api_key(self) -> str:
        return self.repo.load_setting("minimax_api_key")

    def get_model(self) -> str:
        return self.repo.load_setting("minimax_model") or AI_DEFAULT_MODEL

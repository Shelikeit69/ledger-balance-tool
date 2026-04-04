from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class AppConfig:
    data_dir: Path

TARGET_SHEET_NAME = "明细分类账"
REQUIRED_LEDGER_COLUMNS = (
    "科目代码",
    "科目名称",
    "日期",
    "业务日期",
    "凭证字号",
    "摘要",
    "借方金额",
    "贷方金额",
    "方向",
    "余额",
)
AI_DEFAULT_MODEL = "MiniMax-Text-01"
AI_API_BASE = "https://api.minimax.chat/v1"

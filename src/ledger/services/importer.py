from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

from ledger.config import REQUIRED_LEDGER_COLUMNS, TARGET_SHEET_NAME


# ── 标准化数据结构 ─────────────────────────────────────

@dataclass(frozen=True)
class NormalizedLedgerRow:
    subject_code: str
    subject_name: str
    posted_date: date | None
    business_date: date | None
    voucher_no: str
    summary: str
    debit_amount: Decimal
    credit_amount: Decimal
    direction: str
    balance: Decimal


# ── 导入结果 ───────────────────────────────────────────

@dataclass(frozen=True)
class FileImportError:
    file_path: Path
    code: str
    message: str


@dataclass
class ImportResult:
    rows: list[NormalizedLedgerRow]
    file_errors: list[FileImportError]

    def __init__(self) -> None:
        self.rows = []
        self.file_errors = []

    @property
    def records_imported(self) -> int:
        return len(self.rows)


# ── 公开接口 ───────────────────────────────────────────

def import_paths(paths: list[Path]) -> ImportResult:
    result = ImportResult()
    for path in [Path(p) for p in paths]:
        if path.is_dir():
            for child in sorted(path.iterdir()):
                _import_supported_path(child, result)
        else:
            _import_supported_path(path, result)
    return result


# ── 内部实现 ───────────────────────────────────────────

def _import_supported_path(file_path: Path, result: ImportResult) -> None:
    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        _import_xlsx(file_path, result)
    elif suffix == ".csv":
        _import_csv(file_path, result)


def _import_xlsx(file_path: Path, result: ImportResult) -> None:
    workbook = load_workbook(file_path, read_only=True, data_only=True)
    try:
        if TARGET_SHEET_NAME not in workbook.sheetnames:
            result.file_errors.append(FileImportError(
                file_path=file_path,
                code="missing_sheet",
                message=f"找不到工作表「{TARGET_SHEET_NAME}」",
            ))
            return

        sheet = workbook[TARGET_SHEET_NAME]
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return

        headers = [str(v).strip() if v is not None else "" for v in rows[0]]
        missing = [c for c in REQUIRED_LEDGER_COLUMNS if c not in headers]
        if missing:
            result.file_errors.append(FileImportError(
                file_path=file_path,
                code="missing_columns",
                message=f"缺少列：{', '.join(missing)}",
            ))
            return

        for values in rows[1:]:
            raw = dict(zip(headers, values, strict=False))
            if not _is_summary_row(raw):
                result.rows.append(_normalize(raw))
    finally:
        workbook.close()


def _import_csv(file_path: Path, result: ImportResult) -> None:
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        missing = [c for c in REQUIRED_LEDGER_COLUMNS if c not in headers]
        if missing:
            result.file_errors.append(FileImportError(
                file_path=file_path,
                code="missing_columns",
                message=f"缺少列：{', '.join(missing)}",
            ))
            return
        for raw in reader:
            row_dict = dict(raw)
            if not _is_summary_row(row_dict):
                result.rows.append(_normalize(row_dict))


# ── 汇总行过滤 ─────────────────────────────────────────

_SUMMARY_ROW_KEYWORDS = frozenset({
    "本期合计",
    "期初余额",
    "本期发生额",
    "本年累计",
    "期末余额",
    "合计",
})


def _is_summary_row(raw: dict[str, object]) -> bool:
    summary = str(raw.get("摘要", "")).replace(" ", "").replace("\u3000", "")
    return summary in _SUMMARY_ROW_KEYWORDS


# ── 标准化单行 ─────────────────────────────────────────

def _normalize(raw: dict[str, object]) -> NormalizedLedgerRow:
    voucher_no = str(raw.get("凭证字号", "")).replace(" ", "")
    return NormalizedLedgerRow(
        subject_code=str(raw.get("科目代码", "")).strip(),
        subject_name=str(raw.get("科目名称", "")).strip(),
        posted_date=_parse_date(raw.get("日期")),
        business_date=_parse_date(raw.get("业务日期")),
        voucher_no=voucher_no,
        summary=str(raw.get("摘要", "")).strip(),
        debit_amount=_parse_decimal(raw.get("借方金额")),
        credit_amount=_parse_decimal(raw.get("贷方金额")),
        direction=str(raw.get("方向", "")).strip(),
        balance=_parse_decimal(raw.get("余额")),
    )


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Excel 序列号
    try:
        serial = int(float(text))
        return date(1899, 12, 30) + __import__("datetime").timedelta(days=serial)
    except (ValueError, OverflowError):
        return None


def _parse_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, (int, float)):
        return Decimal(str(round(value, 2)))
    text = str(value).strip().replace(",", "")
    if not text:
        return Decimal("0.00")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0.00")

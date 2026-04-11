from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ledger.services.importer import import_paths


FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_ledger.csv"


def test_importer_marks_summary_rows_and_initializes_entry_amounts():
    result = import_paths([FIXTURE_CSV])

    assert not result.file_errors
    assert result.records_imported > 0

    rows = result.rows
    entry_rows = [row for row in rows if row.row_type == "entry"]
    assert entry_rows, "fixture 应至少导入 1 条 entry"

    first = entry_rows[0]
    assert first.amount_side == "credit"
    assert first.original_amount == Decimal("50000.00")
    assert first.remaining_amount == Decimal("50000.00")


def test_importer_infers_row_type_and_inherits_subject_fields(tmp_path: Path):
    csv_path = tmp_path / "inherit.csv"
    csv_path.write_text(
        "\n".join(
            [
                "科目代码,科目名称,日期,业务日期,凭证字号,摘要,借方金额,贷方金额,方向,余额",
                "1122,应收账款,2024-01-01,2024-01-01,记-0001,年初余额,0,0,借,100",
                ",,2024-01-02,2024-01-02,记-0002,测试业务,100,0,借,200",
                ",,2024-01-03,2024-01-03,记-0003,本期合计,100,0,借,300",
                ",,2024-01-04,2024-01-04,记-0004,本年累计,100,0,借,400",
            ]
        ),
        encoding="utf-8-sig",
    )

    result = import_paths([csv_path])

    assert not result.file_errors
    assert [row.row_type for row in result.rows] == ["opening", "entry", "period_total", "year_total"]
    assert result.rows[1].subject_code == "1122"
    assert result.rows[1].subject_name == "应收账款"
    assert result.rows[1].amount_side == "debit"
    assert result.rows[1].remaining_amount == Decimal("100.00")
    assert result.rows[0].remaining_amount == Decimal("0.00")

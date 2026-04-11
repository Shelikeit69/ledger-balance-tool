from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from ledger.services.importer import ImportedLedgerRow
from ledger.storage.repository import EntryMatchInput, LedgerRepository


def _sample_entry(
    *,
    row_index: int,
    amount_side: str,
    original_amount: str,
    summary: str = "测试摘要",
    row_type: str = "entry",
) -> ImportedLedgerRow:
    debit = Decimal(original_amount) if amount_side == "debit" else Decimal("0.00")
    credit = Decimal(original_amount) if amount_side == "credit" else Decimal("0.00")
    return ImportedLedgerRow(
        row_index=row_index,
        subject_code="1122",
        subject_name="应收账款",
        posted_date=date(2024, 1, row_index),
        business_date=date(2024, 1, row_index),
        voucher_no=f"记-{row_index:04d}",
        summary=summary,
        debit_amount=debit,
        credit_amount=credit,
        direction="借" if amount_side == "debit" else "贷",
        balance=Decimal("0.00"),
        row_type=row_type,
        amount_side=amount_side,
        original_amount=Decimal(original_amount),
        remaining_amount=Decimal(original_amount) if row_type == "entry" else Decimal("0.00"),
    )


def test_repository_persists_imported_entries_and_non_entry_rows(tmp_path: Path):
    repo = LedgerRepository(tmp_path / "ledger.db")

    repo.replace_entries(
        [
            _sample_entry(row_index=1, amount_side="debit", original_amount="100.00"),
            _sample_entry(
                row_index=2,
                amount_side="debit",
                original_amount="0.00",
                summary="本期合计",
                row_type="period_total",
            ),
        ]
    )

    entries = repo.list_entries()
    assert len(entries) == 2
    assert entries[0].remaining_amount == Decimal("100.00")
    assert entries[1].row_type == "period_total"
    assert entries[1].remaining_amount == Decimal("0.00")


def test_repository_creates_match_records_and_updates_remaining_amount(tmp_path: Path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.replace_entries(
        [
            _sample_entry(row_index=1, amount_side="debit", original_amount="1000.00", summary="A"),
            _sample_entry(row_index=2, amount_side="credit", original_amount="600.00", summary="B"),
        ]
    )
    entries = repo.list_entries(row_type="entry")

    match_id = repo.create_match_record(
        match_type="auto_partial",
        match_mode="1:1",
        matched_amount=Decimal("600.00"),
        reason="partial match",
        created_by="engine",
        links=[
            EntryMatchInput(entry_id=entries[0].id, role="debit", used_amount=Decimal("600.00")),
            EntryMatchInput(entry_id=entries[1].id, role="credit", used_amount=Decimal("600.00")),
        ],
    )

    updated = repo.list_entries(row_type="entry")
    assert match_id > 0
    assert updated[0].remaining_amount == Decimal("400.00")
    assert updated[1].remaining_amount == Decimal("0.00")

    matches = repo.list_match_records()
    assert len(matches) == 1
    assert matches[0].matched_amount == Decimal("600.00")
    assert len(matches[0].links) == 2


def test_repository_can_cancel_match_and_recalculate_remaining_amount(tmp_path: Path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.replace_entries(
        [
            _sample_entry(row_index=1, amount_side="debit", original_amount="1000.00", summary="A"),
            _sample_entry(row_index=2, amount_side="credit", original_amount="600.00", summary="B"),
        ]
    )
    entries = repo.list_entries(row_type="entry")

    match_id = repo.create_match_record(
        match_type="manual",
        match_mode="1:1",
        matched_amount=Decimal("600.00"),
        reason="manual match",
        created_by="user",
        links=[
            EntryMatchInput(entry_id=entries[0].id, role="debit", used_amount=Decimal("600.00")),
            EntryMatchInput(entry_id=entries[1].id, role="credit", used_amount=Decimal("600.00")),
        ],
    )

    repo.delete_match_record(match_id)

    restored = repo.list_entries(row_type="entry")
    assert restored[0].remaining_amount == Decimal("1000.00")
    assert restored[1].remaining_amount == Decimal("600.00")
    assert repo.list_match_records() == []

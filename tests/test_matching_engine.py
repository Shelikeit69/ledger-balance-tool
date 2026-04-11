from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from ledger.services.importer import ImportedLedgerRow
from ledger.services.matching_engine import run_matching_cycle
from ledger.storage.repository import LedgerRepository


def _entry(
    *,
    row_index: int,
    amount_side: str,
    amount: str,
    summary: str,
) -> ImportedLedgerRow:
    debit = Decimal(amount) if amount_side == "debit" else Decimal("0.00")
    credit = Decimal(amount) if amount_side == "credit" else Decimal("0.00")
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
        row_type="entry",
        amount_side=amount_side,
        original_amount=Decimal(amount),
        remaining_amount=Decimal(amount),
    )


def test_run_matching_cycle_handles_full_match(tmp_path: Path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.replace_entries(
        [
            _entry(row_index=1, amount_side="debit", amount="1000.00", summary="A"),
            _entry(row_index=2, amount_side="credit", amount="1000.00", summary="B"),
        ]
    )

    created = run_matching_cycle(repo)

    entries = repo.list_entries(row_type="entry")
    assert created == 1
    assert [entry.remaining_amount for entry in entries] == [Decimal("0.00"), Decimal("0.00")]


def test_run_matching_cycle_handles_partial_match(tmp_path: Path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.replace_entries(
        [
            _entry(row_index=1, amount_side="debit", amount="1000.00", summary="A"),
            _entry(row_index=2, amount_side="credit", amount="600.00", summary="B"),
        ]
    )

    created = run_matching_cycle(repo)

    entries = repo.list_entries(row_type="entry")
    assert created == 1
    assert [entry.remaining_amount for entry in entries] == [Decimal("400.00"), Decimal("0.00")]


def test_run_matching_cycle_handles_combination_match_up_to_three_rows(tmp_path: Path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.replace_entries(
        [
            _entry(row_index=1, amount_side="debit", amount="1000.00", summary="A"),
            _entry(row_index=2, amount_side="credit", amount="600.00", summary="B"),
            _entry(row_index=3, amount_side="credit", amount="400.00", summary="C"),
        ]
    )

    created = run_matching_cycle(repo)

    entries = repo.list_entries(row_type="entry")
    assert created >= 1
    assert [entry.remaining_amount for entry in entries] == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]


def test_run_matching_cycle_loops_until_no_more_matches(tmp_path: Path):
    repo = LedgerRepository(tmp_path / "ledger.db")
    repo.replace_entries(
        [
            _entry(row_index=1, amount_side="debit", amount="1000.00", summary="A"),
            _entry(row_index=2, amount_side="credit", amount="1000.00", summary="B"),
            _entry(row_index=3, amount_side="debit", amount="300.00", summary="C"),
            _entry(row_index=4, amount_side="credit", amount="300.00", summary="D"),
        ]
    )

    created = run_matching_cycle(repo)

    entries = repo.list_entries(row_type="entry")
    assert created == 2
    assert all(entry.remaining_amount == Decimal("0.00") for entry in entries)

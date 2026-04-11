from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from ledger.services.ai_suggester import analyze_candidate_pairs
from ledger.storage.repository import EntryRecord


def _entry(entry_id: int, summary: str, voucher_no: str, amount_side: str, amount: str) -> EntryRecord:
    debit = Decimal(amount) if amount_side == "debit" else Decimal("0.00")
    credit = Decimal(amount) if amount_side == "credit" else Decimal("0.00")
    return EntryRecord(
        id=entry_id,
        row_index=entry_id,
        subject_code="1122",
        subject_name="应收账款",
        posted_date=date(2024, 1, entry_id),
        business_date=date(2024, 1, entry_id),
        voucher_no=voucher_no,
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


def test_ai_analysis_only_returns_confirmable_candidates():
    debit_entry = _entry(1, "支付乙公司采购款", "记-0001", "debit", "800.00")
    credit_entry = _entry(2, "乙公司采购款项归还", "记-0002", "credit", "800.00")

    with patch(
        "ledger.services.ai_suggester._call_minimax",
        return_value=json.dumps([{"pair_index": 1, "recommended": True, "reason": "摘要高度相似"}]),
    ):
        suggestions = analyze_candidate_pairs(
            candidate_pairs=[([debit_entry], [credit_entry], Decimal("800.00"))],
            api_key="demo",
        )

    assert len(suggestions) == 1
    assert suggestions[0].recommended is True
    assert suggestions[0].matched_amount == Decimal("800.00")
    assert suggestions[0].match_mode == "1:1"
    assert suggestions[0].debit_entry_ids == [1]
    assert suggestions[0].credit_entry_ids == [2]

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ledger.storage.repository import EntryRecord


@dataclass(frozen=True)
class TraceLine:
    entry_id: int
    summary: str
    direction: str
    original_amount: Decimal
    matched_amount: Decimal
    remaining_amount: Decimal
    status: str


@dataclass(frozen=True)
class ProjectTrace:
    outstanding_amount: Decimal
    outstanding_direction: str
    lines: list[TraceLine]


def remaining_trace_lines(trace: ProjectTrace) -> list[TraceLine]:
    return [line for line in trace.lines if line.remaining_amount > 0]


def trace_status_summary(trace: ProjectTrace) -> str:
    counts = {"未匹配": 0, "部分匹配": 0, "已匹配": 0}
    for line in trace.lines:
        counts[line.status] = counts.get(line.status, 0) + 1
    return " | ".join([f"未匹配 {counts['未匹配']}", f"部分匹配 {counts['部分匹配']}", f"已匹配 {counts['已匹配']}"])


def trace_project_balance(rows: list[EntryRecord], rules=None) -> ProjectTrace:
    outstanding_amount = sum((row.remaining_amount for row in rows), Decimal("0.00"))
    direction = "借"
    if rows:
        debit_total = sum((row.remaining_amount for row in rows if row.amount_side == "debit"), Decimal("0.00"))
        credit_total = sum((row.remaining_amount for row in rows if row.amount_side == "credit"), Decimal("0.00"))
        direction = "借" if debit_total >= credit_total else "贷"
    return ProjectTrace(
        outstanding_amount=outstanding_amount,
        outstanding_direction=direction,
        lines=[
            TraceLine(
                entry_id=row.id,
                summary=row.summary,
                direction="借" if row.amount_side == "debit" else "贷",
                original_amount=row.original_amount,
                matched_amount=row.matched_amount,
                remaining_amount=row.remaining_amount,
                status=row.status,
            )
            for row in rows
        ],
    )

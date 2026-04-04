from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ledger.services.attribution import (
    CorrectionRule,
    summaries_match,
    summaries_share_manual_rule,
    normalize_summary_text,
)
from ledger.services.importer import NormalizedLedgerRow

STATUS_LABELS = {
    "uncleared": "未清",
    "partially_cleared": "部分冲平",
    "cleared": "已清",
}


@dataclass(frozen=True)
class TraceLine:
    voucher_no: str
    summary: str
    posted_date: date | None
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


def localized_status(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def trace_status_summary(trace: ProjectTrace) -> str:
    counts = {s: 0 for s in STATUS_LABELS}
    for line in trace.lines:
        counts[line.status] = counts.get(line.status, 0) + 1
    return " | ".join([
        f"未清 {counts['uncleared']}",
        f"部分冲平 {counts['partially_cleared']}",
        f"已清 {counts['cleared']}",
    ])


@dataclass
class _WorkingLine:
    row: NormalizedLedgerRow
    direction: str
    original_amount: Decimal
    matched_amount: Decimal
    remaining_amount: Decimal


def trace_project_balance(
    rows: list[NormalizedLedgerRow],
    rules: list[CorrectionRule] | None = None,
) -> ProjectTrace:
    active_rules = rules or []
    normalized_rows = sorted(
        rows,
        key=lambda r: (
            r.posted_date or date.min,
            r.business_date or date.min,
            r.voucher_no,
            r.summary,
        ),
    )

    working_lines: list[_WorkingLine] = []
    open_debits: list[_WorkingLine] = []
    open_credits: list[_WorkingLine] = []

    for row in normalized_rows:
        direction, amount = _direction_and_amount(row)
        current = _WorkingLine(
            row=row,
            direction=direction,
            original_amount=amount,
            matched_amount=Decimal("0.00"),
            remaining_amount=amount,
        )
        opposite = open_credits if direction == "debit" else open_debits
        _match_against_open(current, opposite, active_rules)

        if current.remaining_amount > 0:
            (open_debits if direction == "debit" else open_credits).append(current)
        working_lines.append(current)

    net = sum((r.credit_amount - r.debit_amount) for r in normalized_rows)
    outstanding_direction = "贷" if net >= 0 else "借"
    outstanding_pool = open_credits if net >= 0 else open_debits
    outstanding_amount = sum(
        (line.remaining_amount for line in outstanding_pool), Decimal("0.00")
    )

    return ProjectTrace(
        outstanding_amount=outstanding_amount,
        outstanding_direction=outstanding_direction,
        lines=[
            TraceLine(
                voucher_no=line.row.voucher_no,
                summary=line.row.summary,
                posted_date=line.row.posted_date,
                direction="贷" if line.direction == "credit" else "借",
                original_amount=line.original_amount,
                matched_amount=line.matched_amount,
                remaining_amount=line.remaining_amount,
                status=_status_for(line),
            )
            for line in working_lines
        ],
    )


def _direction_and_amount(row: NormalizedLedgerRow) -> tuple[str, Decimal]:
    if row.credit_amount > 0:
        return "credit", row.credit_amount
    return "debit", row.debit_amount


def _match_against_open(
    current: _WorkingLine,
    opposite_open: list[_WorkingLine],
    rules: list[CorrectionRule],
) -> None:
    candidates = [
        line for line in opposite_open
        if line.remaining_amount > 0
        and _summaries_can_reconcile(current.row.summary, line.row.summary, rules)
    ]
    candidates.sort(key=lambda line: _match_priority(current, line, rules))

    for open_line in candidates:
        if current.remaining_amount <= 0:
            break
        matched = min(current.remaining_amount, open_line.remaining_amount)
        current.matched_amount += matched
        current.remaining_amount -= matched
        open_line.matched_amount += matched
        open_line.remaining_amount -= matched


def _summaries_can_reconcile(left: str, right: str, rules: list[CorrectionRule]) -> bool:
    if summaries_share_manual_rule(left, right, rules):
        return True
    return summaries_match(left, right)


def _match_priority(
    current: _WorkingLine,
    candidate: _WorkingLine,
    rules: list[CorrectionRule],
) -> tuple[int, int, int, date, str]:
    return (
        0 if candidate.remaining_amount == current.remaining_amount else 1,
        0 if summaries_share_manual_rule(current.row.summary, candidate.row.summary, rules) else 1,
        0 if normalize_summary_text(current.row.summary) == normalize_summary_text(candidate.row.summary) else 1,
        candidate.row.posted_date or date.min,
        candidate.row.voucher_no,
    )


def _status_for(line: _WorkingLine) -> str:
    if line.remaining_amount == line.original_amount:
        return "uncleared"
    if line.remaining_amount == 0:
        return "cleared"
    return "partially_cleared"

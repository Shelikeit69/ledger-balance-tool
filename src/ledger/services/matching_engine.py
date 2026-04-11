from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from ledger.storage.repository import EntryMatchInput, EntryRecord, LedgerRepository


@dataclass(frozen=True)
class CandidatePair:
    debit_entries: list[EntryRecord]
    credit_entries: list[EntryRecord]
    matched_amount: Decimal
    match_mode: str
    reason: str


def run_matching_cycle(repo: LedgerRepository) -> int:
    created_count = 0
    while True:
        created = (
            full_match(repo)
            or partial_match(repo)
            or combination_match(repo)
        )
        if not created:
            return created_count
        created_count += created


def full_match(repo: LedgerRepository) -> int:
    debit_entries, credit_entries = _open_entries(repo)
    for debit_entry in debit_entries:
        for credit_entry in credit_entries:
            if debit_entry.remaining_amount == credit_entry.remaining_amount:
                _create_match(
                    repo,
                    debit_entries=[debit_entry],
                    credit_entries=[credit_entry],
                    matched_amount=debit_entry.remaining_amount,
                    match_type="auto_full",
                    match_mode="1:1",
                    reason="金额完全相等，自动全额匹配",
                    created_by="engine",
                )
                return 1
    return 0


def partial_match(repo: LedgerRepository) -> int:
    debit_entries, credit_entries = _open_entries(repo)
    for debit_entry in debit_entries:
        for credit_entry in credit_entries:
            matched_amount = min(debit_entry.remaining_amount, credit_entry.remaining_amount)
            if matched_amount <= Decimal("0.00"):
                continue
            if debit_entry.remaining_amount == credit_entry.remaining_amount:
                continue
            _create_match(
                repo,
                debit_entries=[debit_entry],
                credit_entries=[credit_entry],
                matched_amount=matched_amount,
                match_type="auto_partial",
                match_mode="1:1",
                reason="金额不等，自动部分匹配",
                created_by="engine",
            )
            return 1
    return 0


def combination_match(repo: LedgerRepository) -> int:
    debit_entries, credit_entries = _open_entries(repo)

    for debit_entry in debit_entries:
        matched_group = _find_combination_by_sum(credit_entries, debit_entry.remaining_amount, max_size=3)
        if matched_group:
            _create_match(
                repo,
                debit_entries=[debit_entry],
                credit_entries=matched_group,
                matched_amount=debit_entry.remaining_amount,
                match_type="auto_full",
                match_mode=f"1:{len(matched_group)}",
                reason="组合金额相等，自动组合匹配",
                created_by="engine",
            )
            return 1

    for credit_entry in credit_entries:
        matched_group = _find_combination_by_sum(debit_entries, credit_entry.remaining_amount, max_size=3)
        if matched_group:
            _create_match(
                repo,
                debit_entries=matched_group,
                credit_entries=[credit_entry],
                matched_amount=credit_entry.remaining_amount,
                match_type="auto_full",
                match_mode=f"{len(matched_group)}:1",
                reason="组合金额相等，自动组合匹配",
                created_by="engine",
            )
            return 1

    return 0


def generate_ai_candidates(repo: LedgerRepository) -> list[CandidatePair]:
    debit_entries, credit_entries = _open_entries(repo)
    candidates: list[CandidatePair] = []

    for debit_entry in debit_entries:
        for credit_entry in credit_entries:
            if debit_entry.remaining_amount == credit_entry.remaining_amount:
                candidates.append(
                    CandidatePair(
                        debit_entries=[debit_entry],
                        credit_entries=[credit_entry],
                        matched_amount=debit_entry.remaining_amount,
                        match_mode="1:1",
                        reason="金额完全相等，等待摘要语义确认",
                    )
                )

    for debit_entry in debit_entries:
        matched_group = _find_combination_by_sum(credit_entries, debit_entry.remaining_amount, max_size=3)
        if matched_group:
            candidates.append(
                CandidatePair(
                    debit_entries=[debit_entry],
                    credit_entries=matched_group,
                    matched_amount=debit_entry.remaining_amount,
                    match_mode=f"1:{len(matched_group)}",
                    reason="组合金额相等，等待摘要语义确认",
                )
            )

    for credit_entry in credit_entries:
        matched_group = _find_combination_by_sum(debit_entries, credit_entry.remaining_amount, max_size=3)
        if matched_group:
            candidates.append(
                CandidatePair(
                    debit_entries=matched_group,
                    credit_entries=[credit_entry],
                    matched_amount=credit_entry.remaining_amount,
                    match_mode=f"{len(matched_group)}:1",
                    reason="组合金额相等，等待摘要语义确认",
                )
            )

    return _dedupe_candidates(candidates)


def confirm_match(
    repo: LedgerRepository,
    *,
    debit_entries: list[EntryRecord],
    credit_entries: list[EntryRecord],
    matched_amount: Decimal,
    match_mode: str,
    reason: str,
    created_by: str,
    match_type: str = "manual",
) -> int:
    return _create_match(
        repo,
        debit_entries=debit_entries,
        credit_entries=credit_entries,
        matched_amount=matched_amount,
        match_type=match_type,
        match_mode=match_mode,
        reason=reason,
        created_by=created_by,
    )


def cancel_match(repo: LedgerRepository, match_record_id: int) -> None:
    repo.delete_match_record(match_record_id)


def _open_entries(repo: LedgerRepository) -> tuple[list[EntryRecord], list[EntryRecord]]:
    entries = repo.list_entries(row_type="entry", only_unmatched=True)
    debit_entries = [entry for entry in entries if entry.amount_side == "debit" and entry.remaining_amount > 0]
    credit_entries = [entry for entry in entries if entry.amount_side == "credit" and entry.remaining_amount > 0]
    return debit_entries, credit_entries


def _find_combination_by_sum(
    entries: list[EntryRecord],
    target_amount: Decimal,
    *,
    max_size: int,
) -> list[EntryRecord] | None:
    candidates = [entry for entry in entries if entry.remaining_amount > 0 and entry.remaining_amount <= target_amount]
    for size in range(2, min(max_size, len(candidates)) + 1):
        for combo in combinations(candidates, size):
            total = sum((item.remaining_amount for item in combo), Decimal("0.00"))
            if total == target_amount:
                return list(combo)
    return None


def _create_match(
    repo: LedgerRepository,
    *,
    debit_entries: list[EntryRecord],
    credit_entries: list[EntryRecord],
    matched_amount: Decimal,
    match_type: str,
    match_mode: str,
    reason: str,
    created_by: str,
) -> int:
    return repo.create_match_record(
        match_type=match_type,
        match_mode=match_mode,
        matched_amount=matched_amount,
        reason=reason,
        created_by=created_by,
        links=_build_links(debit_entries, credit_entries, matched_amount),
    )


def _dedupe_candidates(candidates: list[CandidatePair]) -> list[CandidatePair]:
    seen: set[tuple[tuple[int, ...], tuple[int, ...], str]] = set()
    result: list[CandidatePair] = []
    for candidate in candidates:
        key = (
            tuple(sorted(entry.id for entry in candidate.debit_entries)),
            tuple(sorted(entry.id for entry in candidate.credit_entries)),
            candidate.match_mode,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _build_links(
    debit_entries: list[EntryRecord],
    credit_entries: list[EntryRecord],
    matched_amount: Decimal,
) -> list[EntryMatchInput]:
    links: list[EntryMatchInput] = []
    links.extend(_allocate_role_links(debit_entries, "debit", matched_amount))
    links.extend(_allocate_role_links(credit_entries, "credit", matched_amount))
    return links


def _allocate_role_links(
    entries: list[EntryRecord],
    role: str,
    matched_amount: Decimal,
) -> list[EntryMatchInput]:
    remaining = matched_amount
    links: list[EntryMatchInput] = []
    for entry in entries:
        if remaining <= Decimal("0.00"):
            break
        used_amount = min(entry.remaining_amount, remaining)
        if used_amount <= Decimal("0.00"):
            continue
        links.append(EntryMatchInput(entry_id=entry.id, role=role, used_amount=used_amount))
        remaining -= used_amount
    return links

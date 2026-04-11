from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

import httpx

from ledger.config import AI_API_BASE, AI_DEFAULT_MODEL
from ledger.storage.repository import EntryRecord


@dataclass(frozen=True)
class AiMatchSuggestion:
    pair_index: int
    recommended: bool
    reason: str
    matched_amount: Decimal
    match_mode: str
    debit_entry_ids: list[int]
    credit_entry_ids: list[int]


def analyze_candidate_pairs(
    candidate_pairs: list[tuple[list[EntryRecord], list[EntryRecord], Decimal]],
    api_key: str,
    model: str = AI_DEFAULT_MODEL,
) -> list[AiMatchSuggestion]:
    if not candidate_pairs or not api_key:
        return []

    prompt = _build_prompt(candidate_pairs)
    raw = _call_minimax(prompt, api_key, model or AI_DEFAULT_MODEL)
    return _parse_response(raw, candidate_pairs)


def _build_prompt(candidate_pairs: list[tuple[list[EntryRecord], list[EntryRecord], Decimal]]) -> str:
    lines: list[str] = []
    for index, (debit_entries, credit_entries, matched_amount) in enumerate(candidate_pairs, start=1):
        debit_text = " | ".join(_format_entry(entry) for entry in debit_entries)
        credit_text = " | ".join(_format_entry(entry) for entry in credit_entries)
        lines.append(
            f"候选{index}：\n"
            f"  借方：{debit_text}\n"
            f"  贷方：{credit_text}\n"
            f"  金额：{matched_amount:,.2f}\n"
        )
    return (
        "你是账目配平辅助助手。以下候选配对已经满足金额条件，"
        "你只需要根据摘要、凭证号、日期判断是否像同一笔业务。\n"
        "必须只返回 JSON 数组，不得输出 markdown 或解释文字。\n"
        '格式：[{"pair_index": 1, "recommended": true, "reason": "简短理由"}]\n'
        "若不建议匹配，recommended 返回 false。\n"
        "候选列表：\n"
        + "\n".join(lines)
    )


def _format_entry(entry: EntryRecord) -> str:
    date_text = entry.posted_date.isoformat() if entry.posted_date else ""
    return f"#{entry.id} {entry.summary} / {entry.voucher_no} / {date_text}"


def _parse_response(
    raw: str,
    candidate_pairs: list[tuple[list[EntryRecord], list[EntryRecord], Decimal]],
) -> list[AiMatchSuggestion]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.strip().startswith("```"))
    try:
        items = json.loads(text)
    except Exception:
        return []

    suggestions: list[AiMatchSuggestion] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pair_index = int(item.get("pair_index", 0))
        if pair_index < 1 or pair_index > len(candidate_pairs):
            continue
        debit_entries, credit_entries, matched_amount = candidate_pairs[pair_index - 1]
        recommended = bool(item.get("recommended"))
        suggestions.append(
            AiMatchSuggestion(
                pair_index=pair_index,
                recommended=recommended,
                reason=str(item.get("reason", "")).strip(),
                matched_amount=matched_amount,
                match_mode=f"{len(debit_entries)}:{len(credit_entries)}",
                debit_entry_ids=[entry.id for entry in debit_entries],
                credit_entry_ids=[entry.id for entry in credit_entries],
            )
        )
    return suggestions


def _call_minimax(prompt: str, api_key: str, model: str) -> str:
    url = f"{AI_API_BASE}/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是账目配平辅助助手。你的回复必须且只能是一个合法 JSON 数组，"
                    "格式为 [{\"pair_index\": 1, \"recommended\": true, \"reason\": \"原因\"}]。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    with httpx.Client(timeout=120) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        return "[]"
    message = choices[0].get("message") or {}
    content = str(message.get("content", "")).strip()
    if not content:
        return "[]"
    return content

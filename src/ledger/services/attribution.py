from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ledger.services.importer import NormalizedLedgerRow


@dataclass(frozen=True)
class CorrectionRule:
    match_text: str
    project_name: str


@dataclass(frozen=True)
class ProjectGroup:
    project_name: str
    rows: list[NormalizedLedgerRow]
    summary_key: str
    voucher_nos: list[str]


# ── 文本标准化工具 ─────────────────────────────────────

def normalize_summary_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    text = re.sub(r"[\s\-—－_/\\()（）【】\[\]「」『』。，、：:；;！!？?]+", "", text)
    return text


def normalize_voucher_no(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


_REVERSAL_TAGS = frozenset({"退单", "重转"})


def _strip_reversal_tag(text: str) -> str:
    """去掉退单/重转标记词，返回核心文字（已标准化）。"""
    raw = normalize_summary_text(text)
    for tag in _REVERSAL_TAGS:
        raw = raw.replace(normalize_summary_text(tag), "")
    return raw


def _char_overlap_ratio(a: str, b: str) -> float:
    """两个字符串公共字符集占较短串的比例。"""
    if not a or not b:
        return 0.0
    set_a, set_b = set(a), set(b)
    common = len(set_a & set_b)
    return common / min(len(set_a), len(set_b))


def summaries_match(left: str, right: str) -> bool:
    a = normalize_summary_text(left)
    b = normalize_summary_text(right)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 4 and shorter in longer:
        return True
    # 退单/重转互配：一方含退单、另一方含重转，且核心文字重叠超过 60%
    tags_a = {normalize_summary_text(t) for t in _REVERSAL_TAGS if normalize_summary_text(t) in a}
    tags_b = {normalize_summary_text(t) for t in _REVERSAL_TAGS if normalize_summary_text(t) in b}
    if tags_a and tags_b and tags_a != tags_b:
        core_a = _strip_reversal_tag(left)
        core_b = _strip_reversal_tag(right)
        if core_a and core_b and _char_overlap_ratio(core_a, core_b) > 0.6:
            return True
    return False


# ── 规则解析 ───────────────────────────────────────────

def resolve_rule_project_name(summary: str, rules: list[CorrectionRule]) -> str | None:
    normalized = normalize_summary_text(summary)
    if not normalized:
        return None
    for rule in rules:
        if normalize_summary_text(rule.match_text) and normalize_summary_text(rule.match_text) in normalized:
            return rule.project_name
        if normalize_summary_text(rule.project_name) and normalize_summary_text(rule.project_name) in normalized:
            return rule.project_name
    return None


def resolve_rule_project_key(summary: str, rules: list[CorrectionRule]) -> str | None:
    name = resolve_rule_project_name(summary, rules)
    return normalize_summary_text(name) if name else None


def summaries_share_manual_rule(left: str, right: str, rules: list[CorrectionRule]) -> bool:
    lk = resolve_rule_project_key(left, rules)
    rk = resolve_rule_project_key(right, rules)
    return bool(lk and rk and lk == rk)


# ── 归组主逻辑 ─────────────────────────────────────────

def attribute_projects(
    rows: list[NormalizedLedgerRow],
    rules: list[CorrectionRule],
) -> list[ProjectGroup]:
    grouped_rows: list[dict] = []

    for row in rows:
        canonical_name = resolve_rule_project_name(row.summary, rules)
        summary_key = normalize_summary_text(canonical_name or row.summary)

        for group in grouped_rows:
            if summary_key == group["summary_key"]:
                group["rows"].append(row)
                group["voucher_nos"].append(normalize_voucher_no(row.voucher_no))
                break
            if (
                canonical_name is None
                and not group["manual_rule"]
                and summaries_match(row.summary, group["rows"][0].summary)
            ):
                group["rows"].append(row)
                group["voucher_nos"].append(normalize_voucher_no(row.voucher_no))
                break
        else:
            grouped_rows.append({
                "project_name": canonical_name or summary_key,
                "summary_key": summary_key,
                "manual_rule": canonical_name is not None,
                "rows": [row],
                "voucher_nos": [normalize_voucher_no(row.voucher_no)],
            })

    return sorted(
        [
            ProjectGroup(
                project_name=str(g["project_name"]),
                rows=list(g["rows"]),
                summary_key=str(g["summary_key"]),
                voucher_nos=list(dict.fromkeys(g["voucher_nos"])),
            )
            for g in grouped_rows
        ],
        key=lambda item: item.project_name,
    )

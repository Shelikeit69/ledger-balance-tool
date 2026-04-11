from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectionRule:
    match_text: str
    project_name: str


def normalize_summary_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    text = re.sub(r"[\s\-—－_/\\()（）【】\[\]「」『』。，、：:；;！!？?]+", "", text)
    return text


def apply_text_rules(summary: str, rules: list[CorrectionRule]) -> str:
    normalized_summary = normalize_summary_text(summary)
    for rule in rules:
        normalized_match = normalize_summary_text(rule.match_text)
        if normalized_match and normalized_match in normalized_summary:
            return rule.project_name
    return summary

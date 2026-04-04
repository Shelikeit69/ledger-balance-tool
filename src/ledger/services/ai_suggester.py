from __future__ import annotations

import json
import httpx


from ledger.config import AI_API_BASE, AI_DEFAULT_MODEL
from ledger.services.attribution import CorrectionRule, ProjectGroup
from ledger.services.balance_trace import ProjectTrace


def suggest_rules(
    groups: list[ProjectGroup],
    api_key: str,
    model: str = AI_DEFAULT_MODEL,
    traces: list[ProjectTrace] | None = None,
) -> list[CorrectionRule]:
    if not groups or not api_key or not traces or len(groups) != len(traces):
        return []

    # 1. 构造候选配对（金额完全相同且方向相反）
    candidates = []  # [(idx, idx, groupA, groupB, traceA, traceB)]
    for i, (g1, t1) in enumerate(zip(groups, traces)):
        for j, (g2, t2) in enumerate(zip(groups, traces)):
            if i >= j:
                continue
            if t1.outstanding_amount == t2.outstanding_amount and t1.outstanding_amount > 0:
                dir1, dir2 = t1.outstanding_direction, t2.outstanding_direction
                if (dir1 == "借" and dir2 == "贷") or (dir1 == "贷" and dir2 == "借"):
                    candidates.append((i, j, g1, g2, t1, t2))

    if not candidates:
        return []

    BATCH_SIZE = 5
    all_rules = []
    for batch_start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[batch_start:batch_start + BATCH_SIZE]
        # 重新编号从1开始
        pair_texts = []
        for idx, (_, _, g1, g2, t1, t2) in enumerate(batch, 1):
            pair_texts.append(
                f"配对{idx}：\n  A: 「{g1.project_name}」（{t1.outstanding_direction}方 {t1.outstanding_amount:,.2f}）\n  B: 「{g2.project_name}」（{t2.outstanding_direction}方 {t2.outstanding_amount:,.2f}）"
            )
        prompt = (
            "你必须只返回 JSON 数组，不得输出任何其他文字。\n"
            "以下是账目系统自动筛选出的候选项目配对，每对金额完全相同且方向相反。\n"
            "请判断每对项目的摘要是否描述同一笔业务。\n"
            "请严格按以下 JSON 格式返回，不要添加任何解释或 markdown 标记：\n"
            '[{"index": 1, "match": true, "reason": "简短理由"}, ...]\n'
            "如果没有任何配对可归并，返回空数组：[]\n"
            "配对列表：\n" + "\n".join(pair_texts)
        )
        raw = _call_minimax(prompt, api_key, model)

        batch_rules = _parse_ai_response(raw, batch)
        all_rules.extend(batch_rules)
    return all_rules

def _parse_ai_response(raw: str, batch) -> list[CorrectionRule]:
    try:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(line for line in lines if not line.strip().startswith("```") )
        items = json.loads(text)
    except Exception:
        return []
    rules: list[CorrectionRule] = []
    for item in items:
        match_val = item.get("match")
        if not (isinstance(item, dict) and "index" in item and (match_val is True or str(match_val).lower() == "true")):
            continue
        idx = item["index"] - 1
        if 0 <= idx < len(batch):
            _, _, g1, g2, _, _ = batch[idx]
            if len(g1.project_name) >= len(g2.project_name):
                match_text, project_name = g1.project_name, g2.project_name
            else:
                match_text, project_name = g2.project_name, g1.project_name
            if match_text != project_name:
                rules.append(CorrectionRule(match_text=match_text, project_name=project_name))
    return rules


def _build_summary_list(groups: list[ProjectGroup], traces: list[ProjectTrace] | None) -> list[str]:
    # traces 按顺序与 groups 对应
    result: list[str] = []
    for idx, group in enumerate(groups):
        name = group.project_name
        if traces and idx < len(traces):
            trace = traces[idx]
            amount = trace.outstanding_amount
            direction = trace.outstanding_direction
            # 格式：项目名（方向 金额）
            s = f"{name}（{direction}方 {amount:,.2f}）"
        else:
            s = name
        result.append(s)
    return result


def _build_prompt(summaries: list[str]) -> str:
    items = "\n".join(f"{i+1}. {s}" for i, s in enumerate(summaries))
    return (
        "以下是账目系统中未配平的项目列表，每条包含项目名称、挂账方向和金额。\n"
        "请分析哪些项目描述的是同一笔业务，判断依据：\n"
        "- 摘要内容相似（如原始记录与重转/退单记录）\n"
        "- 金额相同或接近\n"
        "- 方向相反（一借一贷，说明可以互相冲平）\n"
        "对于你识别出的同类项，建议将「别名摘要」归入「主项目名称」。\n"
        "严格按以下 JSON 格式返回，不要添加任何解释或 markdown 标记：\n"
        '[{"match_text": "别名摘要原文", "project_name": "主项目名称原文"}, ...]\n'
        "如果没有发现可归并的项目，返回空数组：[]\n"
        f"项目列表：\n{items}"
    )


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
                "content": "你是会计账目分析助手。你的回复必须且只能是一个合法的 JSON 数组，格式为 [{\"index\": 1, \"match\": true, \"reason\": \"原因\"}]。禁止输出任何 JSON 以外的文字、标点或换行。",
            },
            {
                "role": "user",
                "content": prompt,
            },
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
        return ""
    msg = choices[0].get("message") or {}

    # 优先取 content，没有则从 reasoning_content 里提取最后的 JSON 部分
    content = msg.get("content", "").strip()
    if not content:
        reasoning = msg.get("reasoning_content", "")
        idx = reasoning.rfind("[")
        if idx != -1:
            content = reasoning[idx:]
    return content


def _parse_response(raw: str) -> list[CorrectionRule]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        )
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return []
    rules: list[CorrectionRule] = []
    for item in items:
        if isinstance(item, dict):
            match_text = str(item.get("match_text", "")).strip()
            project_name = str(item.get("project_name", "")).strip()
            if match_text and project_name and match_text != project_name:
                rules.append(CorrectionRule(
                    match_text=match_text,
                    project_name=project_name,
                ))
    return rules

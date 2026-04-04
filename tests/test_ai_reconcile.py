"""测试：AI 是否能在无人工干预的情况下完成账目配平。

测试数据来自 tests/fixtures/sample_ledger.csv，包含三类条目：

1. 可自动配平（摘要完全相同的借贷对）
2. 只能依赖 AI 配平（摘要不同、金额相同且方向相反的借贷对）
3. 无对应条目（孤立记录，任何情况下均应保持未清）

测试方法：
- 用 unittest.mock.patch 替换底层 _call_minimax，模拟 AI 返回"全部匹配"。
- 验证应用 AI 建议规则后，所有可配对的项目 outstanding_amount == 0。
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from ledger.services.attribution import attribute_projects
from ledger.services.balance_trace import trace_project_balance
from ledger.services.ai_suggester import suggest_rules
from ledger.services.importer import import_paths

# CSV 测试数据路径
FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_ledger.csv"

# 无对应条目的孤立记录金额（零星行政杂费 200 元，无配对）
UNPAIRED_OUTSTANDING = Decimal("200.00")


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _load_rows():
    """从 CSV fixture 加载所有账目行。"""
    result = import_paths([FIXTURE_CSV])
    assert not result.file_errors, f"CSV 导入出错：{result.file_errors}"
    assert result.records_imported > 0, "CSV 中没有可导入的记录"
    return result.rows


def _dynamic_ai_mock(prompt: str, api_key: str, model: str) -> str:
    """
    动态 AI mock：解析 prompt 中有几个「配对N：」，对所有配对返回 match=true。
    这样无论分组排序如何变化，测试都能正确响应。
    """
    count = len(re.findall(r"配对\d+：", prompt))
    response = [
        {"index": i + 1, "match": True, "reason": "同一笔业务，金额相同方向相反"}
        for i in range(count)
    ]
    return json.dumps(response)


def _run_pipeline_with_ai(rows):
    """
    完整运行：无规则归组 → 配平追踪 → AI 建议规则 → 带规则重新归组 → 再次追踪。
    返回 (ai_rules, groups_after, traces_after)。
    """
    # 第一步：无规则归组 + 追踪
    groups = attribute_projects(rows, rules=[])
    traces = [trace_project_balance(g.rows, rules=[]) for g in groups]

    # 第二步：mock AI，收集建议规则
    with patch("ledger.services.ai_suggester._call_minimax", side_effect=_dynamic_ai_mock):
        ai_rules = suggest_rules(groups, api_key="test-key", traces=traces)

    # 第三步：带 AI 规则重新归组 + 追踪
    groups_after = attribute_projects(rows, rules=ai_rules)
    traces_after = [trace_project_balance(g.rows, rules=ai_rules) for g in groups_after]

    return ai_rules, groups_after, traces_after


# ── 测试类 ────────────────────────────────────────────────────────────────────

class TestAutoReconcile:
    """自动配平：摘要完全相同的借贷对，无需 AI 即可清零。"""

    def test_same_summary_pair_clears_automatically(self):
        rows = _load_rows()
        # 只取「收到甲公司货款」两行（摘要相同）
        target_rows = [r for r in rows if "甲公司货款" in r.summary]
        assert len(target_rows) == 2, "fixture 中应有 2 行甲公司货款记录"

        groups = attribute_projects(target_rows, rules=[])
        # 相同摘要 → 应归为 1 组
        assert len(groups) == 1, "相同摘要应归入同一项目组"

        trace = trace_project_balance(groups[0].rows, rules=[])
        assert trace.outstanding_amount == Decimal("0.00"), (
            f"自动配平后 outstanding 应为 0，实际为 {trace.outstanding_amount}"
        )


class TestAiReconcile:
    """AI 配平：摘要不同但金额相同且方向相反的借贷对，依靠 AI 建议规则清零。"""

    def test_ai_produces_rules_for_unmatched_pairs(self):
        """AI 应为无法自动匹配的借贷对生成至少一条规则。"""
        rows = _load_rows()
        ai_rules, _, _ = _run_pipeline_with_ai(rows)
        assert len(ai_rules) > 0, "AI 应返回至少一条配平规则"

    def test_all_paired_entries_clear_after_ai(self):
        """应用 AI 规则后，所有有对应条目的项目 outstanding_amount 应为 0。"""
        rows = _load_rows()
        _, groups_after, traces_after = _run_pipeline_with_ai(rows)

        still_outstanding = [
            (g.project_name, t.outstanding_amount, t.outstanding_direction)
            for g, t in zip(groups_after, traces_after)
            if t.outstanding_amount > Decimal("0.00")
        ]

        # 只允许孤立记录（零星行政杂费 200 元）保持未清
        assert len(still_outstanding) == 1, (
            f"AI 配平后应只剩 1 条未清记录，实际剩余：{still_outstanding}"
        )
        assert still_outstanding[0][1] == UNPAIRED_OUTSTANDING, (
            f"未清金额应为 {UNPAIRED_OUTSTANDING}，实际为 {still_outstanding[0][1]}"
        )

    def test_total_outstanding_equals_unpaired_only(self):
        """AI 配平后，全部项目未清金额之和 == 孤立记录金额（200 元）。"""
        rows = _load_rows()
        _, _, traces_after = _run_pipeline_with_ai(rows)

        total = sum(t.outstanding_amount for t in traces_after)
        assert total == UNPAIRED_OUTSTANDING, (
            f"AI 配平后总未清应为 {UNPAIRED_OUTSTANDING}，实际为 {total}"
        )

    def test_without_ai_pairs_remain_uncleared(self):
        """不调用 AI（api_key 为空）时，不同摘要的借贷对应保持未清状态。"""
        rows = _load_rows()
        groups = attribute_projects(rows, rules=[])
        traces = [trace_project_balance(g.rows, rules=[]) for g in groups]

        # api_key 为空 → suggest_rules 直接返回 []
        ai_rules = suggest_rules(groups, api_key="", traces=traces)
        assert ai_rules == [], "api_key 为空时不应返回规则"

        total = sum(t.outstanding_amount for t in traces)
        assert total > UNPAIRED_OUTSTANDING, (
            "不使用 AI 时，未清金额应远大于孤立记录的 200 元"
        )

    def test_ai_does_not_affect_auto_cleared_entries(self):
        """AI 配平不应破坏已自动配平的条目（甲公司货款仍保持 outstanding=0）。"""
        rows = _load_rows()
        _, groups_after, traces_after = _run_pipeline_with_ai(rows)

        for g, t in zip(groups_after, traces_after):
            if "甲公司货款" in g.project_name:
                assert t.outstanding_amount == Decimal("0.00"), (
                    f"AI 配平不应影响已自动清零的项目，{g.project_name} 出现异常"
                )
                return

        pytest.fail("未找到甲公司货款项目，请检查 fixture 数据")


class TestUnpairedEntry:
    """孤立记录验证：无论是否启用 AI，零星行政杂费始终保持未清。"""

    def test_unpaired_row_stays_outstanding_without_ai(self):
        rows = _load_rows()
        unpaired = [r for r in rows if "零星行政杂费" in r.summary]
        assert len(unpaired) == 1, "fixture 中应有且只有 1 行零星行政杂费"

        groups = attribute_projects(unpaired, rules=[])
        trace = trace_project_balance(groups[0].rows, rules=[])
        assert trace.outstanding_amount == UNPAIRED_OUTSTANDING

    def test_unpaired_row_stays_outstanding_after_ai(self):
        rows = _load_rows()
        _, groups_after, traces_after = _run_pipeline_with_ai(rows)

        unpaired_traces = [
            t for g, t in zip(groups_after, traces_after)
            if "零星行政杂费" in g.project_name
        ]
        assert len(unpaired_traces) == 1, "AI 配平后零星行政杂费项目应仍然存在"
        assert unpaired_traces[0].outstanding_amount == UNPAIRED_OUTSTANDING

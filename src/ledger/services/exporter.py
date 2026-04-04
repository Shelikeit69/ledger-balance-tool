from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from ledger.services.attribution import ProjectGroup
from ledger.services.balance_trace import (
    ProjectTrace,
    remaining_trace_lines,
    trace_status_summary,
)

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def export_summary(items: list[tuple[ProjectGroup, ProjectTrace]], path: Path) -> None:
    wb = Workbook()

    # Sheet 1：未配平汇总
    ws1 = wb.active
    ws1.title = "未配平汇总"
    headers1 = ["项目名称", "挂账金额", "方向", "剩余记录数", "状态汇总", "涉及笔数", "主要凭证字号"]
    ws1.append(headers1)
    _style_header_row(ws1, 1)

    for group, trace in items:
        if trace.outstanding_amount > 0:
            ws1.append([
                group.project_name,
                float(trace.outstanding_amount),
                trace.outstanding_direction,
                len(remaining_trace_lines(trace)),
                trace_status_summary(trace),
                len(group.rows),
                ", ".join(group.voucher_nos[:3]),
            ])

    # Sheet 2：配平明细
    ws2 = wb.create_sheet("配平明细")
    headers2 = ["项目名称", "凭证字号", "摘要", "日期", "方向",
                "原始金额", "已配平金额", "剩余金额", "状态"]
    ws2.append(headers2)
    _style_header_row(ws2, 1)

    for group, trace in items:
        for line in trace.lines:
            ws2.append([
                group.project_name,
                line.voucher_no,
                line.summary,
                line.posted_date.isoformat() if line.posted_date else "",
                line.direction,
                float(line.original_amount),
                float(line.matched_amount),
                float(line.remaining_amount),
                line.status,
            ])

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def _style_header_row(ws, row: int) -> None:
    for cell in ws[row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

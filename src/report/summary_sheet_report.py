"""汇总页质检结果写入报告（JSON/HTML/UI），与 FA list findings 并列展示。"""

from __future__ import annotations

from typing import Any

from ingest.summary_sheet import PspProgramRow, SummarySheetDataset
from report.summary import worst_severity
from rules.models import QcIssue, Severity

# 避免超大底稿把 JSON 撑爆；程序行数极多时仅保留前 N 条明细
_MAX_PROGRAMS_IN_REPORT = 400
_MAX_NOTE_CHARS = 600


def _trim_notes(rows: list[PspProgramRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in rows[:_MAX_PROGRAMS_IN_REPORT]:
        wr = p.waiver_reason
        if wr and len(wr) > _MAX_NOTE_CHARS:
            wr = wr[: _MAX_NOTE_CHARS] + "…"
        n = p.notes
        if n and len(n) > _MAX_NOTE_CHARS:
            n = n[: _MAX_NOTE_CHARS] + "…"
        out.append(
            {
                "procedure_name": p.procedure_name,
                "sheet_ref": p.sheet_ref,
                "execution_status": p.execution_status,
                "waiver_reason": wr,
                "notes": n,
                "source_row": p.source_row,
                "is_psp": p.is_psp,
            }
        )
    return out


def build_summary_sheet_section(
    dataset: SummarySheetDataset,
    psp_issues: list[QcIssue],
) -> dict[str, Any]:
    """
    生成写入 ``QcReport.summary_sheet_section`` 的结构：

    - 汇总页 ingest 元数据、列绑定、程序表（截断）
    - AE-003 / ``psp_completion`` 整体结论与 findings（与顶层 ``issues`` 中该规则问题一致）
    """
    psp_only = [i for i in psp_issues if i.rule_id == "psp_completion"]
    overall = worst_severity([i.severity for i in psp_only]) if psp_only else Severity.PASS
    bindings = [
        {
            "role": b.role,
            "source_header": b.source_header,
            "column_index": b.column_index,
        }
        for b in (dataset.column_bindings or [])
    ]
    programs_payload = _trim_notes(dataset.programs)
    ingest_notes = list(dataset.notes or [])[:40]
    return {
        "ingested": True,
        "source_sheet": dataset.source_sheet,
        "layout": dataset.layout,
        "header_row": dataset.header_row,
        "program_count": len(dataset.programs),
        "programs_in_report": len(programs_payload),
        "programs_truncated": len(dataset.programs) > _MAX_PROGRAMS_IN_REPORT,
        "last_data_row": dataset.last_data_row,
        "ingest_notes": ingest_notes,
        "column_bindings": bindings,
        "psp_completion": {
            "dict_rule_code": "AE-003",
            "rule_id": "psp_completion",
            "overall_severity": overall.value,
            "issue_count": len(psp_only),
            "issues": [i.to_dict() for i in psp_only],
        },
        "programs": programs_payload,
    }

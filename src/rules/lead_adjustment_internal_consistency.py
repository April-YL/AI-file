from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_adjustment_gating import is_direct_ppe_account, should_run_strict_total_check
from rules.lead_common import amounts_close, parse_threshold_amount
from rules.models import QcIssue, Severity

RULE_ID = "lead_adjustment_internal_consistency"

_ADJUSTMENT_ROLES = ("book_adjustment", "audit_adjustment")


@dataclass(frozen=True)
class _MainAdjustmentEntry:
    account_label: str
    role: str
    amount: Decimal
    source_row: int


@dataclass(frozen=True)
class _SummaryAdjustmentEntry:
    account_label: str | None
    amount: Decimal | None
    source_row: int
    raw_cells: list[str | None]

    @property
    def is_direct_ppe(self) -> bool:
        return is_direct_ppe_account(self.account_label)


@dataclass(frozen=True)
class _AdjustmentMatch:
    main: _MainAdjustmentEntry
    summary: _SummaryAdjustmentEntry | None
    comparison_mode: str
    comparison_amount: Decimal | None
    difference: Decimal | None

    @property
    def matched(self) -> bool:
        if self.summary is None or self.difference is None:
            return False
        ref = max(abs(self.main.amount), abs(self.comparison_amount or Decimal("0")), Decimal("1"))
        return amounts_close(self.main.amount, self.comparison_amount or Decimal("0"), ref=ref)


def _main_adjustment_entries(lead: LeadSheetDataset) -> list[_MainAdjustmentEntry]:
    entries: list[_MainAdjustmentEntry] = []
    for row in lead.movement_rows:
        for role in _ADJUSTMENT_ROLES:
            amt = parse_threshold_amount(row.values.get(role))
            if amt is not None and amt != 0:
                entries.append(
                    _MainAdjustmentEntry(
                        account_label=row.account_label,
                        role=role,
                        amount=amt,
                        source_row=row.source_row,
                    )
                )
    return entries


def _summary_adjustment_entries(lead: LeadSheetDataset) -> list[_SummaryAdjustmentEntry]:
    entries: list[_SummaryAdjustmentEntry] = []
    for row in lead.adjustment_rows:
        amount: Decimal | None = None
        for cell in row.raw_cells:
            amt = parse_threshold_amount(cell)
            if amt is not None and amt != 0:
                amount = amt
        entries.append(
            _SummaryAdjustmentEntry(
                account_label=_infer_summary_account_label(row.raw_cells),
                amount=amount,
                source_row=row.source_row,
                raw_cells=row.raw_cells,
            )
        )
    return entries


def _infer_summary_account_label(cells: list[str | None]) -> str | None:
    text_cells = [str(cell).strip() for cell in cells if cell and str(cell).strip()]
    direct = next((text for text in text_cells if is_direct_ppe_account(text)), None)
    if direct:
        return direct
    for text in text_cells:
        if _looks_like_adjustment_ref(text) or _looks_like_adjustment_type(text):
            continue
        if parse_threshold_amount(text) is not None:
            continue
        return text
    return None


def _looks_like_adjustment_ref(text: str) -> bool:
    compact = re.sub(r"[\s_\-/]", "", text.strip(), flags=re.IGNORECASE)
    if not compact:
        return False
    if "AA#" in text.upper() or "PRC" in text.upper():
        return True
    return bool(re.fullmatch(r"[A-Z]*\d+[A-Z#]*", compact, flags=re.IGNORECASE))


def _looks_like_adjustment_type(text: str) -> bool:
    compact = text.replace(" ", "").replace("　", "")
    return compact in {
        "调整类型",
        "调整编号",
        "已更正审计调整",
        "未更正审计调整",
        "管理层账表调整",
        "审计调整",
        "账表调整",
    }


def _labels_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    l_norm = re.sub(r"[\s_\-（）()]", "", left)
    r_norm = re.sub(r"[\s_\-（）()]", "", right)
    return bool(l_norm and r_norm and (l_norm in r_norm or r_norm in l_norm))


def _best_match(
    main: _MainAdjustmentEntry,
    candidates: list[_SummaryAdjustmentEntry],
) -> _AdjustmentMatch:
    label_candidates = [
        entry for entry in candidates
        if entry.amount is not None and _labels_match(main.account_label, entry.account_label)
    ]
    if not label_candidates:
        return _AdjustmentMatch(
            main=main,
            summary=None,
            comparison_mode="no_direct_ppe_row",
            comparison_amount=None,
            difference=None,
        )

    best: _AdjustmentMatch | None = None
    for summary in label_candidates:
        assert summary.amount is not None
        same = _AdjustmentMatch(
            main=main,
            summary=summary,
            comparison_mode="same_sign",
            comparison_amount=summary.amount,
            difference=main.amount - summary.amount,
        )
        opposite = _AdjustmentMatch(
            main=main,
            summary=summary,
            comparison_mode="opposite_sign",
            comparison_amount=-summary.amount,
            difference=main.amount + summary.amount,
        )
        candidate = same if abs(same.difference or 0) <= abs(opposite.difference or 0) else opposite
        if best is None or abs(candidate.difference or 0) < abs(best.difference or 0):
            best = candidate
    return best or _AdjustmentMatch(
        main=main,
        summary=None,
        comparison_mode="no_direct_ppe_row",
        comparison_amount=None,
        difference=None,
    )


def build_adjustment_reconciliation_hints(lead: LeadSheetDataset | None) -> list[dict[str, Any]]:
    """Return transparent Lead adjustment matching details for reports / LLM payloads."""
    if lead is None:
        return []
    main_entries = [e for e in _main_adjustment_entries(lead) if is_direct_ppe_account(e.account_label)]
    summary_entries = _summary_adjustment_entries(lead)
    direct_summary = [e for e in summary_entries if e.is_direct_ppe]
    indirect_summary = [e for e in summary_entries if not e.is_direct_ppe and e.amount is not None]
    hints: list[dict[str, Any]] = []
    for main in main_entries:
        match = _best_match(main, direct_summary)
        hints.append(_match_to_dict(match))
    if indirect_summary:
        hints.append(
            {
                "kind": "indirect_counterparty_rows",
                "rows": [
                    {
                        "source_row": entry.source_row,
                        "account_label": entry.account_label,
                        "amount": str(entry.amount) if entry.amount is not None else None,
                    }
                    for entry in indirect_summary
                ],
                "note": "These rows balance the journal entry but are not direct PPE rows.",
            }
        )
    return hints


def _match_to_dict(match: _AdjustmentMatch) -> dict[str, Any]:
    out: dict[str, Any] = {
        "kind": "direct_ppe_amount_check",
        "matched": match.matched,
        "comparison_mode": match.comparison_mode,
        "main": {
            "source_row": match.main.source_row,
            "account_label": match.main.account_label,
            "role": match.main.role,
            "amount": str(match.main.amount),
        },
    }
    if match.summary is not None:
        out["summary"] = {
            "source_row": match.summary.source_row,
            "account_label": match.summary.account_label,
            "raw_amount": str(match.summary.amount) if match.summary.amount is not None else None,
            "comparison_amount": (
                str(match.comparison_amount) if match.comparison_amount is not None else None
            ),
            "difference": str(match.difference) if match.difference is not None else None,
        }
    return out


def _format_match(match: _AdjustmentMatch) -> str:
    main = (
        f"主表第 {match.main.source_row} 行「{match.main.account_label}」"
        f"{_role_label(match.main.role)}={match.main.amount}"
    )
    if match.summary is None:
        return f"{main}；调整汇总表未匹配到同科目的固定资产直接影响行。"
    summary_amount = match.summary.amount if match.summary.amount is not None else "无法读取"
    comparison = match.comparison_amount if match.comparison_amount is not None else "无法折算"
    diff = match.difference if match.difference is not None else "无法计算"
    return (
        f"{main}；调整汇总表第 {match.summary.source_row} 行"
        f"「{match.summary.account_label or '未识别科目'}」原始金额={summary_amount}，"
        f"按 {match.comparison_mode} 折算后={comparison}，差异={diff}。"
    )


def _role_label(role: str) -> str:
    if role == "book_adjustment":
        return "账表调整数"
    if role == "audit_adjustment":
        return "审计调整数"
    return role


def check_lead_adjustment_internal_consistency(
    lead: LeadSheetDataset | None,
    *,
    strict_total: bool | None = None,
    layout_result: dict | None = None,
    extracted_rows: list[dict] | None = None,
) -> list[QcIssue]:
    """Compare Lead movement-table adjustment columns with the Lead adjustment summary only."""
    if lead is None or not lead.source_sheet:
        return []

    if strict_total is None:
        strict_total = should_run_strict_total_check(
            lead,
            layout_result=layout_result,
            extracted_rows=extracted_rows,
        )

    main_entries = _main_adjustment_entries(lead)
    direct_main_entries = [e for e in main_entries if is_direct_ppe_account(e.account_label)]
    summary_rows = [
        r
        for r in lead.adjustment_rows
        if not _is_no_adjustment_conclusion(r.raw_cells)
        and not _is_non_adjustment_note(r.raw_cells)
    ]
    summary_entries = _summary_adjustment_entries(lead)
    direct_summary_entries = [entry for entry in summary_entries if entry.is_direct_ppe]
    issues: list[QcIssue] = []

    if main_entries and not summary_rows:
        labels = "、".join(entry.account_label for entry in main_entries[:5])
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="adjustment_summary",
                severity=Severity.FAIL,
                message=f"Lead 主表存在调整金额，但调整事项汇总表未识别到记录：{labels}",
                suggestion="在 Lead 调整事项汇总表补充对应调整记录，或清理主表调整列。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=main_entries[0].source_row,
            )
        )
        return issues

    if summary_rows and not main_entries:
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="movement_adjustments",
                severity=Severity.WARN,
                message="Lead 调整事项汇总表存在记录，但主表账表/审计调整列未识别到调整金额",
                suggestion="复核调整汇总是否应回填至 Lead 主表调整列，或确认该汇总记录无需影响主表。",
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=summary_rows[0].source_row,
            )
        )
        return issues

    if not strict_total or not direct_main_entries:
        return issues

    matches = [_best_match(entry, direct_summary_entries) for entry in direct_main_entries]
    mismatches = [match for match in matches if not match.matched]
    if mismatches:
        detail = "；".join(_format_match(match) for match in mismatches[:3])
        indirect_rows = [
            entry for entry in summary_entries
            if not entry.is_direct_ppe and entry.amount is not None
        ]
        if indirect_rows:
            detail += "；对方科目行仅用于分录平衡，不参与固定资产直接金额比对："
            detail += "、".join(
                f"第 {entry.source_row} 行「{entry.account_label or '未识别科目'}」={entry.amount}"
                for entry in indirect_rows[:3]
            )
        issues.append(
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="adjustment_amount",
                severity=Severity.NEED_REVIEW,
                message=(
                    "Lead 主表调整列与调整事项汇总表固定资产直接影响行不一致："
                    f"{detail}"
                ),
                suggestion=(
                    "请核对 Lead 主表调整列是否链接到调整汇总表对应固定资产科目行；"
                    "调整汇总表中用于平衡分录的非固定资产对方科目，不应与 Lead 主表直接金额做净额比较。"
                ),
                procedure_code="K.00",
                source_sheet=lead.source_sheet,
                source_row=summary_rows[0].source_row,
            )
        )
    return issues


def _is_no_adjustment_conclusion(cells: list[str | None]) -> bool:
    text = "".join(str(c) for c in cells if c)
    compact = (
        text.replace(" ", "")
        .replace("　", "")
        .replace("。", "")
        .replace(".", "")
        .lower()
    )
    markers = (
        "本年度不涉及审计调整",
        "本年不涉及审计调整",
        "本期不涉及审计调整",
        "不涉及审计调整",
        "无审计调整",
        "无调整事项",
        "不涉及调整事项",
    )
    return any(m.lower() in compact for m in markers)


def _is_non_adjustment_note(cells: list[str | None]) -> bool:
    text_cells = [str(c) for c in cells if c]
    if len(text_cells) != 1:
        return False
    text = text_cells[0]
    compact = (
        text.replace(" ", "")
        .replace("　", "")
        .replace("。", "")
        .replace(".", "")
        .lower()
    )
    return (
        compact.startswith("nb")
        and ("te" in compact or "sad" in compact)
    ) or ("执行阶段" in text and "审定阶段" in text and ("TE" in text or "SAD" in text))

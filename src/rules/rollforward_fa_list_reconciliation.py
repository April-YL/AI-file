from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from ingest.reconciliation import ReconciliationCheck, ReconciliationStatus
from ingest.rollforward_sheet import RollforwardSheetDataset
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import parse_amount

RULE_ID = "rollforward_fa_list_reconciliation"

_AMOUNT_TOL = Decimal("0.01")

_FIELD_BY_LINK_ID: dict[str, str] = {
    "fa_list_rollforward_net": "net_value",
    "fa_list_rollforward_original": "original_value",
    "fa_list_rollforward_accum_dep": "accumulated_depreciation",
}

_FIELD_LABELS: dict[str, str] = {
    "net_value": "净值",
    "original_value": "原值",
    "accumulated_depreciation": "累计折旧",
}


def _rf_source_sheet(rollforward: RollforwardSheetDataset | None) -> str:
    if rollforward and rollforward.source_sheet:
        return rollforward.source_sheet
    return "K.01 Agree SL to GL"


def _issue(
    *,
    rollforward: RollforwardSheetDataset | None,
    field: str | None,
    severity: Severity,
    message: str,
    suggestion: str,
    source_row: int | None = None,
) -> QcIssue:
    return QcIssue(
        asset_id=None,
        rule_id=RULE_ID,
        field=field,
        severity=severity,
        message=message,
        suggestion=suggestion,
        procedure_code="K.01",
        source_sheet=_rf_source_sheet(rollforward),
        source_row=source_row,
    )


def _sad_from_lead(lead: LeadSheetDataset | None) -> Decimal | None:
    if lead is None:
        return None
    sad = parse_amount(field_values(lead).get("sad"))
    if sad is None or sad <= 0:
        return None
    return sad


def _check_table3(
    rollforward: RollforwardSheetDataset,
    *,
    lead: LeadSheetDataset | None = None,
) -> list[QcIssue] | None:
    """主检查：读取 K.01 表3 check 结果。

    返回 None 表示表3不可读，调用方再走辅助/兜底逻辑。
    """
    if not rollforward.section_presence.get("b4_table3_check_with_table1"):
        return None

    values = list(rollforward.table3_check_values or [])
    if not values:
        return None

    diffs = [v for v in values if abs(v) > _AMOUNT_TOL]
    if not diffs:
        return []

    sad = _sad_from_lead(lead)
    if sad is None:
        return [
            _issue(
                rollforward=rollforward,
                field="table3_check_with_table1",
                severity=Severity.NEED_REVIEW,
                message=(
                    "K.01 表3（FA list 汇总表与后推明细表 check）存在差异，"
                    "但未能从 K.00 Lead 可靠读取 SAD"
                ),
                suggestion="请先确认 K.00 Lead 的 SAD（名义金额）是否填写正确，再判断表3差异是否需要 Notes 解释。",
                source_row=rollforward.table3_check_row,
            )
        ]

    material_diffs = [v for v in diffs if abs(v) > sad]
    if not material_diffs:
        return []

    max_diff = max(material_diffs, key=lambda d: abs(d))
    if rollforward.table3_notes_text_present:
        return [
            _issue(
                rollforward=rollforward,
                field="table3_notes_text",
                severity=Severity.NEED_REVIEW,
                message=(
                    "K.01 表3（FA list 汇总表与后推明细表 check）存在超过 SAD 的差异，"
                    f"底稿已有表3 专题 Notes：最大差异={max_diff}，SAD={sad}"
                ),
                suggestion="请质检人员复核 Notes 是否说明差异原因、调查过程、处理结论及是否需要进一步审计程序。",
                source_row=rollforward.table3_notes_row or rollforward.table3_check_row,
            )
        ]

    return [
        _issue(
            rollforward=rollforward,
            field="table3_check_with_table1",
            severity=Severity.FAIL,
            message=(
                "K.01 表3（FA list 汇总表与后推明细表 check）存在超过 SAD 的差异，"
                "但未读取到表3 专题 Notes 解释："
                + "、".join(str(v) for v in material_diffs[:6])
                + f"；SAD={sad}"
            ),
            suggestion=(
                "请在表3 区域或表3 与表4 之间的 Notes 区补充差异说明；"
                "勿仅依赖 TB 或表4 折旧 Notes 代替表3 差异说明。"
            ),
            source_row=rollforward.table3_check_row,
        )
    ]


def _fallback_issue_from_reconciliations(
    reconciliations: list[ReconciliationCheck] | None,
    *,
    rollforward: RollforwardSheetDataset | None,
) -> QcIssue | None:
    """兜底提示：表2/表3读不到时，才引用 Agent 自算合计。"""
    if not reconciliations:
        return None

    relevant = [
        c
        for c in reconciliations
        if c.link_id in _FIELD_BY_LINK_ID
        and c.status
        in (
            ReconciliationStatus.MISMATCH,
            ReconciliationStatus.MISSING_LEFT,
            ReconciliationStatus.MISSING_RIGHT,
            ReconciliationStatus.NEED_REVIEW,
        )
    ]
    if not relevant:
        return None

    parts: list[str] = []
    for check in relevant[:3]:
        field = _FIELD_BY_LINK_ID.get(check.link_id, check.link_id)
        label = _FIELD_LABELS.get(field, field)
        if check.status == ReconciliationStatus.MISMATCH:
            parts.append(
                f"{label}自算差异={check.difference}（FA list={check.left_value}，K.01={check.right_value}）"
            )
        else:
            parts.append(f"{label}无法自算核对：{check.message}")

    return _issue(
        rollforward=rollforward,
        field="fa_list_rollforward_fallback",
        severity=Severity.NEED_REVIEW,
        message=(
            "未能可靠读取 K.01 表3 check 结果；"
            "以下仅为 Agent 根据 FA list 与 K.01 合计做的兜底提示："
            + "；".join(parts)
        ),
        suggestion="请以 K.01 表2 SUMIF 汇总和表3 check 结果为准，人工确认底稿是否已完成 GL-002 核对。",
        source_row=(rollforward.total_row or rollforward.header_row) if rollforward else None,
    )





def build_rollforward_fa_list_reconciliation_observation(
    reconciliations: list[ReconciliationCheck] | None,
    *,
    rollforward: RollforwardSheetDataset | None = None,
    lead: LeadSheetDataset | None = None,
) -> dict:
    if rollforward is None or not rollforward.source_sheet:
        return _evidence_observation(
            checked_data=[
                _evidence_item(
                    sheet=None,
                    section="K.01 后推与 FA list 勾稽",
                    missing_data=["未识别到 K.01 后推工作表"],
                )
            ],
            check_logic="未取得 K.01 后推工作表，未执行后推与 FA list 勾稽检查。",
            expected_result="应识别到 K.01 表3 Check 区或表2 FA list 汇总区。",
            actual_result="未识别到 K.01 后推工作表。",
            result_summary="资料不足，未触发 finding。",
        )

    sad = _sad_from_lead(lead)
    if rollforward.section_presence.get("b4_table3_check_with_table1") and rollforward.table3_check_values:
        diffs = [v for v in rollforward.table3_check_values if abs(v) > _AMOUNT_TOL]
        max_diff = max(diffs, key=lambda d: abs(d)) if diffs else Decimal("0")
        finding_count = 1 if (diffs and (sad is None or abs(max_diff) > sad)) else 0
        checked_data = [
            _evidence_item(
                sheet=rollforward.source_sheet,
                section="K.01 表3 FA list汇总与后推明细 Check 区",
                location=_rows_location([rollforward.table3_check_row]),
                identified_by=_identified_by(
                    sheet=rollforward.source_sheet,
                    section="b4_table3_check_with_table1",
                    keywords=["K.01", "表3", "FA list", "Check", "差异"],
                    rows=[rollforward.table3_check_row],
                ),
                key_columns=["FA list汇总", "K.01后推明细", "Check/差异"],
                values_read=[
                    _value_read(
                        f"表3 Check {idx}",
                        value,
                        row=rollforward.table3_check_row,
                        amount_type="勾稽差异",
                    )
                    for idx, value in enumerate(rollforward.table3_check_values, start=1)
                ],
            )
        ]
        if sad is not None:
            checked_data.append(
                _evidence_item(
                    sheet=lead.source_sheet if lead else None,
                    section="K.00 Lead SAD",
                    identified_by=_identified_by(
                        sheet=lead.source_sheet if lead else None,
                        section="materiality",
                        keywords=["SAD", "名义金额"],
                        rows=[],
                    ),
                    key_columns=["SAD"],
                    values_read=[
                        _value_read("SAD", sad, amount_type="审计阈值")
                    ],
                )
            )
        return _evidence_observation(
            checked_data=checked_data,
            check_logic="优先使用 K.01 表3 Check 区核对 FA list 汇总与 K.01 后推明细是否一致。",
            expected_result="表3 Check 差异应为 0；如存在差异，应结合 SAD 判断是否需要记录异常。",
            actual_result=f"读取到 {len(rollforward.table3_check_values)} 个表3 Check 值，最大差异 {max_diff}。",
            result_summary=f"触发 finding {finding_count} 条。",
        )

    region = rollforward.section_regions.get("b3_table2_fa_summary")
    relevant = [c for c in (reconciliations or []) if c.link_id in _FIELD_BY_LINK_ID]
    relevant_bad = [
        c
        for c in relevant
        if c.status
        in (
            ReconciliationStatus.MISMATCH,
            ReconciliationStatus.MISSING_LEFT,
            ReconciliationStatus.MISSING_RIGHT,
            ReconciliationStatus.NEED_REVIEW,
        )
    ]
    finding_count = 1
    if not rollforward.section_presence.get("b3_table2_fa_summary"):
        finding_count += 1
    elif rollforward.table2_amount_count <= 0:
        finding_count += 1
    if relevant_bad:
        finding_count += 1
    missing_data = ["未可靠识别 K.01 表3 Check 区"]
    if not rollforward.section_presence.get("b3_table2_fa_summary"):
        missing_data.append("未可靠识别 K.01 表2 FA list 汇总区")
    elif rollforward.table2_amount_count <= 0:
        missing_data.append("K.01 表2未读取到可用于核对的汇总金额")
    return _evidence_observation(
        checked_data=[
            _evidence_item(
                sheet=rollforward.source_sheet,
                section="K.01 表2 FA list 汇总区",
                location=_rows_location([region.anchor_row if region else None]),
                identified_by=_identified_by(
                    sheet=rollforward.source_sheet,
                    section="b3_table2_fa_summary",
                    keywords=["K.01", "表2", "FA list", "SUMIF", "汇总"],
                    rows=[region.anchor_row if region else None],
                ),
                key_columns=["FA list汇总金额"],
                values_read=[
                    _value_read(
                        "表2可读取金额数量",
                        rollforward.table2_amount_count,
                        row=region.anchor_row if region else None,
                        amount_type="读取数量",
                    )
                ]
                if rollforward.table2_amount_count > 0
                else [],
                missing_data=missing_data,
            ),
            _evidence_item(
                sheet="FA list / K.01",
                section="Agent 兜底勾稽结果",
                identified_by=_identified_by(
                    sheet="FA list / K.01",
                    section="reconciliations",
                    keywords=["FA list", "K.01", "兜底勾稽"],
                    rows=[],
                ),
                key_columns=["FA list金额", "K.01金额", "差异"],
                values_read=[
                    _value_read(
                        _FIELD_LABELS.get(_FIELD_BY_LINK_ID.get(check.link_id, ""), check.link_id),
                        check.difference,
                        amount_type="兜底差异",
                    )
                    for check in relevant[:6]
                ],
                missing_data=[] if relevant else ["未形成可用的兜底勾稽结果"],
            ),
        ],
        check_logic="K.01 表3 Check 区不可读时，仅记录表2识别情况和 Agent 兜底勾稽结果，不能替代表3正式勾稽结论。",
        expected_result="应优先取得 K.01 表3 Check 结果；表3不可读时，应提示人工复核正式勾稽区域。",
        actual_result=f"表3 Check 未可靠读取；表2读取金额数量 {rollforward.table2_amount_count}；兜底勾稽 {len(relevant)} 项。",
        result_summary=f"触发 finding {finding_count} 条。",
    )


def _evidence_observation(
    *,
    checked_data: list[dict],
    check_logic: str,
    expected_result: str,
    actual_result: str,
    result_summary: str,
) -> dict:
    return {
        "checked_data": checked_data,
        "check_logic": check_logic,
        "expected_result": expected_result,
        "actual_result": actual_result,
        "result_summary": result_summary,
    }


def _evidence_item(
    *,
    sheet: str | None,
    section: str,
    location: str | None = None,
    identified_by: dict | None = None,
    key_columns: list[str] | None = None,
    values_read: list[dict] | None = None,
    missing_data: list[str] | None = None,
) -> dict:
    return {
        "sheet": sheet,
        "section": section,
        "location": location,
        "identified_by": identified_by
        or _identified_by(sheet=sheet, section=section, keywords=[], rows=[]),
        "key_columns": key_columns or [],
        "values_read": values_read or [],
        "missing_data": missing_data or [],
    }


def _identified_by(
    *,
    sheet: str | None,
    section: str,
    keywords: list[str],
    rows,
) -> dict:
    return {
        "sheet_name": sheet,
        "section": section,
        "matched_keywords": keywords,
        "matched_rows": [row for row in rows if isinstance(row, int)],
        "matched_columns": [],
    }


def _value_read(
    label: str,
    value: object,
    *,
    row: int | None = None,
    amount_type: str | None = None,
) -> dict:
    return {
        "label": label,
        "value": None if value is None else str(value),
        "row": row,
        "column": None,
        "cell": None,
        "unit": None,
        "amount_type": amount_type,
    }


def _rows_location(rows) -> str | None:
    row_list = sorted({row for row in rows if isinstance(row, int)})
    if not row_list:
        return None
    return "行 " + ", ".join(str(row) for row in row_list)

def check_rollforward_fa_list_reconciliation(
    reconciliations: list[ReconciliationCheck] | None,
    *,
    rollforward: RollforwardSheetDataset | None = None,
    lead: LeadSheetDataset | None = None,
) -> list[QcIssue]:
    """GL-002：K.01 表3 check 为主，表2为辅助，Agent 自算仅兜底。"""
    if rollforward is None or not rollforward.source_sheet:
        return []

    table3_issues = _check_table3(rollforward, lead=lead)
    if table3_issues is not None:
        return table3_issues

    issues: list[QcIssue] = []
    if not rollforward.section_presence.get("b3_table2_fa_summary"):
        issues.append(
            _issue(
                rollforward=rollforward,
                field="b3_table2_fa_summary",
                severity=Severity.NEED_REVIEW,
                message="未可靠识别 K.01 表2（FA list 关键数据 SUMIF 汇总）",
                suggestion="请人工确认 K.01 是否保留表2，并检查表2是否从 FA list 正确汇总。",
                source_row=None,
            )
        )
    elif rollforward.table2_amount_count <= 0:
        issues.append(
            _issue(
                rollforward=rollforward,
                field="b3_table2_fa_summary",
                severity=Severity.NEED_REVIEW,
                message="已识别 K.01 表2，但未读取到可用于核对的汇总金额",
                suggestion="请检查表2 SUMIF 公式是否有结果，或确认读取范围是否覆盖表2。",
                source_row=rollforward.section_regions.get("b3_table2_fa_summary").anchor_row
                if rollforward.section_regions.get("b3_table2_fa_summary")
                else None,
            )
        )

    issues.append(
        _issue(
            rollforward=rollforward,
            field="b4_table3_check_with_table1",
            severity=Severity.NEED_REVIEW,
            message="未可靠读取 K.01 表3（FA list 汇总表与后推明细表 check）结果",
            suggestion="请人工查看表3 check 是否为 0/一致；后续可根据实际模板继续增强表3读取。",
            source_row=rollforward.section_regions.get("b4_table3_check_with_table1").anchor_row
            if rollforward.section_regions.get("b4_table3_check_with_table1")
            else None,
        )
    )

    fallback = _fallback_issue_from_reconciliations(
        reconciliations,
        rollforward=rollforward,
    )
    if fallback is not None:
        issues.append(fallback)
    return issues

from __future__ import annotations

from decimal import Decimal

from ingest.lead_sheet import LeadSheetDataset
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset, get_movement_transaction_amount
from rules.addition_common import sum_purchase_original_value
from rules.lead_common import field_values
from rules.models import QcIssue, Severity
from rules.parsing import amount_tolerance, parse_amount

RULE_ID = "addition_rollforward_reconciliation"
_AMOUNT_TOL = Decimal("0.01")


def _sad_from_lead(lead: LeadSheetDataset | None) -> Decimal | None:
    if lead is None:
        return None
    sad = parse_amount(field_values(lead).get("sad"))
    if sad is None or sad <= 0:
        return None
    return sad


def check_addition_rollforward_reconciliation(
    addition_list: FaListDataset | None,
    *,
    rollforward: RollforwardSheetDataset | None = None,
    lead: LeadSheetDataset | None = None,
) -> list[QcIssue]:
    """SP-002：新增清单购置原值合计 vs K.01 后推购置行金额。"""
    if addition_list is None or not addition_list.records:
        return []

    mapped = {m.standard_field for m in addition_list.mapped_fields}
    list_total, list_count = sum_purchase_original_value(addition_list.records, mapped)
    if list_total is None:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="original_value",
                severity=Severity.NEED_REVIEW,
                message="新增清单存在记录，但未能汇总购置类新增原值（缺少原值列或未识别购置新增方式）。",
                suggestion="确认新增清单已映射原值与新增方式列，并区分购置与其他新增方式。",
                procedure_code="K.02.1",
                source_sheet=addition_list.source_sheet,
            )
        ]

    if rollforward is None or not rollforward.source_sheet:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="original_value",
                severity=Severity.NEED_REVIEW,
                message=(
                    f"新增清单购置原值合计={list_total}（{list_count} 行），"
                    "但未读取到 K.01 后推表，无法核对购置金额。"
                ),
                suggestion="确认工作簿包含 K.01 后推明细表，并检查 sheet 名称是否可被识别。",
                procedure_code="K.02.1",
                source_sheet=addition_list.source_sheet,
            )
        ]

    rf_amount, rf_row = get_movement_transaction_amount(
        rollforward,
        transaction_key="purchase",
        measure="original_value",
    )
    if rf_amount is None:
        return [
            QcIssue(
                asset_id=None,
                rule_id=RULE_ID,
                field="original_value",
                severity=Severity.NEED_REVIEW,
                message=(
                    f"新增清单购置原值合计={list_total}（{list_count} 行），"
                    "但未在 K.01 后推表中识别到「购置」交易行金额。"
                ),
                suggestion=(
                    "请人工核对 K.01 表1/变动区是否列示购置金额；"
                    "若模板变体未覆盖，可在后续版本补充 ingest 规则。"
                ),
                procedure_code="K.02.1",
                source_sheet=addition_list.source_sheet,
            )
        ]

    diff = abs(list_total - rf_amount)
    tol = amount_tolerance(max(abs(list_total), abs(rf_amount)), absolute=_AMOUNT_TOL)
    if diff <= tol:
        return []

    sad = _sad_from_lead(lead)
    over_sad = sad is not None and diff > sad
    message = (
        f"新增清单购置原值合计={list_total}（{list_count} 行），"
        f"K.01 后推购置金额={rf_amount}，差异={diff}。"
    )
    if over_sad:
        message += f" 差异超过 SAD（{sad}），需调查。"
    suggestion = (
        "核对新增清单与 K.01 后推明细表购置行是否口径一致（仅购置、不含在建转入等）；"
        "检查是否存在遗漏/重复资产、分类错误或金额填列错误。"
    )
    if over_sad:
        suggestion += " 差异超过 SAD 时，请在底稿 Notes 区记录调查结论。"

    return [
        QcIssue(
            asset_id=None,
            rule_id=RULE_ID,
            field="original_value",
            severity=Severity.WARN,
            message=message,
            suggestion=suggestion,
            procedure_code="K.02.1",
            source_sheet=addition_list.source_sheet,
            source_row=rf_row,
        )
    ]

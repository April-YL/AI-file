"""跨 sheet 勾稽关系定义与比对。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from ingest.models import AssetRecord, SheetKind
from ingest.records import FaListDataset
from ingest.rollforward_sheet import RollforwardSheetDataset, get_movement_transaction_amount
from rules.addition_common import sum_purchase_original_value
from rules.parsing import amount_tolerance, parse_amount

# 模块内聚合，避免 ingest → rules 循环（仅使用 parsing 工具函数）


class ReconciliationStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    MISSING_LEFT = "missing_left"
    MISSING_RIGHT = "missing_right"
    NOT_APPLICABLE = "not_applicable"
    NEED_REVIEW = "need_review"


@dataclass(frozen=True)
class ReconciliationLinkSpec:
    link_id: str
    dict_rule_code: str
    name: str
    left_label: str
    right_label: str
    amount_field: str
    procedure_hint: str


RECONCILIATION_LINKS: tuple[ReconciliationLinkSpec, ...] = (
    ReconciliationLinkSpec(
        link_id="fa_list_rollforward_net",
        dict_rule_code="GL-002",
        name="FA list 净值与后推期末净值",
        left_label="FA list 净值合计",
        right_label="K.01 后推期末净值",
        amount_field="net_value",
        procedure_hint="K.01 / FA list",
    ),
    ReconciliationLinkSpec(
        link_id="fa_list_rollforward_original",
        dict_rule_code="GL-002",
        name="FA list 原值与后推期末原值",
        left_label="FA list 原值合计",
        right_label="K.01 后推期末原值",
        amount_field="original_value",
        procedure_hint="K.01 / FA list",
    ),
    ReconciliationLinkSpec(
        link_id="fa_list_rollforward_accum_dep",
        dict_rule_code="GL-002",
        name="FA list 累计折旧与后推期末累计折旧",
        left_label="FA list 累计折旧合计",
        right_label="K.01 后推期末累计折旧",
        amount_field="accumulated_depreciation",
        procedure_hint="K.01 / FA list",
    ),
    ReconciliationLinkSpec(
        link_id="addition_list_rollforward",
        dict_rule_code="SP-002",
        name="新增清单原值与后推本期增加",
        left_label="新增清单原值合计",
        right_label="K.01 后推本期增加原值",
        amount_field="original_value",
        procedure_hint="K.02.1 / K.01",
    ),
    ReconciliationLinkSpec(
        link_id="disposal_list_rollforward",
        dict_rule_code="SP-002",
        name="处置清单净值与后推本期减少",
        left_label="处置清单净值合计",
        right_label="K.01 后推本期减少净值",
        amount_field="net_value",
        procedure_hint="K.02.2 / K.01",
    ),
)


@dataclass
class ReconciliationCheck:
    link_id: str
    dict_rule_code: str
    name: str
    status: ReconciliationStatus
    left_ref: str | None
    right_ref: str | None
    left_value: str | None
    right_value: str | None
    difference: str | None
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "dict_rule_code": self.dict_rule_code,
            "name": self.name,
            "status": self.status.value,
            "left_ref": self.left_ref,
            "right_ref": self.right_ref,
            "left_value": self.left_value,
            "right_value": self.right_value,
            "difference": self.difference,
            "message": self.message,
            "suggestion": self.suggestion,
        }


def _sum_dataset(records: list[AssetRecord], field_name: str) -> Decimal | None:
    total = Decimal("0")
    seen = False
    for rec in records:
        val = parse_amount(getattr(rec, field_name, None))
        if val is not None:
            total += val
            seen = True
    return total if seen else None


def _fmt_amount(val: Decimal | None) -> str | None:
    if val is None:
        return None
    return str(val)


def _compare_amounts(
    left: Decimal | None,
    right: Decimal | None,
    *,
    left_ref: str,
    right_ref: str,
    spec: ReconciliationLinkSpec,
) -> ReconciliationCheck:
    if left is None and right is None:
        return ReconciliationCheck(
            link_id=spec.link_id,
            dict_rule_code=spec.dict_rule_code,
            name=spec.name,
            status=ReconciliationStatus.NOT_APPLICABLE,
            left_ref=left_ref,
            right_ref=right_ref,
            left_value=None,
            right_value=None,
            difference=None,
            message="两侧均无可用金额，跳过勾稽",
        )
    if left is None:
        return ReconciliationCheck(
            link_id=spec.link_id,
            dict_rule_code=spec.dict_rule_code,
            name=spec.name,
            status=ReconciliationStatus.MISSING_LEFT,
            left_ref=left_ref,
            right_ref=right_ref,
            left_value=None,
            right_value=_fmt_amount(right),
            difference=None,
            message=f"{spec.left_label} 缺失，无法与 {spec.right_label} 比对",
            suggestion="补充左侧数据或确认该程序是否适用",
        )
    if right is None:
        return ReconciliationCheck(
            link_id=spec.link_id,
            dict_rule_code=spec.dict_rule_code,
            name=spec.name,
            status=ReconciliationStatus.MISSING_RIGHT,
            left_ref=left_ref,
            right_ref=right_ref,
            left_value=_fmt_amount(left),
            right_value=None,
            difference=None,
            message=f"{spec.right_label} 缺失，无法与 {spec.left_label} 比对",
            suggestion="补充 K.01 后推合计行或检查表头映射",
        )

    diff = left - right
    tol = amount_tolerance(max(abs(left), abs(right)))
    if abs(diff) <= tol:
        status = ReconciliationStatus.MATCH
        message = f"{spec.left_label} 与 {spec.right_label} 一致（允差 {tol}）"
        suggestion = ""
    else:
        status = ReconciliationStatus.MISMATCH
        message = f"{spec.left_label} 与 {spec.right_label} 不一致，差异 {diff}"
        suggestion = "调查差异是否超过 SAD，并核对底稿与台账来源"

    return ReconciliationCheck(
        link_id=spec.link_id,
        dict_rule_code=spec.dict_rule_code,
        name=spec.name,
        status=status,
        left_ref=left_ref,
        right_ref=right_ref,
        left_value=_fmt_amount(left),
        right_value=_fmt_amount(right),
        difference=_fmt_amount(diff),
        message=message,
        suggestion=suggestion,
    )


def run_fa_rollforward_reconciliations(
    fa_list: FaListDataset | None,
    rollforward: RollforwardSheetDataset | None,
    *,
    fields: tuple[str, ...] = ("net_value", "original_value", "accumulated_depreciation"),
) -> list[ReconciliationCheck]:
    """FA list 与 K.01 后推期末余额类勾稽。"""
    link_by_field = {s.amount_field: s for s in RECONCILIATION_LINKS if s.link_id.startswith("fa_list_rollforward")}
    checks: list[ReconciliationCheck] = []

    left_ref = f"{fa_list.source_sheet}!{SheetKind.FA_LIST.value}" if fa_list and fa_list.source_sheet else None
    right_ref = (
        f"{rollforward.source_sheet}!row{rollforward.total_row}"
        if rollforward and rollforward.source_sheet and rollforward.total_row
        else (f"{rollforward.source_sheet}" if rollforward and rollforward.source_sheet else None)
    )

    for field_name in fields:
        spec = link_by_field.get(field_name)
        if spec is None:
            continue
        left_val = _sum_dataset(fa_list.records, field_name) if fa_list and fa_list.records else None
        right_val = rollforward.ending_totals.get(field_name) if rollforward else None
        checks.append(
            _compare_amounts(
                left_val,
                right_val,
                left_ref=left_ref or spec.left_label,
                right_ref=right_ref or spec.right_label,
                spec=spec,
            )
        )
    return checks


def run_list_rollforward_reconciliations(
    dataset: FaListDataset | None,
    rollforward: RollforwardSheetDataset | None,
    *,
    link_id: str,
) -> ReconciliationCheck:
    spec = next(s for s in RECONCILIATION_LINKS if s.link_id == link_id)
    left_ref = dataset.source_sheet if dataset and dataset.source_sheet else None

    left_val = _sum_dataset(dataset.records, spec.amount_field) if dataset and dataset.records else None
    if link_id == "addition_list_rollforward" and dataset is not None:
        mapped = {m.standard_field for m in dataset.mapped_fields}
        purchase_total, _ = sum_purchase_original_value(dataset.records, mapped)
        if purchase_total is not None:
            left_val = purchase_total
    right_val: Decimal | None = None
    right_ref = rollforward.source_sheet if rollforward and rollforward.source_sheet else None

    if link_id == "addition_list_rollforward" and rollforward is not None:
        rf_amount, _ = get_movement_transaction_amount(
            rollforward,
            transaction_key="purchase",
            measure="original_value",
        )
        if rf_amount is not None:
            right_val = rf_amount

    if left_val is None:
        return ReconciliationCheck(
            link_id=spec.link_id,
            dict_rule_code=spec.dict_rule_code,
            name=spec.name,
            status=ReconciliationStatus.NOT_APPLICABLE,
            left_ref=left_ref,
            right_ref=right_ref,
            left_value=None,
            right_value=None,
            difference=None,
            message=f"无 {spec.left_label} 数据",
        )

    if right_val is None:
        return ReconciliationCheck(
            link_id=spec.link_id,
            dict_rule_code=spec.dict_rule_code,
            name=spec.name,
            status=ReconciliationStatus.NEED_REVIEW,
            left_ref=left_ref,
            right_ref=right_ref,
            left_value=_fmt_amount(left_val),
            right_value=None,
            difference=None,
            message=(
                f"{spec.left_label}={left_val}；{spec.right_label} 待从 K.01 变动行解析（当前仅支持期末合计勾稽）"
            ),
            suggestion="人工核对后推本期增加/减少与清单合计；后续版本将解析 K.01 变动列",
        )

    diff = left_val - right_val
    tol = amount_tolerance(max(abs(left_val), abs(right_val)))
    if abs(diff) <= tol:
        return ReconciliationCheck(
            link_id=spec.link_id,
            dict_rule_code=spec.dict_rule_code,
            name=spec.name,
            status=ReconciliationStatus.MATCH,
            left_ref=left_ref,
            right_ref=right_ref,
            left_value=_fmt_amount(left_val),
            right_value=_fmt_amount(right_val),
            difference=_fmt_amount(diff),
            message=f"{spec.left_label} 与 {spec.right_label} 一致",
        )

    return ReconciliationCheck(
        link_id=spec.link_id,
        dict_rule_code=spec.dict_rule_code,
        name=spec.name,
        status=ReconciliationStatus.MISMATCH,
        left_ref=left_ref,
        right_ref=right_ref,
        left_value=_fmt_amount(left_val),
        right_value=_fmt_amount(right_val),
        difference=_fmt_amount(diff),
        message=(
            f"{spec.left_label}={left_val}，{spec.right_label}={right_val}，差异={diff}"
        ),
        suggestion="核对新增/处置清单与 K.01 后推对应交易行金额是否口径一致。",
    )


def run_workbook_reconciliations(
    *,
    fa_list: FaListDataset | None,
    rollforward: RollforwardSheetDataset | None,
    addition_list: FaListDataset | None = None,
    disposal_list: FaListDataset | None = None,
) -> list[ReconciliationCheck]:
    checks: list[ReconciliationCheck] = []
    checks.extend(run_fa_rollforward_reconciliations(fa_list, rollforward))
    checks.append(
        run_list_rollforward_reconciliations(
            addition_list,
            rollforward,
            link_id="addition_list_rollforward",
        )
    )
    checks.append(
        run_list_rollforward_reconciliations(
            disposal_list,
            rollforward,
            link_id="disposal_list_rollforward",
        )
    )
    return checks

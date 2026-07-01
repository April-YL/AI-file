from __future__ import annotations

from collections.abc import Iterable

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import (
    GAM_TT_RATIO_BANDS,
    cra_tier,
    effective_overall_threshold,
    field_values,
    parse_threshold_amount,
    skip_cra_module,
)
from rules.lead_required_fields import LEAD_REQUIRED_FIELD_KEYS
from rules.models import QcIssue, Severity

_FIELD_LABELS = {
    "client_name": "客户名称",
    "period_end": "期末",
    "analysis_date": "分析日期",
    "te": "TE",
    "sad": "SAD",
    "gaap": "适用会计准则",
    "currency": "记账本位币",
}


def build_lead_required_fields_observation(
    lead: LeadSheetDataset | None,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    if lead is None or not lead.source_sheet:
        return _observation(
            checked_data=[
                _checked_data(
                    sheet=None,
                    section="K.00 Lead Sheet 基础信息",
                    location=None,
                    matched_keywords=[],
                    matched_rows=[],
                    matched_columns=[],
                    key_columns=list(LEAD_REQUIRED_FIELD_KEYS),
                    values_read=[],
                    missing_data=["K.00 Lead Sheet"],
                )
            ],
            check_logic="检查是否识别到 K.00 Lead Sheet，并读取基础信息区的客户名称、期末、分析日期、TE、SAD、适用会计准则和记账本位币。",
            expected_result="Lead 基础信息区应完整填写上述必需字段。",
            actual_result="本次未识别到可用于检查的 K.00 Lead Sheet。",
            result_summary=_result_summary(issues),
        )

    fields_by_key = {field.field_key: field for field in lead.basic_info_fields}
    values = field_values(lead)
    missing = [
        _FIELD_LABELS.get(key, key)
        for key in LEAD_REQUIRED_FIELD_KEYS
        if not str(values.get(key) or "").strip()
    ]
    matched_rows = [
        field.source_row
        for key in LEAD_REQUIRED_FIELD_KEYS
        for field in [fields_by_key.get(key)]
        if field is not None and field.source_row is not None
    ]
    matched_columns = [
        field.source_col
        for key in LEAD_REQUIRED_FIELD_KEYS
        for field in [fields_by_key.get(key)]
        if field is not None and field.source_col is not None
    ]
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet 基础信息",
                location=_rows_location(matched_rows),
                matched_keywords=[
                    fields_by_key[key].label
                    for key in LEAD_REQUIRED_FIELD_KEYS
                    if key in fields_by_key
                ],
                matched_rows=matched_rows,
                matched_columns=matched_columns,
                key_columns=list(LEAD_REQUIRED_FIELD_KEYS),
                values_read=[
                    _value_read(
                        label=_FIELD_LABELS.get(key, key),
                        value=values.get(key),
                        row=fields_by_key.get(key).source_row if key in fields_by_key else None,
                        column=fields_by_key.get(key).source_col if key in fields_by_key else None,
                        amount_type="Lead 基础信息",
                    )
                    for key in LEAD_REQUIRED_FIELD_KEYS
                ],
                missing_data=missing,
            )
        ],
        check_logic="逐项读取 Lead 基础信息区，检查客户名称、期末、分析日期、TE、SAD、适用会计准则和记账本位币是否为空。",
        expected_result="上述必需字段均应已填写，且能够追溯到 Lead Sheet 的具体行列。",
        actual_result=(
            f"本次识别到 {len(lead.basic_info_fields)} 个基础信息字段，"
            f"必需字段缺失 {len(missing)} 项。"
        ),
        result_summary=_result_summary(issues),
    )


def build_lead_ingest_readability_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    block_rows = [
        row
        for block in lead.blocks
        for row in (block.start_row, block.end_row)
        if row is not None
    ]
    missing = []
    if not lead.movement_rows:
        missing.append("Lead movement table rows")
    if not lead.usable_for_rules:
        missing.append("usable movement table structure")
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet 资料识别质量",
                location=_rows_location(block_rows),
                matched_keywords=[block.anchor_text for block in lead.blocks if block.anchor_text],
                matched_rows=block_rows,
                matched_columns=[],
                key_columns=[
                    "blocks",
                    "movement_bindings",
                    "movement_rows",
                    "check_with_a3",
                ],
                values_read=[
                    _value_read(
                        label="识别到的资料区块数",
                        value=len(lead.blocks),
                        row=None,
                        column=None,
                        amount_type="ingest",
                    ),
                    _value_read(
                        label="识别到的 movement 行数",
                        value=len(lead.movement_rows),
                        row=None,
                        column=None,
                        amount_type="ingest",
                    ),
                    _value_read(
                        label="识别到的 movement 列绑定数",
                        value=len(lead.movement_bindings),
                        row=None,
                        column=None,
                        amount_type="ingest",
                    ),
                    _value_read(
                        label="是否可继续执行 Lead 明细规则",
                        value="是" if lead.usable_for_rules else "否",
                        row=None,
                        column=None,
                        amount_type="ingest_status",
                    ),
                ],
                missing_data=missing,
            )
        ],
        check_logic="检查 Lead 资料识别结果是否足以支撑后续 Lead 明细规则继续执行，重点看 movement table 行、列绑定和 Check with A3 / Diff 区域是否可靠。",
        expected_result="Lead movement table 应能稳定识别核心账户行和关键金额列，才能继续执行依赖 Lead 明细的规则。",
        actual_result=(
            f"本次识别到 {len(lead.blocks)} 个资料区块、"
            f"{len(lead.movement_rows)} 行 movement 数据、"
            f"{len(lead.movement_bindings)} 个 movement 列绑定；"
            f"可继续执行状态：{'是' if lead.usable_for_rules else '否'}。"
        ),
        result_summary=_result_summary(issues),
    )


def build_lead_data_insufficient_observation(
    lead: LeadSheetDataset,
    *,
    rule_id: str,
    reason: str,
) -> dict:
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet 参数类规则执行前置条件",
                location=None,
                matched_keywords=[block.anchor_text for block in lead.blocks if block.anchor_text],
                matched_rows=[],
                matched_columns=[],
                key_columns=_required_keys_for_rule(rule_id),
                values_read=[],
                missing_data=[reason],
            )
        ],
        check_logic="本规则依赖 Lead Sheet 的参数区或 CRA/TT 区；当 Lead 资料识别质量不足时，仅记录未执行原因，不读取或推断参数值。",
        expected_result="Lead Sheet 应能稳定识别基础信息、CRA/TT 或波动阈值等参数资料后，才执行本规则。",
        actual_result=f"本次未执行该规则：{reason}",
        result_summary="资料不足，未执行本规则。",
    )


def build_lead_analysis_date_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    fields = _basic_fields_by_key(lead)
    values = field_values(lead)
    keys = ["period_end", "analysis_date"]
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet 分析日期参数",
                location=_rows_location([fields[key].source_row for key in keys if key in fields]),
                matched_keywords=[fields[key].label for key in keys if key in fields],
                matched_rows=[fields[key].source_row for key in keys if key in fields],
                matched_columns=[fields[key].source_col for key in keys if key in fields],
                key_columns=keys,
                values_read=[
                    _value_read(
                        label=_FIELD_LABELS.get(key, key),
                        value=values.get(key),
                        row=fields.get(key).source_row if key in fields else None,
                        column=fields.get(key).source_col if key in fields else None,
                        amount_type="Lead 日期参数",
                    )
                    for key in keys
                ],
                missing_data=[_FIELD_LABELS.get(key, key) for key in keys if not str(values.get(key) or "").strip()],
            )
        ],
        check_logic="读取 Lead Sheet 的期末和分析日期，检查分析日期是否不早于期末。",
        expected_result="分析日期应等于或晚于期末日期。",
        actual_result=f"本次读取期末={values.get('period_end') or ''}，分析日期={values.get('analysis_date') or ''}。",
        result_summary=_result_summary(issues),
    )


def build_materiality_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    values = _materiality_values(lead)
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet PM/TE/SAD 摘录",
                location=_rows_location([row.source_row for row in lead.materiality]),
                matched_keywords=[row.label for row in lead.materiality],
                matched_rows=[row.source_row for row in lead.materiality],
                matched_columns=[
                    col
                    for row in lead.materiality
                    for col in (row.source_col_workpaper, row.source_col_canvas)
                    if col is not None
                ],
                key_columns=["pm", "te", "sad"],
                values_read=values,
                missing_data=[] if values else ["PM/TE/SAD"],
            )
        ],
        check_logic="读取 Lead Sheet 中 PM、TE、SAD 的底稿值及可识别的 Canvas/外部值，仅作为人工核对证据。",
        expected_result="PM、TE、SAD 应与 Canvas 或项目最终重要性参数一致；该规则只提示人工核对，不自动给出通过结论。",
        actual_result=f"本次摘录到 {len(values)} 个 PM/TE/SAD 相关值，需人工对照 Canvas 核对。",
        result_summary=_result_summary(issues),
    )


def build_risk_threshold_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    values = _cra_values(lead)
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet CRA/TT 参数表",
                location=_rows_location([row.source_row for row in lead.cra_rows]),
                matched_keywords=[row.assertion for row in lead.cra_rows],
                matched_rows=[row.source_row for row in lead.cra_rows],
                matched_columns=[
                    col
                    for row in lead.cra_rows
                    for col in (
                        row.source_col_assertion,
                        row.source_col_cra,
                        row.source_col_tt,
                        row.source_col_tt_overall,
                    )
                    if col is not None
                ],
                key_columns=["assertion", "cra", "tt", "tt_overall"],
                values_read=values,
                missing_data=[] if lead.cra_rows or skip_cra_module(lead) else ["CRA/TT 参数表"],
            )
        ],
        check_logic="读取各认定的 CRA、TT 和整体 TT，仅作为人工复核 CRA/TT 是否与 Canvas 或风险底稿一致的证据。",
        expected_result="各认定 CRA、TT 应与 Canvas 或风险底稿一致；该规则只提示人工核对，不自动给出通过结论。",
        actual_result=f"本次摘录到 {len(lead.cra_rows)} 行 CRA/TT 参数。",
        result_summary=_result_summary(issues),
    )


def build_lead_tt_overall_min_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    tts = [
        parse_threshold_amount(row.tt)
        for row in lead.cra_rows
        if parse_threshold_amount(row.tt) is not None and parse_threshold_amount(row.tt) > 0
    ]
    expected = min(tts) if tts else None
    overall = effective_overall_threshold(lead.cra_rows)
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet 整体 TT 与认定 TT",
                location=_rows_location([row.source_row for row in lead.cra_rows]),
                matched_keywords=[row.assertion for row in lead.cra_rows],
                matched_rows=[row.source_row for row in lead.cra_rows],
                matched_columns=[
                    col
                    for row in lead.cra_rows
                    for col in (row.source_col_tt, row.source_col_tt_overall)
                    if col is not None
                ],
                key_columns=["tt", "tt_overall"],
                values_read=_cra_values(lead),
                missing_data=[] if lead.cra_rows else ["CRA/TT 参数表"],
            )
        ],
        check_logic="读取各认定 TT 和整体 TT，检查整体 TT 是否等于各认定 TT 中最小的非零金额。",
        expected_result="整体 TT 应等于各认定 TT 的最小非零金额。",
        actual_result=f"本次计算最小认定 TT={_text(expected)}，整体 TT={_text(overall)}。",
        result_summary=_result_summary(issues),
    )


def build_lead_tt_gam_range_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    fields = _basic_fields_by_key(lead)
    values = field_values(lead)
    te = parse_threshold_amount(values.get("te"))
    cra_values = _cra_values(lead)
    if "te" in fields:
        cra_values.insert(
            0,
            _value_read(
                label="TE",
                value=values.get("te"),
                row=fields["te"].source_row,
                column=fields["te"].source_col,
                amount_type="Lead 参数",
            ),
        )
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet CRA/TT GAM 区间",
                location=_rows_location([row.source_row for row in lead.cra_rows]),
                matched_keywords=[row.assertion for row in lead.cra_rows],
                matched_rows=[row.source_row for row in lead.cra_rows],
                matched_columns=[
                    col
                    for row in lead.cra_rows
                    for col in (row.source_col_cra, row.source_col_tt)
                    if col is not None
                ],
                key_columns=["te", "assertion", "cra", "tt", "tt_te_ratio"],
                values_read=cra_values,
                missing_data=[] if te is not None and lead.cra_rows else ["TE 或 CRA/TT 参数表"],
            )
        ],
        check_logic="读取 TE、各认定 CRA 和 TT，按 CRA 档位计算 TT/TE 比例是否落在 GAM 建议区间内。",
        expected_result="Minimal/Low/Moderate/High 各档 CRA 的 TT/TE 比例应落在对应 GAM 区间内。",
        actual_result=f"本次读取 TE={_text(te)}，CRA/TT 行数={len(lead.cra_rows)}。",
        result_summary=_result_summary(issues),
    )


def build_lead_volatility_threshold_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    fields = _basic_fields_by_key(lead)
    values = field_values(lead)
    vol = lead.volatility
    target_label = "TE" if skip_cra_module(lead) else "整体 TT"
    target_value = parse_threshold_amount(values.get("te")) if skip_cra_module(lead) else effective_overall_threshold(lead.cra_rows)
    values_read = []
    if vol is not None:
        values_read.extend(
            [
                _value_read(
                    label="波动金额阈值",
                    value=vol.amount,
                    row=vol.source_row_amount,
                    column=None,
                    amount_type="Lead 波动阈值",
                ),
                _value_read(
                    label="波动比例阈值",
                    value=vol.percent,
                    row=vol.source_row_percent,
                    column=None,
                    amount_type="Lead 波动阈值",
                ),
            ]
        )
    if target_label == "TE" and "te" in fields:
        values_read.append(
            _value_read(
                label="TE",
                value=values.get("te"),
                row=fields["te"].source_row,
                column=fields["te"].source_col,
                amount_type="Lead 参数",
            )
        )
    elif target_value is not None:
        values_read.append(
            _value_read(
                label="整体 TT",
                value=target_value,
                row=None,
                column=None,
                amount_type="Lead 参数",
            )
        )
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Sheet 波动阈值",
                location=_rows_location(
                    [
                        vol.source_row_amount if vol else None,
                        vol.source_row_percent if vol else None,
                    ]
                ),
                matched_keywords=["波动幅度", target_label],
                matched_rows=[
                    vol.source_row_amount if vol else None,
                    vol.source_row_percent if vol else None,
                ],
                matched_columns=[],
                key_columns=["volatility_amount", "volatility_percent", target_label],
                values_read=values_read,
                missing_data=[] if vol is not None else ["波动阈值"],
            )
        ],
        check_logic=f"读取波动金额阈值，并检查其是否 link 到 {target_label}。",
        expected_result=f"波动金额阈值应与 {target_label} 一致。",
        actual_result=f"本次读取波动金额={vol.amount if vol else ''}，对照参数 {target_label}={_text(target_value)}。",
        result_summary=_result_summary(issues),
    )


def _required_keys_for_rule(rule_id: str) -> list[str]:
    return {
        "lead_analysis_date_after_period_end": ["period_end", "analysis_date"],
        "materiality_consistency": ["pm", "te", "sad"],
        "risk_threshold_consistency": ["assertion", "cra", "tt", "tt_overall"],
        "lead_tt_overall_min": ["tt", "tt_overall"],
        "lead_tt_gam_range": ["te", "cra", "tt"],
        "lead_volatility_threshold_link": ["volatility_amount", "te", "tt_overall"],
    }.get(rule_id, [])


def _basic_fields_by_key(lead: LeadSheetDataset):
    return {field.field_key: field for field in lead.basic_info_fields}


def _materiality_values(lead: LeadSheetDataset) -> list[dict]:
    values: list[dict] = []
    fields = _basic_fields_by_key(lead)
    for key in ("pm", "te", "sad"):
        field = fields.get(key)
        if field is not None:
            values.append(
                _value_read(
                    label=_FIELD_LABELS.get(key, key.upper()),
                    value=field.value,
                    row=field.source_row,
                    column=field.source_col,
                    amount_type="Lead 重要性参数",
                )
            )
    for item in lead.materiality:
        if item.workpaper_value:
            values.append(
                _value_read(
                    label=f"{item.label} 底稿值",
                    value=item.workpaper_value,
                    row=item.source_row,
                    column=item.source_col_workpaper,
                    amount_type="Lead 重要性参数",
                )
            )
        if item.canvas_value:
            values.append(
                _value_read(
                    label=f"{item.label} Canvas/外部值",
                    value=item.canvas_value,
                    row=item.source_row,
                    column=item.source_col_canvas,
                    amount_type="外部核对参数",
                )
            )
    return values[:20]


def _cra_values(lead: LeadSheetDataset) -> list[dict]:
    values: list[dict] = []
    for row in lead.cra_rows:
        values.extend(
            [
                _value_read(
                    label=f"{row.assertion} CRA",
                    value=row.cra,
                    row=row.source_row,
                    column=row.source_col_cra,
                    amount_type="Lead CRA",
                ),
                _value_read(
                    label=f"{row.assertion} TT",
                    value=row.tt,
                    row=row.source_row,
                    column=row.source_col_tt,
                    amount_type="Lead TT",
                ),
                _value_read(
                    label=f"{row.assertion} 整体 TT",
                    value=row.tt_overall,
                    row=row.source_row,
                    column=row.source_col_tt_overall,
                    amount_type="Lead TT",
                ),
            ]
        )
        te_ratio = None
        tt = parse_threshold_amount(row.tt)
        if tt is not None:
            tier = cra_tier(row.cra)
            if tier in GAM_TT_RATIO_BANDS:
                te_ratio = f"CRA={row.cra}; GAM={GAM_TT_RATIO_BANDS[tier][0]}-{GAM_TT_RATIO_BANDS[tier][1]}"
        if te_ratio:
            values.append(
                _value_read(
                    label=f"{row.assertion} GAM 区间",
                    value=te_ratio,
                    row=row.source_row,
                    column=row.source_col_cra,
                    amount_type="GAM 区间",
                )
            )
    return values[:20]


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _observation(
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


def _checked_data(
    *,
    sheet: str | None,
    section: str,
    location: str | None,
    matched_keywords: list[str],
    matched_rows: list[int | None],
    matched_columns: list[int | None],
    key_columns: list[str],
    values_read: list[dict],
    missing_data: list[str],
) -> dict:
    return {
        "sheet": sheet,
        "section": section,
        "location": location,
        "identified_by": {
            "sheet_name": sheet,
            "section": section,
            "matched_keywords": [str(value) for value in matched_keywords if value][:12],
            "matched_rows": _clean_ints(matched_rows),
            "matched_columns": _clean_ints(matched_columns),
        },
        "key_columns": key_columns[:12],
        "values_read": values_read[:20],
        "missing_data": missing_data[:12],
    }


def _value_read(
    *,
    label: str,
    value: object,
    row: int | None,
    column: int | None,
    amount_type: str,
) -> dict:
    return {
        "label": label,
        "value": "" if value is None else str(value),
        "row": row,
        "column": column,
        "cell": _cell(row, column),
        "unit": None,
        "amount_type": amount_type,
    }


def _result_summary(issues: list[QcIssue]) -> str:
    finding_count = sum(1 for issue in issues if issue.severity != Severity.PASS)
    if finding_count:
        return f"触发 finding {finding_count} 条。"
    return "未触发 finding。"


def _rows_location(rows: list[int | None]) -> str | None:
    clean = _clean_ints(rows)
    if not clean:
        return None
    return "行 " + ", ".join(str(row) for row in clean[:12])


def _clean_ints(values: list[int | None]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result[:12]


def _cell(row: int | None, column: int | None) -> str | None:
    if row is None or column is None:
        return None
    return f"{_column_letter(column)}{row}"


def _column_letter(column: int) -> str:
    letters = ""
    while column > 0:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters

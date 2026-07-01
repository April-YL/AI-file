from __future__ import annotations

from collections.abc import Iterable

from ingest.lead_sheet import LeadSheetDataset
from rules.lead_common import (
    GAM_TT_RATIO_BANDS,
    cra_tier,
    effective_overall_threshold,
    field_values,
    movement_amount_for_row,
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
                section=_section_for_data_insufficient_rule(rule_id),
                location=None,
                matched_keywords=[block.anchor_text for block in lead.blocks if block.anchor_text],
                matched_rows=[],
                matched_columns=[],
                key_columns=_required_keys_for_rule(rule_id),
                values_read=[],
                missing_data=[reason],
            )
        ],
        check_logic="本规则依赖 Lead Sheet 中已识别的资料区；当 Lead 资料识别质量不足时，仅记录未执行原因，不读取或推断底稿值。",
        expected_result="Lead Sheet 应能稳定识别本规则所需资料后，才执行本规则。",
        actual_result=f"本次未执行该规则：{reason}",
        result_summary="资料不足，未执行本规则。",
    )


def build_lead_movement_rows_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    missing = []
    if not lead.movement_rows:
        missing.append("Lead 两期引导主表账户行")
    if not lead.movement_bindings:
        missing.append("Lead 两期引导主表金额列")
    return _observation(
        checked_data=[_movement_checked_data(lead, missing_data=missing)],
        check_logic="读取 Lead 两期引导主表，检查原值、累计折旧、减值准备、净值等核心账户行，以及索引号、期末审定数、上期审定数等核心列是否可识别并已填写。",
        expected_result="Lead 两期引导主表应包含核心账户行和核心列；除净值行可由前三行勾稽外，核心账户行应能追溯到对应索引号和金额列。",
        actual_result=f"本次识别到 {len(lead.movement_rows)} 行 movement 数据、{len(lead.movement_bindings)} 个金额列绑定。",
        result_summary=_result_summary(issues),
    )


def build_lead_movement_consistency_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    return _observation(
        checked_data=[_movement_checked_data(lead)],
        check_logic="逐行读取 Lead 两期引导主表的上期审定数、本期审定数和变动金额，核对“本期审定数 - 上期审定数”是否与表内变动金额一致。",
        expected_result="每个账户行的变动金额应与本期审定数减上期审定数一致，仅允许金额尾差。",
        actual_result=f"本次对 {len(lead.movement_rows)} 行 movement 数据执行金额自洽检查。",
        result_summary=_result_summary(issues),
    )


def build_lead_movement_notes_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    return _observation(
        checked_data=[_movement_checked_data(lead, key_columns=[
            "account_label",
            "investigate_quantitative",
            "investigate_qualitative",
            "notes",
        ])],
        check_logic="读取 Lead 主表定量调查、定性调查和 Notes 列；当调查标记为“是”时，检查对应账户行是否填写 Notes。",
        expected_result="凡被标记为需要调查的 Lead 主表行，均应填写 Notes 或可追溯的说明引用。",
        actual_result=f"本次读取 {len(lead.movement_rows)} 行 movement 数据中的调查标记和 Notes 字段。",
        result_summary=_result_summary(issues),
    )


def build_lead_check_with_a3_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    cw = lead.check_with_a3
    missing = [] if cw else ["Check with A3 / Diff / Notes 区"]
    return _observation(
        checked_data=[
            _checked_data(
                sheet=lead.source_sheet,
                section="K.00 Lead Check with A3 / Diff",
                location=_rows_location([
                    cw.check_source_row if cw else None,
                    cw.diff_source_row if cw else None,
                    cw.notes_source_row if cw else None,
                ]),
                matched_keywords=["Check with A3", "Diff", "Notes"],
                matched_rows=[
                    cw.check_source_row if cw else None,
                    cw.diff_source_row if cw else None,
                    cw.notes_source_row if cw else None,
                ],
                matched_columns=[],
                key_columns=["account_label", "movement_value", "a3_value", "diff_value", "notes"],
                values_read=_check_with_a3_values(cw),
                missing_data=missing,
            )
        ],
        check_logic="读取 Lead 主表末尾的 Check with A3、Diff 和 Notes 区，重点核对净值行 Lead 金额、A3 金额和 Diff 是否一致，重大差异是否有说明。",
        expected_result="净值行 Diff 应为零或仅为允许尾差；重大非零 Diff 应在 Notes 中说明。",
        actual_result=f"本次识别到 {len(cw.lines) if cw else 0} 条 Check with A3 对齐明细。",
        result_summary=_result_summary(issues),
    )


def build_unexpected_movement_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    return _observation(
        checked_data=[
            _movement_checked_data(lead, key_columns=[
                "account_label",
                "movement_amount",
                "movement_pct",
                "investigate_quantitative",
                "investigate_qualitative",
                "notes",
            ]),
            _volatility_checked_data(lead),
            _fluctuation_notes_checked_data(lead),
        ],
        check_logic="读取 Lead 波动金额、波动比例门槛，以及主表各账户行的变动金额、变动比例和调查标记；当超过门槛或被标记需调查时，检查波动说明是否为空或过于笼统。",
        expected_result="超过波动门槛或被标记需调查的项目，应有具体波动说明，不能仅写无异常波动等空泛结论。",
        actual_result=f"本次读取 {len(lead.movement_rows)} 行 movement 数据，并检查波动说明区是否支持异常波动调查。",
        result_summary=_result_summary(issues),
    )


def build_lead_fluctuation_notes_refs_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    return _observation(
        checked_data=[
            _movement_checked_data(lead, key_columns=["account_label", "notes"]),
            _fluctuation_notes_checked_data(lead),
        ],
        check_logic="读取 Lead 主表 Notes 引用和波动说明区正文，检查主表引用的 Notes 编号是否能在波动说明区找到对应说明，并关注说明区是否存在无法回连主表的编号。",
        expected_result="Lead 主表 Notes 引用应与波动说明区编号互相对应，需要调查的主表行应能追溯到具体说明。",
        actual_result=f"本次读取 {len(lead.movement_rows)} 行主表 Notes，并读取波动说明区文本长度 {len(lead.fluctuation_notes or '')}。",
        result_summary=_result_summary(issues),
    )


def build_lead_expectation_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
    *,
    rule_id: str,
) -> dict:
    issues = list(issues)
    logic = {
        "lead_expectation_analysis": "读取 Lead 预期分析区和波动门槛，检查是否识别到账户变更预期，以及波动金额/比例门槛是否可读取。",
        "lead_expectation_basis_present": "读取 Lead 预期分析行，检查预期说明是否包含形成依据，而不是仅有空白、无异常、合理等简短结论。",
        "lead_expectation_vs_movement_review": "读取 Lead 预期分析、波动门槛和 movement 实际变动；当预期写明无重大变化但实际波动超过门槛时，提示人工复核。",
    }.get(rule_id, "读取 Lead 预期分析相关资料，记录本规则实际检查依据。")
    expected = {
        "lead_expectation_analysis": "Lead 应能识别预期分析区、账户变更预期和波动门槛。",
        "lead_expectation_basis_present": "预期分析应说明判断依据，不应只有笼统结论。",
        "lead_expectation_vs_movement_review": "预期分析口径应与实际 movement 波动保持一致；若不一致，应由人工复核说明。",
    }.get(rule_id, "Lead 预期分析资料应支持本规则检查。")
    return _observation(
        checked_data=[
            _expectation_checked_data(lead),
            _volatility_checked_data(lead),
            _movement_checked_data(lead, key_columns=["account_label", "movement_amount", "movement_pct"]),
        ],
        check_logic=logic,
        expected_result=expected,
        actual_result=f"本次识别到 {len(lead.expectations)} 行预期分析、{len(lead.movement_rows)} 行 movement 数据。",
        result_summary=_result_summary(issues),
    )


def build_lead_adjustment_observation(
    lead: LeadSheetDataset,
    issues: Iterable[QcIssue],
) -> dict:
    issues = list(issues)
    return _observation(
        checked_data=[
            _movement_checked_data(lead, key_columns=[
                "account_label",
                "book_adjustment",
                "audit_adjustment",
            ]),
            _adjustment_checked_data(lead),
        ],
        check_logic="读取 Lead 主表账表调整、审计调整列，以及 Lead 调整事项汇总表；检查主表调整金额与调整汇总记录是否能对应。",
        expected_result="如 Lead 主表存在调整金额，应能在调整事项汇总表找到对应记录；如汇总表存在调整记录，也应能回连主表相关调整列。",
        actual_result=f"本次识别到 {len(lead.adjustment_rows)} 行调整事项汇总记录，并读取 {len(lead.movement_rows)} 行主表调整列。",
        result_summary=_result_summary(issues),
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


def _movement_checked_data(
    lead: LeadSheetDataset,
    *,
    key_columns: list[str] | None = None,
    missing_data: list[str] | None = None,
) -> dict:
    rows = [row.source_row for row in lead.movement_rows]
    columns = [binding.column_index for binding in lead.movement_bindings]
    keys = key_columns or [
        "account_label",
        "sheet_ref",
        "py_audited",
        "audited_ending",
        "movement_amount",
        "movement_pct",
        "book_balance",
    ]
    missing = list(missing_data or [])
    if not lead.movement_rows:
        missing.append("Lead 两期引导主表账户行")
    if not lead.movement_bindings:
        missing.append("Lead 两期引导主表金额列")
    return _checked_data(
        sheet=lead.source_sheet,
        section="K.00 Lead 两期引导主表",
        location=_rows_location(rows),
        matched_keywords=[row.account_label for row in lead.movement_rows],
        matched_rows=rows,
        matched_columns=columns,
        key_columns=keys,
        values_read=_movement_values(lead, keys),
        missing_data=missing,
    )


def _movement_values(lead: LeadSheetDataset, keys: list[str]) -> list[dict]:
    values: list[dict] = []
    for row in lead.movement_rows:
        for key in keys:
            if key == "account_label":
                values.append(
                    _value_read(
                        label="账户行",
                        value=row.account_label,
                        row=row.source_row,
                        column=None,
                        amount_type="Lead movement",
                    )
                )
                continue
            if key == "sheet_ref":
                values.append(
                    _value_read(
                        label=f"{row.account_label} 索引号",
                        value=row.sheet_ref,
                        row=row.source_row,
                        column=None,
                        amount_type="Lead movement",
                    )
                )
                continue
            if key == "computed_movement":
                values.append(
                    _value_read(
                        label=f"{row.account_label} 计算变动额",
                        value=movement_amount_for_row(row.values),
                        row=row.source_row,
                        column=None,
                        amount_type="Lead movement",
                    )
                )
                continue
            if key in row.values:
                values.append(
                    _value_read(
                        label=f"{row.account_label} {_movement_role_label(key)}",
                        value=row.values.get(key),
                        row=row.source_row,
                        column=_column_for_role(lead, key),
                        amount_type="Lead movement",
                    )
                )
    return values[:20]


def _check_with_a3_values(cw) -> list[dict]:
    if cw is None:
        return []
    values: list[dict] = []
    for line in cw.lines:
        values.extend(
            [
                _value_read(
                    label=f"{line.account_label} Lead金额",
                    value=line.movement_value,
                    row=cw.check_source_row,
                    column=None,
                    amount_type="Lead Check with A3",
                ),
                _value_read(
                    label=f"{line.account_label} A3金额",
                    value=line.a3_value,
                    row=cw.check_source_row,
                    column=None,
                    amount_type="Lead Check with A3",
                ),
                _value_read(
                    label=f"{line.account_label} Diff",
                    value=line.diff_value,
                    row=cw.diff_source_row,
                    column=None,
                    amount_type="Lead Check with A3",
                ),
            ]
        )
    if cw.notes_text:
        values.append(
            _value_read(
                label="Check with A3 Notes",
                value=cw.notes_text,
                row=cw.notes_source_row,
                column=None,
                amount_type="Lead Check with A3",
            )
        )
    return values[:20]


def _volatility_checked_data(lead: LeadSheetDataset) -> dict:
    vol = lead.volatility
    return _checked_data(
        sheet=lead.source_sheet,
        section="K.00 Lead 波动门槛",
        location=_rows_location([
            vol.source_row_amount if vol else None,
            vol.source_row_percent if vol else None,
        ]),
        matched_keywords=["波动幅度", "金额", "比例"],
        matched_rows=[
            vol.source_row_amount if vol else None,
            vol.source_row_percent if vol else None,
        ],
        matched_columns=[],
        key_columns=["volatility_amount", "volatility_percent"],
        values_read=[
            _value_read(
                label="波动金额门槛",
                value=vol.amount if vol else None,
                row=vol.source_row_amount if vol else None,
                column=None,
                amount_type="Lead 波动门槛",
            ),
            _value_read(
                label="波动比例门槛",
                value=vol.percent if vol else None,
                row=vol.source_row_percent if vol else None,
                column=None,
                amount_type="Lead 波动门槛",
            ),
        ] if vol else [],
        missing_data=[] if vol else ["波动金额/比例门槛"],
    )


def _fluctuation_notes_checked_data(lead: LeadSheetDataset) -> dict:
    block = _lead_block(lead, "fluctuation_notes")
    rows = []
    if block is not None:
        rows = [block.start_row, block.end_row]
    return _checked_data(
        sheet=lead.source_sheet,
        section="K.00 Lead 波动说明区",
        location=_rows_location(rows),
        matched_keywords=[block.anchor_text] if block and block.anchor_text else ["波动说明"],
        matched_rows=rows,
        matched_columns=[],
        key_columns=["fluctuation_notes"],
        values_read=[
            _value_read(
                label="波动说明",
                value=lead.fluctuation_notes,
                row=block.start_row if block else None,
                column=None,
                amount_type="Lead 波动说明",
            )
        ] if lead.fluctuation_notes else [],
        missing_data=[] if lead.fluctuation_notes else ["波动说明区正文"],
    )


def _expectation_checked_data(lead: LeadSheetDataset) -> dict:
    rows = [row.source_row for row in lead.expectations]
    values: list[dict] = []
    for row in lead.expectations:
        values.extend(
            [
                _value_read(
                    label="账户变更",
                    value=row.account_change,
                    row=row.source_row,
                    column=None,
                    amount_type="Lead 预期分析",
                ),
                _value_read(
                    label=f"{row.account_change} 预期",
                    value=row.expectation,
                    row=row.source_row,
                    column=None,
                    amount_type="Lead 预期分析",
                ),
            ]
        )
    return _checked_data(
        sheet=lead.source_sheet,
        section="K.00 Lead 预期分析区",
        location=_rows_location(rows),
        matched_keywords=[row.account_change for row in lead.expectations],
        matched_rows=rows,
        matched_columns=[],
        key_columns=["account_change", "expectation"],
        values_read=values[:20],
        missing_data=[] if lead.expectations else ["预期分析账户变更行"],
    )


def _adjustment_checked_data(lead: LeadSheetDataset) -> dict:
    values: list[dict] = []
    for row in lead.adjustment_rows:
        values.append(
            _value_read(
                label=f"调整汇总第 {row.source_row} 行",
                value=" | ".join(str(cell) for cell in row.raw_cells if cell),
                row=row.source_row,
                column=None,
                amount_type="Lead 调整汇总",
            )
        )
    return _checked_data(
        sheet=lead.source_sheet,
        section="K.00 Lead 调整事项汇总表",
        location=_rows_location([row.source_row for row in lead.adjustment_rows]),
        matched_keywords=[row.adjustment_type for row in lead.adjustment_rows if row.adjustment_type],
        matched_rows=[row.source_row for row in lead.adjustment_rows],
        matched_columns=[],
        key_columns=["adjustment_type", "raw_cells"],
        values_read=values[:20],
        missing_data=[] if lead.adjustment_rows else ["调整事项汇总记录"],
    )


def _column_for_role(lead: LeadSheetDataset, role: str) -> int | None:
    for binding in lead.movement_bindings:
        if binding.role == role:
            return binding.column_index
    return None


def _movement_role_label(role: str) -> str:
    return {
        "py_audited": "上期审定数",
        "audited_ending": "本期审定数",
        "movement_amount": "变动金额",
        "movement_pct": "变动比例",
        "book_balance": "账面价值",
        "investigate_quantitative": "定量调查",
        "investigate_qualitative": "定性调查",
        "notes": "Notes",
        "book_adjustment": "账表调整",
        "audit_adjustment": "审计调整",
    }.get(role, role)


def _lead_block(lead: LeadSheetDataset, kind_value: str):
    for block in lead.blocks:
        if getattr(block.kind, "value", None) == kind_value:
            return block
    return None


def _section_for_data_insufficient_rule(rule_id: str) -> str:
    if rule_id in {
        "lead_movement_rows_complete",
        "lead_movement_consistency",
        "lead_movement_notes_required",
        "lead_check_with_a3_row",
        "unexpected_movement_investigation",
        "lead_fluctuation_notes_refs",
        "lead_rollforward_tb_reconciliation",
    }:
        return "K.00 Lead movement / 勾稽规则执行前置条件"
    if rule_id in {
        "lead_expectation_analysis",
        "lead_expectation_basis_present",
        "lead_expectation_vs_movement_review",
    }:
        return "K.00 Lead 预期分析规则执行前置条件"
    if rule_id == "lead_adjustment_internal_consistency":
        return "K.00 Lead 调整事项规则执行前置条件"
    return "K.00 Lead Sheet 参数类规则执行前置条件"


def _required_keys_for_rule(rule_id: str) -> list[str]:
    return {
        "lead_analysis_date_after_period_end": ["period_end", "analysis_date"],
        "materiality_consistency": ["pm", "te", "sad"],
        "risk_threshold_consistency": ["assertion", "cra", "tt", "tt_overall"],
        "lead_tt_overall_min": ["tt", "tt_overall"],
        "lead_tt_gam_range": ["te", "cra", "tt"],
        "lead_volatility_threshold_link": ["volatility_amount", "te", "tt_overall"],
        "lead_movement_rows_complete": ["account_label", "sheet_ref", "py_audited", "audited_ending"],
        "lead_movement_consistency": ["py_audited", "audited_ending", "movement_amount"],
        "lead_movement_notes_required": ["investigate_quantitative", "investigate_qualitative", "notes"],
        "lead_check_with_a3_row": ["check_with_a3", "diff", "notes"],
        "unexpected_movement_investigation": ["volatility_amount", "volatility_percent", "movement_amount", "movement_pct", "notes"],
        "lead_fluctuation_notes_refs": ["movement_notes", "fluctuation_notes"],
        "lead_expectation_analysis": ["expectation", "volatility_amount", "volatility_percent"],
        "lead_expectation_basis_present": ["expectation"],
        "lead_expectation_vs_movement_review": ["expectation", "movement_amount", "movement_pct"],
        "lead_adjustment_internal_consistency": ["book_adjustment", "audit_adjustment", "adjustment_summary"],
        "lead_rollforward_tb_reconciliation": ["lead_movement", "k01_rollforward_totals"],
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

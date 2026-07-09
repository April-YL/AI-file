"""质检点执行台账数据合并组件。

本模块只做 UI 展示前的数据整理，不修改 report / issue / ledger 原始数据。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

STATUS_LABELS: dict[str, str] = {
    "EXECUTED": "已执行",
    "DATA_INSUFFICIENT": "数据不足未执行",
    "NOT_APPLICABLE": "暂不适用",
    "NOT_TRIGGERED_BY_CONTEXT": "未识别到底稿",
    "LLM_DISABLED": "LLM 未开启",
    "DELIVERY_CONTEXT_MISSING": "缺少交付阶段",
    "NOT_WIRED": "待接入",
    "UNKNOWN": "待确认",
}

MODULE_LABELS: dict[str, str] = {
    "PSP": "全局 / 交付检查",
    "SUMMARY": "全局 / 交付检查",
    "GLOBAL": "全局 / 交付检查",
    "Lead": "K.00 Lead",
    "K.00": "K.00 Lead",
    "K.01": "K.01 后推",
    "FA list": "FA list",
    "FA_LIST": "FA list",
    "K.02": "K.02.1 新增测试",
    "K.02.1": "K.02.1 新增测试",
    "K.02.2": "K.02.2 处置测试",
    "K.03": "K.03 折旧测试",
    "K03": "K.03 折旧测试",
    "K.03.1": "K.03.1 SAP",
    "K.03.2": "K.03.2 折旧测试",
    "K.03.3": "K.03.3 折旧政策复核",
    "UNKNOWN": "其他",
}

PROCEDURE_ORDER: tuple[str, ...] = (
    "全局 / 交付检查",
    "K.00 Lead",
    "K.01 后推",
    "FA list",
    "K.02.1 新增测试",
    "K.02.2 处置测试",
    "K.03 折旧测试",
    "K.03.1 SAP",
    "K.03.2 折旧测试",
    "K.03.3 折旧政策复核",
    "其他",
)

NOT_EXECUTED_WITH_REASON_STATUSES: set[str] = {
    "DATA_INSUFFICIENT",
    "NOT_APPLICABLE",
    "LLM_DISABLED",
    "DELIVERY_CONTEXT_MISSING",
    "NOT_TRIGGERED_BY_CONTEXT",
    "NOT_WIRED",
}


def build_execution_ledger_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """构建完整质检点执行台账行。

    主骨架只来自 ``rule_execution_matrix``。``execution_ledger`` 和 ``issues``
    只补充执行事实、取数来源、判断说明和异常记录，不新增质检点行。
    """

    matrix = data.get("rule_execution_matrix")
    if not isinstance(matrix, list) or not matrix:
        return []

    ledger_by_rule = _ledger_by_rule(data.get("execution_ledger"))
    issues_by_rule = _issues_by_rule(data.get("issues"))

    rows: list[dict[str, Any]] = []
    for entry in matrix:
        if not isinstance(entry, dict):
            continue
        rule_id = str(entry.get("rule_id") or "")
        ledger_item = ledger_by_rule.get(rule_id, {})
        issues = issues_by_rule.get(rule_id, [])
        observation = ledger_item.get("observation") if isinstance(ledger_item, dict) else None
        status = _status(entry, ledger_item)
        issue_count = len(issues)
        recorded_count = _count_value(entry.get("finding_count"))
        if recorded_count is None:
            recorded_count = _count_value(ledger_item.get("finding_count"))
        display_count = issue_count if issue_count else (recorded_count or 0)

        rows.append(
            {
                "程序": _module_label(entry.get("module") or entry.get("procedure_code")),
                "质检点ID": entry.get("rule_code") or entry.get("dict_code") or rule_id or "—",
                "质检点编号": entry.get("rule_code") or entry.get("dict_code") or rule_id or "—",
                "质检点名称": entry.get("rule_name") or rule_id or "规则检查",
                "执行状态": _status_label(entry, status),
                "未执行原因": _non_execution_reason(entry, ledger_item, status),
                "执行结果": _execution_result(entry, ledger_item, status, display_count),
                "异常记录": _exception_display(display_count),
                "取数来源": _source_summary(entry, observation),
                "证据摘要": _evidence_summary(observation, issues),
                "取数与判断说明": _trace_hint(observation),
                "异常摘要": _issue_summary(issues),
                "规则编号": entry.get("rule_code") or entry.get("dict_code") or rule_id or "—",
                "规则名称": entry.get("rule_name") or rule_id or "规则检查",
                "异常数": _exception_display(display_count),
                "取数来源摘要": _source_summary(entry, observation),
                "_status": status,
                "_rule_id": rule_id,
                "_matrix_entry": entry,
                "_ledger_item": ledger_item,
                "_issues": issues,
            }
        )

    rows.sort(key=_sort_key)
    return rows


def build_execution_scope_summary(data: dict[str, Any]) -> dict[str, Any]:
    """统计复核结果页的执行范围卡片，并保证统计口径可闭合。"""

    rows = build_execution_ledger_rows(data)
    matrix = data.get("rule_execution_matrix")
    matrix_total = len(matrix) if isinstance(matrix, list) else len(rows)

    executed = 0
    not_executed_with_reason = 0
    pending_record = 0
    for row in rows:
        status = str(row.get("_status") or "").upper()
        if status == "EXECUTED":
            executed += 1
        elif status in NOT_EXECUTED_WITH_REASON_STATUSES:
            not_executed_with_reason += 1
        else:
            pending_record += 1

    summary = {
        "total": len(rows),
        "matrix_total": matrix_total,
        "ledger_rows": len(rows),
        "executed": executed,
        "not_executed_with_reason": not_executed_with_reason,
        "pending_record": pending_record,
    }
    summary["errors"] = validate_execution_scope_summary(summary)
    summary["is_valid"] = not summary["errors"]
    return summary


def validate_execution_scope_summary(summary: dict[str, Any]) -> list[str]:
    """校验执行范围统计是否与完整质检点清单闭合。"""

    errors: list[str] = []
    total = int(summary.get("total") or 0)
    matrix_total = int(summary.get("matrix_total") or 0)
    ledger_rows = int(summary.get("ledger_rows") or 0)
    executed = int(summary.get("executed") or 0)
    not_executed_with_reason = int(summary.get("not_executed_with_reason") or 0)
    pending_record = int(summary.get("pending_record") or 0)

    if ledger_rows != matrix_total:
        errors.append("台账行数与完整质检点清单不一致")
    if total != executed + not_executed_with_reason + pending_record:
        errors.append("执行范围统计未闭合")
    return errors


def render_execution_ledger_table(data: dict[str, Any], *, key_prefix: str = "ledger") -> None:
    """渲染当前运行的完整质检点执行台账。"""

    import streamlit as st

    rows = build_execution_ledger_rows(data)
    matrix = data.get("rule_execution_matrix")
    if not isinstance(matrix, list) or not matrix:
        st.info("本次报告未包含完整质检点清单，无法展示完整执行台账。")
        return
    if len(rows) != len(matrix):
        st.error("质检点执行台账行数与完整质检点清单不一致，请先复核数据合并逻辑。")
        return

    status_options = ["全部状态"] + list(
        dict.fromkeys(str(row.get("执行状态") or "待确认") for row in rows)
    )
    procedure_options = ["全部程序"] + list(
        dict.fromkeys(str(row.get("程序") or "其他") for row in rows)
    )

    col1, col2, col3 = st.columns([1.3, 1.3, 2.2])
    with col1:
        procedure_filter = st.selectbox(
            "程序",
            procedure_options,
            key=f"{key_prefix}_procedure",
            label_visibility="collapsed",
        )
    with col2:
        status_filter = st.selectbox(
            "执行状态",
            status_options,
            key=f"{key_prefix}_status",
            label_visibility="collapsed",
        )
    with col3:
        search = st.text_input(
            "搜索",
            placeholder="搜索质检点编号、名称、取数来源或执行结果...",
            key=f"{key_prefix}_search",
            label_visibility="collapsed",
        )

    display_rows = rows
    if procedure_filter != "全部程序":
        display_rows = [row for row in display_rows if row.get("程序") == procedure_filter]
    if status_filter != "全部状态":
        display_rows = [row for row in display_rows if row.get("执行状态") == status_filter]
    if search:
        needle = search.lower()
        display_rows = [
            row
            for row in display_rows
            if needle
            in " ".join(
                str(row.get(key) or "")
                for key in (
                    "质检点编号",
                    "质检点ID",
                    "质检点名称",
                    "取数来源",
                    "异常摘要",
                )
            ).lower()
        ]

    st.caption(f"显示 {len(display_rows)} 条（共 {len(rows)} 条质检点）")
    visible_columns = [
        "程序",
        "质检点ID",
        "质检点名称",
        "执行状态",
        "未执行原因",
        "异常记录",
        "取数来源",
        "证据摘要",
    ]
    st.markdown(
        """
        <style>
        div[data-testid="stDataFrame"] div[role="gridcell"][aria-colindex="8"] {
            color: #175cd3 !important;
            font-weight: 600 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    table_col, detail_col = st.columns([1.75, 1])
    with table_col:
        event = st.dataframe(
            [{column: _display_value(row.get(column)) for column in visible_columns} for row in display_rows],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"{key_prefix}_table",
        )

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    selected_row = None
    if selected_rows:
        selected_idx = selected_rows[0]
        if 0 <= selected_idx < len(display_rows):
            selected_row = display_rows[selected_idx]

    with detail_col:
        if selected_row:
            _render_row_detail(selected_row)
        else:
            st.info("选中左侧台账行后，在这里查看取数值、异常记录和判断说明。")


def _render_row_detail(row: dict[str, Any]) -> None:
    import streamlit as st

    ledger_item = row.get("_ledger_item")
    observation = ledger_item.get("observation") if isinstance(ledger_item, dict) else None
    issues = row.get("_issues") if isinstance(row.get("_issues"), list) else []
    st.markdown("**检查明细**")
    st.caption(f"{row.get('质检点编号', '—')} · {row.get('质检点名称', '规则检查')}")
    st.dataframe(
        [
            {"项目": "程序", "内容": _display_value(row.get("程序"))},
            {"项目": "执行状态", "内容": _display_value(row.get("执行状态"))},
            {"项目": "未执行原因", "内容": _display_value(row.get("未执行原因"))},
            {"项目": "异常记录", "内容": _display_value(row.get("异常记录"))},
        ],
        use_container_width=True,
        hide_index=True,
    )
    if issues:
        st.markdown("**异常记录**")
        st.write(row.get("异常摘要") or "无")
    if isinstance(observation, dict) and observation:
        _render_observation_detail(observation)
    if not observation and not issues:
        st.caption("本质检点暂无取数证据或异常记录。")


def _render_observation_detail(observation: dict[str, Any]) -> None:
    import streamlit as st

    evidence_rows = _evidence_rows_from_observation(observation)
    if evidence_rows:
        st.markdown("**取数证据**")
        st.dataframe(evidence_rows, use_container_width=True, hide_index=True)
    else:
        inputs = observation.get("inputs") or []
        if isinstance(inputs, list) and inputs:
            st.markdown("**依赖资料**")
            for item in inputs[:8]:
                if not isinstance(item, dict):
                    continue
                parts = [
                    str(item.get(key) or "")
                    for key in ("source_sheet", "section", "field")
                    if item.get(key)
                ]
                st.caption(" / ".join(parts) if parts else "—")

    missing_items = _missing_items_from_observation(observation)
    if missing_items:
        st.warning("缺失资料：" + "；".join(missing_items[:8]))

    for label, key in (
        ("检查逻辑", "check_logic"),
        ("判断标准", "expected_result"),
        ("实际结果", "actual_result"),
        ("执行结果", "result_summary"),
    ):
        text = str(observation.get(key) or "").strip()
        if text:
            st.markdown(f"**{label}**")
            st.write(text)


def _evidence_rows_from_observation(observation: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    checked_data = observation.get("checked_data") or []
    if not isinstance(checked_data, list):
        return rows
    for item in checked_data:
        if not isinstance(item, dict):
            continue
        sheet = _display_value(item.get("sheet"))
        section = _display_value(item.get("section"))
        values = item.get("values_read") or []
        if isinstance(values, list) and values:
            for value in values:
                if not isinstance(value, dict):
                    continue
                rows.append(
                    {
                        "sheet": sheet,
                        "section": section,
                        "cell": _display_value(value.get("cell")),
                        "row": _display_value(value.get("row")),
                        "label": _display_value(value.get("label")),
                        "value": _display_value(value.get("value")),
                    }
                )
        else:
            rows.append(
                {
                    "sheet": sheet,
                    "section": section,
                    "cell": _display_value(item.get("location")),
                    "row": "—",
                    "label": "检查位置",
                    "value": _display_value(item.get("location")),
                }
            )
    return rows


def _missing_items_from_observation(observation: dict[str, Any]) -> list[str]:
    out: list[str] = []
    checked_data = observation.get("checked_data") or []
    if not isinstance(checked_data, list):
        return out
    for item in checked_data:
        if not isinstance(item, dict):
            continue
        missing = item.get("missing_data") or []
        if isinstance(missing, list):
            out.extend(str(value) for value in missing if value)
    return out


def _ledger_by_rule(ledger: object) -> dict[str, dict[str, Any]]:
    if not isinstance(ledger, dict):
        return {}
    items = ledger.get("items")
    if not isinstance(items, list):
        return {}
    by_rule: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "")
        if rule_id and rule_id not in by_rule:
            by_rule[rule_id] = item
    return by_rule


def _issues_by_rule(issues: object) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not isinstance(issues, list):
        return grouped
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("severity") or "").upper() == "PASS":
            continue
        rule_id = str(issue.get("rule_id") or "")
        if rule_id:
            grouped[rule_id].append(issue)
    return grouped


def _status(entry: dict[str, Any], ledger_item: dict[str, Any]) -> str:
    status = str(entry.get("execution_status") or "").upper()
    if status:
        return status
    status = str(ledger_item.get("status") or "").upper()
    if status:
        return status
    if ledger_item.get("executed") is True:
        return "EXECUTED"
    return "UNKNOWN"


def _status_label(entry: dict[str, Any], status: str) -> str:
    label = str(entry.get("execution_status_label") or "").strip()
    return label or STATUS_LABELS.get(status, status or "待确认")


def _non_execution_reason(
    entry: dict[str, Any],
    ledger_item: dict[str, Any],
    status: str,
) -> str:
    if status == "EXECUTED":
        return "—"
    reason = str(entry.get("non_execution_reason") or "").strip()
    if not reason:
        reason = str(ledger_item.get("status_note") or "").strip()
    return reason or STATUS_LABELS.get(status, status or "待确认")


def _execution_result(
    entry: dict[str, Any],
    ledger_item: dict[str, Any],
    status: str,
    issue_count: int,
) -> str:
    observation = ledger_item.get("observation") if isinstance(ledger_item, dict) else None
    if isinstance(observation, dict):
        result = str(observation.get("result_summary") or "").strip()
        if result:
            return result
    result = str(entry.get("result_summary") or "").strip()
    if result:
        return result
    if status == "EXECUTED":
        return f"系统记录 {issue_count} 条规则提示" if issue_count else "规则已执行，未记录异常"
    reason = _non_execution_reason(entry, ledger_item, status)
    return reason if reason != "—" else STATUS_LABELS.get(status, "待确认")


def _exception_display(count: int) -> str:
    return f"{count} 条" if count else "无"


def _display_value(value: object) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    if not text or text.lower() == "none":
        return "—"
    return text


def _evidence_summary(observation: object, issues: list[dict[str, Any]]) -> str:
    if isinstance(observation, dict) and observation:
        return "查看详情"
    if issues:
        return "查看详情"
    return "—"


def _source_summary(entry: dict[str, Any], observation: object) -> str:
    if isinstance(observation, dict):
        sources = _source_locations_from_observation(observation)
        if sources:
            if len(sources) <= 2:
                return "；".join(sources)
            return "；".join(sources[:2]) + f"；等 {len(sources)} 处"
    source = str(entry.get("source_summary") or "").strip()
    if source and source != "—":
        return source
    return "未记录"


def _source_locations_from_observation(observation: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    checked_data = observation.get("checked_data") or []
    if isinstance(checked_data, list):
        for item in checked_data:
            if not isinstance(item, dict):
                continue
            sheet = _display_value(item.get("sheet"))
            location = _display_value(item.get("location"))
            if location != "—":
                sources.append(_join_sheet_location(sheet, location))
            values = item.get("values_read") or []
            if isinstance(values, list):
                for value in values:
                    if not isinstance(value, dict):
                        continue
                    cell = _display_value(value.get("cell"))
                    if cell != "—":
                        sources.append(_join_sheet_location(sheet, cell))
                    elif _display_value(value.get("row")) != "—":
                        sources.append(f"{sheet} / 行 {value.get('row')}")
            if location == "—" and not values:
                section = _display_value(item.get("section"))
                if section != "—":
                    sources.append(f"{sheet} / {section}")

    inputs = observation.get("inputs") or []
    if isinstance(inputs, list):
        for item in inputs:
            if not isinstance(item, dict):
                continue
            sheet = _display_value(item.get("source_sheet") or item.get("sheet"))
            section = _display_value(item.get("section"))
            field = _display_value(item.get("field"))
            parts = [part for part in (sheet, section, field) if part != "—"]
            if parts:
                sources.append(" / ".join(parts))

    deduped: list[str] = []
    for source in sources:
        if source and source != "—" and source not in deduped:
            deduped.append(source)
    return deduped


def _join_sheet_location(sheet: str, location: str) -> str:
    if sheet == "—":
        return location
    if "!" in location:
        return location
    return f"{sheet}!{location}"


def _trace_hint(observation: object) -> str:
    if not isinstance(observation, dict) or not observation:
        return "未记录取数与判断说明"
    if "checked_data" in observation:
        return "可查看系统取数证据"
    if "path" in observation or "inputs" in observation or "checks" in observation:
        return "可查看基础执行说明"
    return "已记录执行说明"


def _issue_summary(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "无"
    messages = [str(item.get("message") or "").strip() for item in issues[:3]]
    messages = [message for message in messages if message]
    return "；".join(messages) if messages else f"{len(issues)} 条规则提示"


def _module_label(value: object) -> str:
    raw = str(value or "").strip()
    return MODULE_LABELS.get(raw, raw or "其他")


def _count_value(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    procedure = str(row.get("程序") or "")
    try:
        procedure_rank = PROCEDURE_ORDER.index(procedure)
    except ValueError:
        procedure_rank = len(PROCEDURE_ORDER)
    return (
        procedure_rank,
        str(row.get("质检点编号") or ""),
        str(row.get("_rule_id") or ""),
    )

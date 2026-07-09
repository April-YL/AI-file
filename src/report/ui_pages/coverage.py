# [P0-1] 检查范围页 — 全量规则覆盖 + 每行展开 trace + 双格式 observation
# 以旧 _render_coverage_diagnostics 为功能基准，功能完整性 ≥ 旧 UI
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 检查范围（全量规则覆盖 + 可追溯）。

骨架 = rule_execution_matrix（所有已注册规则）。
已执行行 = execution_ledger observation trace 嵌入。
"""

from __future__ import annotations

import streamlit as st

from report.ui_components.execution_ledger_table import (
    build_execution_ledger_rows,
    PROCEDURE_ORDER,
)
from report.ui_components.cards import render_section_title, render_info_banner
from report.ui_state.run_store import get_latest_run, list_runs, get_run

_STATUS_LABELS: dict[str, str] = {
    "EXECUTED": "已执行",
    "DATA_INSUFFICIENT": "数据不足",
    "NOT_APPLICABLE": "不适用",
    "NOT_TRIGGERED_BY_CONTEXT": "未识别到底稿",
    "LLM_DISABLED": "LLM 未开启",
    "DELIVERY_CONTEXT_MISSING": "缺少交付阶段",
    "NOT_WIRED": "待接入",
    "UNKNOWN": "待确认",
}

_MODULE_MAP: dict[str, str] = {
    "PSP": "全局 / 交付检查",
    "Lead": "K.00 Lead",
    "K.00": "K.00 Lead",
    "K.01": "K.01 后推",
    "FA list": "FA list",
    "FA_LIST": "FA list",
    "K.02.1": "K.02.1 新增测试",
    "K.02.2": "K.02.2 处置测试",
    "K.03": "K.03 折旧测试",
    "K03": "K.03 折旧测试",
    "K.03.1": "K.03.1 SAP",
    "K.03.2": "K.03.2 折旧测试",
    "K.03.3": "K.03.3 折旧政策复核",
    "UNKNOWN": "其他",
}

_TRACE_DISPLAY_COLS = [
    "程序", "质检点编号", "质检点名称", "执行状态",
    "未执行原因", "异常记录", "取数来源", "取数与判断说明",
]


def _build_rows(matrix: list[dict], ledger_by_rule: dict[str, dict]) -> list[dict]:
    """兼容旧 UI 对比测试：复用统一台账合并逻辑，不另起展示口径。"""
    data = {
        "rule_execution_matrix": matrix,
        "execution_ledger": {"items": list(ledger_by_rule.values())},
        "issues": [],
    }
    return build_execution_ledger_rows(data)


def render_coverage() -> None:
    """渲染检查范围页（全量规则 + 逐行 trace）。"""
    render_section_title("检查范围", "全部已注册规则 × 本次执行结果。已执行规则可逐行展开查看取数与判断过程。")
    render_info_banner(
        "本页为<strong>只读</strong>展示。"
        "执行状态仅表示系统本次是否运行该规则流程，<strong>不代表审计判断</strong>。"
        "未执行不等于无待处理 Findings；异常记录以 Findings 明细为准。"
    )

    # ---- 运行选择器 ----
    runs = list_runs(limit=50)
    if not runs:
        st.info("暂无运行记录。请先执行一次复核。")
        return

    run_options = {r["id"]: f"{r.get('completed_at','')} · {r.get('source_filename','')} · {r.get('overall_severity','')}" for r in runs}
    default_run = runs[0]["id"]
    selected_run = st.selectbox(
        "查看运行", options=list(run_options.keys()),
        format_func=lambda x: run_options[x],
        index=0, key="coverage_run_sel",
    )

    run = get_run(selected_run)
    if not run or not run.get("data"):
        st.info("无法加载运行数据。")
        return

    data = run["data"]
    matrix = data.get("rule_execution_matrix")
    if not matrix or not isinstance(matrix, list):
        st.info("本次报告未包含完整质检点清单，无法展示检查范围。")
        return

    # ---- 构建行 ----
    rows = build_execution_ledger_rows(data)

    # ---- 统计 ----
    _render_stats(data, rows)

    # ---- 筛选 ----
    view_mode = st.radio("视图", ["仅看未执行/待补充", "全部规则"], horizontal=True, key="cov_view")
    if view_mode == "仅看未执行/待补充":
        display_rows = [r for r in rows if r["_status"] != "EXECUTED"]
    else:
        display_rows = rows

    st.caption(f"显示 {len(display_rows)} 条（共 {len(rows)} 条规则）")

    # ---- 按程序分组 ----
    grouped: dict[str, list[dict]] = {}
    for row in display_rows:
        grouped.setdefault(row["程序"], []).append(row)

    for proc in PROCEDURE_ORDER:
        group = grouped.get(proc, [])
        if not group:
            continue
        expanded = any(r.get("异常记录", "无") != "无" for r in group)
        with st.expander(f"{proc} · {len(group)} 条规则", expanded=expanded):
            st.dataframe(
                [{c: r[c] for c in _TRACE_DISPLAY_COLS} for r in group],
                use_container_width=True, hide_index=True,
            )
            # 每行展开 trace
            for row in group:
                _render_row_trace(row)


def _render_stats(data: dict, rows: list[dict]) -> None:
    """汇总统计卡片。"""
    summary = data.get("rule_execution_summary") or {}
    status_counts = summary.get("execution_status_counts") or {}
    total = summary.get("matrix_rule_count", len(rows))
    executed = status_counts.get("EXECUTED", 0)
    insufficient = status_counts.get("DATA_INSUFFICIENT", 0)
    na = status_counts.get("NOT_APPLICABLE", 0)
    not_triggered = status_counts.get("NOT_TRIGGERED_BY_CONTEXT", 0)

    cols = st.columns(6)
    with cols[0]: st.metric("全部规则", total)
    with cols[1]: st.metric("已执行", executed)
    with cols[2]: st.metric("数据不足", insufficient)
    with cols[3]: st.metric("不适用", na)
    with cols[4]: st.metric("未触发", not_triggered)
    with cols[5]: st.metric("待执行/未接入", total - executed)


def _render_row_trace(row: dict) -> None:
    """渲染单行的可展开 trace。"""
    status = row["_status"]
    ledger_item = row.get("_ledger_item", {})

    if status != "EXECUTED":
        return  # 未执行的不展开 trace

    obs = ledger_item.get("observation") if isinstance(ledger_item, dict) else None
    if not obs or not isinstance(obs, dict):
        return

    label = f"检查明细 · {row['质检点编号']} · {row['质检点名称'][:30]}"
    with st.expander(label, expanded=False):
        if "checked_data" in obs:
            _render_evidence_how(obs)
        elif "path" in obs and "inputs" in obs:
            _render_legacy_how(obs)
        else:
            st.info("该规则已执行，但未记录详细取数与判断说明。")


def _render_evidence_how(obs: dict) -> None:
    """证据级 observation 渲染。"""
    checked_data = obs.get("checked_data") or []
    for idx, item in enumerate(checked_data, 1):
        if not isinstance(item, dict):
            continue
        sheet = item.get("sheet", "—")
        section = item.get("section", "—")
        with st.expander(f"检查资料 {idx} · {sheet} / {section}", expanded=(idx == 1)):
            st.markdown(f"**工作表**：{sheet}  |  **区块**：{section}  |  **位置**：{item.get('location', '—')}")
            if item.get("key_columns"):
                st.caption(f"关键列：{'、'.join(str(v) for v in item['key_columns'])}")
            identified = item.get("identified_by") or {}
            if isinstance(identified, dict) and identified:
                kw = "、".join(str(v) for v in (identified.get("matched_keywords") or []))
                st.caption(f"命中：{identified.get('sheet_name', '—')} / {identified.get('section', '—')} / {kw}")
            values_read = item.get("values_read") or []
            if isinstance(values_read, list) and values_read:
                st.markdown("**实际读取值**")
                st.dataframe([{"标签": v.get("label"), "值": v.get("value"), "单元格": v.get("cell"), "行": v.get("row"), "列": v.get("column")} for v in values_read if isinstance(v, dict)], use_container_width=True, hide_index=True)
            missing = item.get("missing_data") or []
            if isinstance(missing, list) and missing:
                st.warning("缺失资料：" + "；".join(str(v) for v in missing))

    for label, key in [("检查逻辑", "check_logic"), ("判断标准", "expected_result"), ("实际结果", "actual_result"), ("执行结果", "result_summary")]:
        text = str(obs.get(key) or "").strip()
        if text:
            st.markdown(f"**{label}**")
            st.write(text)


def _render_legacy_how(obs: dict) -> None:
    """旧版 observation 渲染。"""
    st.info("该规则已记录基础执行说明，但尚未补充证据级执行说明。")

    path = obs.get("path", "—")
    path_label = {"primary": "主路径", "fallback": "兜底路径", "alternative": "替代路径", "skipped": "已跳过", "data_insufficient": "数据不足", "not_applicable": "暂不适用"}.get(path, path)

    inputs = obs.get("inputs") or []
    input_texts = []
    for inp in inputs[:8]:
        if not isinstance(inp, dict):
            continue
        parts = [str(inp.get(k) or "") for k in ("source_sheet", "section", "field") if inp.get(k)]
        input_texts.append(" / ".join(parts) if parts else "—")

    checks = obs.get("checks") or []
    check_texts = []
    for ch in checks[:8]:
        if not isinstance(ch, dict):
            continue
        result_label = {"passed": "未触发规则提示", "triggered": "触发规则提示", "not_applicable": "不适用", "data_insufficient": "数据不足"}.get(ch.get("result", ""), ch.get("result", ""))
        parts = [str(ch.get(k) or "") for k in ("name", "left_label", "operator", "right_label") if ch.get(k)]
        check_texts.append(f"{' '.join(parts)} → {result_label}" if parts else "—")

    st.markdown(f"**检查方式**：{path_label}")
    if input_texts:
        st.markdown("**依赖资料**")
        for t in input_texts:
            st.markdown(f"- {t}")
    if check_texts:
        st.markdown("**检查摘要**")
        for t in check_texts:
            st.markdown(f"- {t}")

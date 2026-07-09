# [阶段一] UI 组件 — 可交互 Findings 表格
# 从 ui_app.py 的 _findings_row + 筛选逻辑迁移
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — Findings 交互浏览器。

提供筛选、排序、搜索、行展开详情的能力。
"""

from __future__ import annotations

import streamlit as st
from openpyxl.utils import get_column_letter

from report.ui_components.cards import render_severity_badge

# ---- 程序标签 ----
_PROCEDURE_LABELS: dict[str, str] = {
    "GLOBAL": "全局 / 交付检查",
    "SUMMARY": "全局 / 交付检查",
    "K.00": "K.00 Lead",
    "K.01": "K.01 后推",
    "FA_LIST": "FA list",
    "K.02.1": "K.02.1 新增测试",
    "K.02.2": "K.02.2 处置测试",
    "K.03.1": "K.03.1 SAP",
    "K.03.2": "K.03.2 折旧测试",
    "K.03.3": "K.03.3 折旧政策复核",
}

# ---- UI 优先级分类 ----
_HIGH_PRIORITY_RULE_IDS = frozenset({
    "psp_completion", "materiality_consistency", "risk_threshold_consistency",
    "lead_check_with_a3_row", "lead_rollforward_tb_reconciliation",
    "rollforward_difference_over_sad", "rollforward_fa_list_reconciliation",
    "rollforward_depreciation_pl_reconciliation", "addition_rollforward_reconciliation",
    "addition_sample_pool_purchase_amount_match", "disposal_rollforward_reconciliation",
    "disposal_summary_reconciliation", "disposal_sample_pool_amount_match",
    "k03_policy_change_without_explanation",
})

_MANUAL_KEYWORDS = (
    "semantic", "llm", "review", "manual",
    "人工", "复核", "判断", "语义", "解释", "说明是否充分", "证据充分性", "cra",
)

_BY_ITEM_RULE_PREFIX = "k03_tod_by_item_"


def _worst_severity(items: list[dict]) -> str:
    rank = {"FAIL": 4, "NEED_REVIEW": 3, "WARN": 2, "PASS": 1}
    severities = [i.get("severity", "PASS") for i in items]
    if not severities:
        return "PASS"
    return max(severities, key=lambda s: rank.get(s, 0))


def _finding_issues(data_or_issues) -> list[dict]:
    """兼容：接受 QcReport dict 或直接 issues list。"""
    if isinstance(data_or_issues, list):
        return [i for i in data_or_issues if i.get("severity") != "PASS"]
    return [i for i in data_or_issues.get("issues", []) if i.get("severity") != "PASS"]


def _finding_count(data_or_issues) -> int:
    return len(_finding_issues(data_or_issues))


def _classify_priority(issue: dict) -> str:
    """UI 展示优先级：high / manual / other。"""
    severity = str(issue.get("severity") or "").upper()
    rule_id = str(issue.get("rule_id") or "")

    # FA list / by-item → other
    if str(issue.get("procedure_code") or "").upper() == "FA_LIST":
        return "other"
    if rule_id.startswith(_BY_ITEM_RULE_PREFIX):
        return "manual" if severity == "NEED_REVIEW" else "other"

    # LLM / manual
    llm_review = issue.get("llm_review_type")
    review_source = str(issue.get("review_source") or "").lower()
    if severity == "NEED_REVIEW" or llm_review or "llm" in review_source:
        return "manual"

    # Core high-priority FAIL
    if severity == "FAIL" and rule_id in _HIGH_PRIORITY_RULE_IDS:
        return "high"

    return "other"


def _priority_label(priority: str) -> str:
    return {"high": "高优先级", "manual": "需审计师判断", "other": "一般提示"}.get(priority, priority)


def _finding_row(issue: dict) -> dict:
    """单条 finding → 表格行 dict。"""
    cell = ""
    sr = issue.get("source_row")
    if sr:
        cell = f"${get_column_letter(2)}${sr}"
    return {
        "级别": issue.get("severity"),
        "优先级": _priority_label(_classify_priority(issue)),
        "程序": _procedure_display(issue.get("procedure_code")),
        "工作表": issue.get("source_sheet") or "—",
        "单元格": cell or "—",
        "规则": issue.get("dict_rule_code") or issue.get("rule_id") or "—",
        "说明": issue.get("message") or "—",
        "建议": issue.get("suggestion") or "",
        "_issue": issue,
    }


def _procedure_display(procedure: object) -> str:
    value = str(procedure or "").strip()
    return _PROCEDURE_LABELS.get(value, value or "其他")


def render_findings_explorer(
    data_or_issues,
    key_prefix: str = "",
) -> None:
    """渲染可交互 Findings 浏览器。

    Args:
        data_or_issues: QcReport dict 或 issues list
        key_prefix: Streamlit widget key 前缀（多实例隔离）
    """
    issues = _finding_issues(data_or_issues)
    if not issues:
        st.success("本次未发现异常 findings。")
        return

    # 构建行数据
    rows = [_finding_row(i) for i in issues]

    # --- 筛选栏 ---
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([2, 1.5, 1.5, 1])
    with filter_col1:
        search = st.text_input(
            "搜索", placeholder="规则 / 说明 / 建议...",
            key=f"{key_prefix}_search",
            label_visibility="collapsed",
        )
    with filter_col2:
        all_procedures = sorted(set(r["程序"] for r in rows))
        proc_filter = st.selectbox(
            "程序", ["全部程序"] + all_procedures,
            key=f"{key_prefix}_proc",
            label_visibility="collapsed",
        )
    with filter_col3:
        sev_filter = st.selectbox(
            "级别", ["全部级别", "FAIL", "WARN", "NEED_REVIEW"],
            key=f"{key_prefix}_sev",
            label_visibility="collapsed",
        )
    with filter_col4:
        pri_filter = st.selectbox(
            "优先级", ["全部优先级", "高优先级", "需审计师判断", "一般提示"],
            key=f"{key_prefix}_pri",
            label_visibility="collapsed",
        )

    # --- 筛选逻辑 ---
    filtered = rows
    if search:
        q = search.lower()
        filtered = [r for r in filtered if q in str(r.get("说明", "")).lower() or q in str(r.get("规则", "")).lower() or q in str(r.get("建议", "")).lower()]
    if proc_filter and proc_filter != "全部程序":
        filtered = [r for r in filtered if r["程序"] == proc_filter]
    if sev_filter and sev_filter != "全部级别":
        filtered = [r for r in filtered if r["级别"] == sev_filter]
    if pri_filter and pri_filter != "全部优先级":
        filtered = [r for r in filtered if r["优先级"] == pri_filter]

    # --- 表格 ---
    st.caption(f"共 {len(filtered)} 条（总数 {len(rows)} 条）")

    display_cols = ["级别", "优先级", "程序", "工作表", "单元格", "规则", "说明"]
    st.dataframe(
        [{c: r[c] for c in display_cols} for r in filtered],
        use_container_width=True,
        hide_index=True,
        column_config={
            "级别": st.column_config.TextColumn(width="small"),
            "说明": st.column_config.TextColumn(width="large"),
        },
    )

    # --- 行详情展开 ---
    with st.expander("点击上方表格行序号查看详情（选择行号）", expanded=False):
        row_idx = st.number_input(
            "行号", min_value=1, max_value=len(filtered),
            value=1, key=f"{key_prefix}_detail_idx",
            label_visibility="collapsed",
        )
        if 1 <= row_idx <= len(filtered):
            _render_finding_detail(filtered[row_idx - 1])


def _render_finding_detail(row: dict) -> None:
    """渲染单条 finding 的详细面板（含 trace）。"""
    issue = row.get("_issue", {})
    st.markdown(f"### {render_severity_badge(row['级别'])}  {row.get('规则', '—')}", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**程序**：{row.get('程序', '—')}")
        st.markdown(f"**工作表**：{row.get('工作表', '—')}")
        st.markdown(f"**单元格**：`{row.get('单元格', '—')}`")
        st.markdown(f"**判断来源**：{issue.get('review_source', '规则判断')}")

    with col2:
        st.markdown(f"**优先级**：{row.get('优先级', '—')}")
        if issue.get("dict_rule_code"):
            st.markdown(f"**规则编号**：{issue.get('dict_rule_code')}")
        if issue.get("k1_checklist_ref"):
            st.markdown(f"**K1 引用**：{issue.get('k1_checklist_ref')}")

    st.divider()
    st.markdown(f"**问题说明**")
    st.write(row.get("说明", "—"))
    if row.get("建议"):
        st.markdown(f"**建议动作**")
        st.info(row["建议"])

    # ---- 系统取数证据 ----
    _render_finding_trace(issue)


def _render_finding_trace(issue: dict) -> None:
    """从 execution_ledger 匹配 observation 并渲染 trace 面板。"""
    rule_id = issue.get("rule_id", "")
    if not rule_id:
        return

    # 尝试从 st.session_state 获取当前运行的 ledger 数据
    ledger = None
    results = st.session_state.get("qc_results", {})
    if results:
        for bundle in results.values():
            data = bundle.get("data") or {}
            candidates = data.get("execution_ledger") or {}
            if candidates:
                ledger = candidates
                break
    if not ledger:
        from report.ui_state.run_store import get_latest_run
        latest = get_latest_run()
        if latest and latest.get("data"):
            ledger = latest["data"].get("execution_ledger") or {}

    if not ledger:
        return

    items = ledger.get("items") or []
    match = next((it for it in items if it.get("rule_id") == rule_id), None)
    if not match:
        return

    obs = match.get("observation")
    if not obs or not isinstance(obs, dict):
        return

    # 证据级 observation
    checked_data = obs.get("checked_data") or []
    if checked_data:
        with st.expander("系统取数证据", expanded=False):
            for idx, item in enumerate(checked_data, 1):
                if not isinstance(item, dict):
                    continue
                sheet = item.get("sheet", "—")
                st.markdown(f"**检查资料 {idx}**：{sheet} / {item.get('section', '—')}")
                values_read = item.get("values_read") or []
                if values_read:
                    st.markdown("**实际读取值**")
                    st.dataframe(
                        [
                            {
                                "标签": _display_value(v.get("label")),
                                "值": _display_value(v.get("value")),
                                "单元格": _display_value(v.get("cell")),
                                "行": _display_value(v.get("row")),
                            }
                            for v in values_read
                            if isinstance(v, dict)
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                missing = item.get("missing_data") or []
                if missing:
                    st.warning("缺失资料：" + "；".join(str(v) for v in missing))

            for label, key in [("检查逻辑", "check_logic"), ("判断标准", "expected_result"), ("实际结果", "actual_result"), ("执行结果", "result_summary")]:
                text = str(obs.get(key) or "").strip()
                if text:
                    st.markdown(f"**{label}**")
                    st.write(text)
        return

    # 旧版 observation
    path = obs.get("path", "—")
    inputs = obs.get("inputs") or []
    checks = obs.get("checks") or []
    if path or inputs or checks:
        input_texts = []
        for inp in (inputs or [])[:5]:
            if isinstance(inp, dict):
                parts = [str(inp.get(k) or "") for k in ("source_sheet", "section", "field") if inp.get(k)]
                input_texts.append(" / ".join(parts) if parts else "—")
        check_texts = []
        for ch in (checks or [])[:5]:
            if isinstance(ch, dict):
                result = ch.get("result", "")
                parts = [str(ch.get(k) or "") for k in ("name", "left_label", "operator", "right_label") if ch.get(k)]
                check_texts.append(f"{' '.join(parts)} → {result}" if parts else str(result))
        with st.expander("系统取数证据", expanded=False):
            st.info("该规则使用旧版执行说明。")
            st.write({"检查方式": path, "依赖资料": "；".join(input_texts) if input_texts else "—", "检查摘要": "；".join(check_texts) if check_texts else "—"})


def _display_value(value: object) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    if not text or text.lower() == "none":
        return "—"
    return text

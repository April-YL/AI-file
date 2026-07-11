# [阶段一] 复核工作台首页 — 项目状态 + 待处理队列 + 快速操作
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 复核工作台（首页）。

定位：任务驱动。帮审计师回答"现在需要我做什么"。
"""

from __future__ import annotations

import streamlit as st

from report.ui_components.cards import (
    render_section_title,
    render_severity_badge,
    render_stat_card,
)
from report.ui_components.execution_ledger_table import build_execution_scope_summary
from report.ui_state.run_store import get_latest_run
from report.ui_state.project_store import get_project


def render_workbench() -> None:
    """渲染复核工作台首页。"""
    latest = get_latest_run()
    if not latest or not latest.get("data"):
        _render_empty_state()
        return

    data = latest.get("data") or {}
    summary = data.get("summary") or {}
    project = get_project(latest.get("project_id"))

    top_left, top_right = st.columns([2.2, 1])
    with top_left:
        _render_project_status(project, latest, summary)
    with top_right:
        _render_primary_actions(data)

    _render_pending_queue(data)
    _render_execution_coverage(data)


def _render_empty_state() -> None:
    """无历史运行时显示的空状态。"""
    st.markdown(
        """
        <div style="text-align:center;padding:60px 20px">
          <div style="font-size:3rem;margin-bottom:12px">📋</div>
          <h2 style="color:var(--ey-black);margin-bottom:8px">欢迎使用审计底稿复核 Agent</h2>
          <p style="color:var(--gray-500);font-size:1rem;margin-bottom:24px">
            当前科目：固定资产 K1<br>
            上传第一份底稿开始复核
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("开始复核", type="primary", use_container_width=True):
        st.session_state["active_page"] = "runner"


def _render_project_status(project: dict | None, latest: dict, summary: dict) -> None:
    """项目状态栏。"""
    proj_name = "当前复核状态"
    eng_name = project.get("engagement_name", "") if project else ""
    subject = latest.get("subject_code", "FA_K1")
    subject_display = "固定资产 K1" if subject == "FA_K1" else subject
    data = latest.get("data") or {}

    eng_badge = f" · {eng_name}" if eng_name else ""
    overall = summary.get("overall_severity", "PASS")
    st.markdown(
        f"""
        <div class="qc-file-header">
          <h2>{proj_name}{eng_badge}</h2>
          <p>科目：{subject_display} · 待处理事项：{_non_pass_count(data)} · 最高提示级别：{overall}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pending_queue(data: dict) -> None:
    """待处理 Findings 摘要：工作台只保留入口，不重复完整清单。"""
    summary = data.get("summary") or {}
    issues = _non_pass_issues(data)
    render_section_title("待处理复核事项", "首页只展示当前需要处理的事项入口，不替代复核结果明细。")

    count_cols = st.columns(4)
    count_items = [
        ("待处理", len(issues), "非 PASS findings", "info"),
        ("异常", summary.get("fail_count", 0), "FAIL", "high"),
        ("需关注", summary.get("warn_count", 0), "WARN", "warn"),
        ("待人工判断", summary.get("need_review_count", 0), "NEED_REVIEW", "review"),
    ]
    for col, (label, value, note, tone) in zip(count_cols, count_items):
        with col:
            render_stat_card(label, str(value), note, tone)

    if not issues:
        st.success("暂无待处理 Findings。")
        return

    groups = _group_by_priority(issues)
    top_items = (groups.get("high", []) + groups.get("manual", []) + groups.get("other", []))[:3]

    for item in top_items:
        sev = item.get("severity", "")
        rule = item.get("dict_rule_code") or item.get("rule_id", "—")
        msg = (item.get("message") or "—")[:120]
        sheet = item.get("source_sheet") or "—"
        cell = item.get("source_cell") or item.get("cell") or ""
        location = f"{sheet}!{cell}" if cell and sheet != "—" else sheet
        st.markdown(
            f"{render_severity_badge(sev)} **{rule}** · {msg} "
            f"<span style='color:var(--gray-500);font-size:0.78rem'>({location})</span>",
            unsafe_allow_html=True,
        )

    if st.button(f"查看完整复核结果（{len(issues)} 条）", type="primary", key="wb_view_full_findings"):
        st.session_state["active_page"] = "findings"
        st.rerun()


def _render_execution_coverage(data: dict) -> None:
    """展示执行覆盖摘要，数据来自 rule_execution_matrix 合并结果。"""
    render_section_title("质检点执行覆盖")
    scope = build_execution_scope_summary(data)
    if not scope.get("ledger_rows"):
        st.info("本次报告未包含完整质检点清单。")
        return
    cols = st.columns(4)
    values = [
        ("总数", scope["total"], "完整质检点清单", "info"),
        ("已执行", scope["executed"], "规则流程已运行", "pass"),
        ("原因明确", scope["not_executed_with_reason"], "资料不足或不适用", "warn"),
        ("待补充", scope["pending_record"], "需补状态或原因", "info"),
    ]
    for col, (label, value, note, tone) in zip(cols, values):
        with col:
            render_stat_card(label, str(value), note, tone)


def _render_primary_actions(data: dict) -> None:
    """首页主操作：只保留启动复核与查看结果。"""
    st.markdown("**操作**")

    if st.button("开始新复核", type="primary", use_container_width=True, key="wb_start_review"):
        st.session_state["active_page"] = "runner"
        st.rerun()

    if st.button(f"查看结果（{_non_pass_count(data)} 条）", use_container_width=True, key="wb_view_results"):
        st.session_state["active_page"] = "findings"
        st.rerun()


# ---- helpers ----

def _non_pass_issues(data: dict) -> list[dict]:
    return [i for i in data.get("issues", []) if i.get("severity") != "PASS"]


def _non_pass_count(data: dict) -> int:
    return len(_non_pass_issues(data))


def _group_by_priority(issues: list[dict]) -> dict[str, list[dict]]:
    """按 UI 优先级分组（复用 findings_table 的分类逻辑）。"""
    from report.ui_components.findings_table import _classify_priority

    groups: dict[str, list[dict]] = {"high": [], "manual": [], "other": []}
    rank = {"FAIL": 0, "NEED_REVIEW": 1, "WARN": 2, "PASS": 3}
    for issue in issues:
        groups[_classify_priority(issue)].append(issue)
    for items in groups.values():
        items.sort(key=lambda i: (rank.get(str(i.get("severity")), 9), str(i.get("rule_id") or "")))
    return groups

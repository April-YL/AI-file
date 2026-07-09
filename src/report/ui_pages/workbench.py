# [阶段一] 复核工作台首页 — 项目状态 + 待处理队列 + 快速操作
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 复核工作台（首页）。

定位：任务驱动。帮审计师回答"现在需要我做什么"。
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from report.ui_components.cards import (
    render_info_banner,
    render_section_title,
    render_severity_badge,
    render_stat_card,
)
from report.ui_components.download_bar import render_download_bar
from report.ui_components.execution_ledger_table import build_execution_scope_summary
from report.ui_state.run_store import get_latest_run, list_runs, get_run
from report.ui_state.project_store import get_project


def render_workbench() -> None:
    """渲染复核工作台首页。"""
    runs = list_runs(limit=50)
    if not runs:
        _render_empty_state()
        return

    # 运行选择器
    run_options = {r["id"]: f"{r.get('completed_at','')} · {r.get('source_filename','')} · {r.get('overall_severity','')}" for r in runs}
    selected_run = st.selectbox(
        "查看运行", options=list(run_options.keys()),
        format_func=lambda x: run_options[x], index=0, key="wb_run_sel",
    )
    run = get_run(selected_run)
    if not run or not run.get("data"):
        _render_empty_state()
        return

    latest = run
    data = latest.get("data") or {}
    summary = data.get("summary") or {}
    project = get_project(latest.get("project_id"))

    _render_project_status(project, latest, summary)
    _render_quick_stats(summary, data)
    col_left, col_right = st.columns([1.9, 1])

    with col_left:
        _render_pending_queue(data)
        _render_execution_coverage(data)

    with col_right:
        _render_quick_actions(latest)
        _render_recent_timeline()


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
    proj_name = project.get("name", "未命名项目") if project else "未命名项目"
    eng_name = project.get("engagement_name", "") if project else ""
    subject = latest.get("subject_code", "FA_K1")
    subject_display = "固定资产 K1" if subject == "FA_K1" else subject

    eng_badge = f" · {eng_name}" if eng_name else ""
    overall = summary.get("overall_severity", "PASS")
    st.markdown(
        f"""
        <div class="qc-file-header">
          <h2>{proj_name}{eng_badge}</h2>
          <p>科目：{subject_display} · 最近复核：{latest.get('completed_at', '—')} · 最高提示级别：{overall}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_quick_stats(summary: dict, data: dict) -> None:
    """快速统计卡片行。"""
    overall = summary.get("overall_severity", "PASS")
    findings = _non_pass_count(data)
    scope = build_execution_scope_summary(data)
    all_rules = scope.get("total") or (data.get("rule_execution_summary") or {}).get("matrix_rule_count", 0)
    executed = scope.get("executed") or 0

    cols = st.columns(4)
    with cols[0]:
        render_stat_card(
            "上次复核最高提示级别",
            render_severity_badge(overall),
            f"{findings} findings",
            "high" if overall == "FAIL" else "warn" if overall == "WARN" else "info",
        )
    with cols[1]:
        render_stat_card("规则执行", f"{executed} / {all_rules}", f"{scope.get('pending_record', 0)} 条待补充记录", "info")
    with cols[2]:
        fail_count = summary.get("fail_count", 0)
        warn_count = summary.get("warn_count", 0)
        render_stat_card("需关注项", str(fail_count + warn_count), f"异常 {fail_count} + 需关注 {warn_count}", "warn")
    with cols[3]:
        review_count = summary.get("need_review_count", 0)
        render_stat_card("待审计师判断", str(review_count), "NEED_REVIEW · 需审计师判断", "review")


def _render_pending_queue(data: dict) -> None:
    """待处理 Findings 摘要：工作台只保留入口，不重复完整清单。"""
    render_section_title("待处理复核事项")

    issues = _non_pass_issues(data)
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


def _render_quick_actions(latest: dict) -> None:
    """快速操作区。"""
    st.markdown("**快速操作**")

    if st.button("开始新复核", type="primary", use_container_width=True):
        st.session_state["active_page"] = "runner"

    # 底稿交付物下载
    artifact_dir = latest.get("artifact_dir")
    data = latest.get("data") or {}
    if data and artifact_dir:
        from report.ui_state.database import ARTIFACTS_DIR
        ad = ARTIFACTS_DIR / artifact_dir
        json_path = ad / "report.json"
        html_path = ad / "review.html"
        xlsx_path = ad / "annotated.xlsx"

        if json_path.exists() and html_path.exists():
            st.markdown("**上次复核交付物**")
            with open(json_path, "rb") as f:
                json_bytes = f.read()
            with open(html_path, "rb") as f:
                html_bytes = f.read()
            annotated = xlsx_path.read_bytes() if xlsx_path.exists() else None
            render_download_bar(
                latest.get("source_filename", "workpaper"),
                str(latest.get("id", "")),
                json_bytes,
                html_bytes,
                annotated,
            )

    if st.button("查看运行历史", use_container_width=True):
        st.session_state["active_page"] = "history"


def _render_recent_timeline() -> None:
    """最近运行时间线（最多 2 条）。"""
    st.markdown("**最近运行**")
    runs = list_runs(limit=2)
    if not runs:
        st.caption("暂无运行记录")
        return
    for item in runs[:2]:
        sev = item.get("overall_severity", "PASS")
        cls = {"FAIL": "high", "WARN": "warn", "PASS": "pass"}.get(sev, "info")
        render_stat_card(
            item.get("source_filename", "—"),
            render_severity_badge(sev),
            f"{item.get('completed_at', '—')} · {item.get('finding_count', 0)} findings · {'LLM' if item.get('llm_enabled') else '纯规则'}",
            cls,
        )


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

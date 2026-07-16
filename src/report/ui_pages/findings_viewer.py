# [阶段一] 复核结果页 — Findings + 质检点执行台账
# 从 ui_app.py 的 _render_result_view + _render_priority_findings 等迁移
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 复核结果页。

阶段一仅展示当前运行结果（阶段二起支持历史运行选择器）。
"""

from __future__ import annotations

import streamlit as st

from report.ui_components.cards import render_stat_card, render_severity_badge
from report.ui_components.download_bar import render_download_bar
from report.ui_components.execution_ledger_table import (
    build_execution_scope_summary,
    render_execution_ledger_table,
)
from report.ui_components.findings_table import (
    _classify_priority,
    _finding_count,
    _finding_issues,
    render_findings_explorer,
)
from report.ui_state.run_store import get_latest_run, list_runs, get_run


def render_findings_viewer() -> None:
    """渲染复核结果页。"""
    active_run = st.session_state.get("active_run") or {}
    if _block_unfinished_active_run(active_run):
        return

    # 历史运行选择器
    runs = list_runs(limit=50)
    # 先从 session_state 取最新结果
    session_results = st.session_state.get("qc_results", {})
    target_run_id = st.session_state.get("last_saved_run_id")
    if session_results:
        latest_run_id = None
        for bundle in session_results.values():
            latest_run_id = bundle.get("saved_run_id")
            break
        target_run_id = target_run_id or latest_run_id
        default_idx = 0
        if target_run_id and runs:
            for i, r in enumerate(runs):
                if r["id"] == target_run_id:
                    default_idx = i
                    break
    else:
        default_idx = 0
        if target_run_id and runs:
            for i, r in enumerate(runs):
                if r["id"] == target_run_id:
                    default_idx = i
                    break

    if not runs:
        st.info("暂无运行记录。请先执行一次复核。")
        return

    run_options = {r["id"]: f"{r.get('completed_at','')} · {r.get('source_filename','')} · {r.get('overall_severity','')}" for r in runs}
    selected_run = st.selectbox(
        "查看运行", options=list(run_options.keys()),
        format_func=lambda x: run_options[x], index=default_idx, key="fv_run_sel",
    )

    # 优先 session_state 最新结果
    if session_results and selected_run == target_run_id:
        names = list(session_results.keys())
        bundle = session_results[names[0]]
        data = bundle["data"]
        filename = names[0]
        run_id = bundle.get("run_id", "00000000_000000")
        duration_seconds = None
        json_bytes = bundle.get("json_bytes", b"{}")
        html_bytes = bundle.get("html_bytes", b"<html></html>")
        annotated_bytes = bundle.get("annotated_bytes")
    else:
        run = get_run(selected_run)
        if not run or not run.get("data"):
            st.info("无法加载运行数据。")
            return
        data = run["data"]
        filename = run.get("source_filename", "—")
        run_id = str(run.get("id", "00000000_000000"))
        duration_seconds = run.get("duration_seconds")
        json_bytes = b""
        html_bytes = b""
        annotated_bytes = None
        artifact_dir = run.get("artifact_dir")
        if artifact_dir:
            from report.ui_state.database import ARTIFACTS_DIR
            ad = ARTIFACTS_DIR / artifact_dir
            if (ad / "report.json").exists():
                json_bytes = (ad / "report.json").read_bytes()
            if (ad / "review.html").exists():
                html_bytes = (ad / "review.html").read_bytes()
            xlsx_path = ad / "annotated.xlsx"
            if xlsx_path.exists():
                annotated_bytes = xlsx_path.read_bytes()

    # --- 顶部：紧凑运行条 + 交付物 ---
    summary = data.get("summary") or {}
    overall = summary.get("overall_severity", "PASS")
    findings = _finding_count(data)
    build_info = data.get("build_info") or {}
    run_version = str(build_info.get("pilot_build") or "").strip() or "历史未记录"

    st.markdown(
        f"""
        <div class="qc-info-banner">
          当前运行：<strong>{filename}</strong> ·
          {render_severity_badge(overall)} · {findings} findings · 运行编号 {run_id} ·
          运行版本：{run_version}
        </div>
        """,
        unsafe_allow_html=True,
    )

    delivery_guard = (data.get("runtime_timings") or {}).get("delivery_guard") or {}
    if delivery_guard.get("disposition") == "REVIEW_REQUIRED":
        st.warning(
            "检测到批量异常问题簇：逐条 findings 已保留供追溯，但标注底稿和 HTML "
            "仅交付聚合待复核提示。请先确认 Sheet、字段映射和金额组口径。"
        )

    # --- 底稿交付物下载（仅在有真实数据时显示）---
    if json_bytes and html_bytes and json_bytes != b"{}" and html_bytes != b"<html></html>":
        render_download_bar(filename, run_id, json_bytes, html_bytes, annotated_bytes)
    else:
        st.info("当前运行暂无可下载交付物。")

    _render_findings_summary_row(data)
    _render_execution_summary_row(data)

    # --- 主 Tab ---
    tab_browser, tab_ledger, tab_extract, tab_runtime = st.tabs([
        "Findings 明细", "质检点执行台账", "基本信息摘录", "运行耗时",
    ])

    with tab_browser:
        render_findings_explorer(data, key_prefix="main")

    with tab_ledger:
        render_execution_ledger_table(data, key_prefix="result_ledger")

    with tab_extract:
        _render_manual_review(data)

    with tab_runtime:
        _render_runtime_timings(data.get("runtime_timings") or {}, filename, duration_seconds=duration_seconds)
        qc_timings = st.session_state.get("qc_timings", {})
        if qc_timings:
            for fname, timings in qc_timings.items():
                if fname != filename:
                    _render_runtime_timings(timings, fname)


def _render_findings_summary_row(data: dict) -> None:
    """Tab 上方 Findings 摘要行。"""
    issues = _finding_issues(data)
    severity_counts = {"FAIL": 0, "WARN": 0, "NEED_REVIEW": 0}
    for issue in issues:
        severity = str(issue.get("severity") or "").upper()
        if severity in severity_counts:
            severity_counts[severity] += 1

    cols = st.columns(4)
    with cols[0]:
        render_stat_card("Findings", str(len(issues)), "不含 PASS", "info")
    with cols[1]:
        render_stat_card("优先查看", str(severity_counts["FAIL"]), "FAIL", "high")
    with cols[2]:
        render_stat_card("需关注", str(severity_counts["WARN"]), "WARN", "warn")
    with cols[3]:
        render_stat_card("待人工处理", str(severity_counts["NEED_REVIEW"]), "NEED_REVIEW", "review")


def _render_execution_summary_row(data: dict) -> None:
    """Tab 上方质检点执行台账摘要行。"""
    scope = build_execution_scope_summary(data)
    if scope["ledger_rows"]:
        total = scope["total"]
        executed = scope["executed"]
        not_executed_with_reason = scope["not_executed_with_reason"]
        pending_record = scope["pending_record"]
    else:
        ledger = data.get("execution_ledger") or {}
        ledger_summary = ledger.get("summary") or {}
        total = int(ledger_summary.get("total_observed_checkpoints") or 0)
        executed = int(ledger_summary.get("executed") or 0)
        not_executed_with_reason = int(ledger_summary.get("data_insufficient") or 0) + int(
            ledger_summary.get("not_applicable") or 0
        )
        pending_record = max(total - executed - not_executed_with_reason, 0)

    cols = st.columns(4)
    with cols[0]:
        render_stat_card("质检点总数", str(total), "来自完整质检点清单", "info")
    with cols[1]:
        render_stat_card("已执行", str(executed), "规则流程已运行", "pass")
    with cols[2]:
        render_stat_card("原因明确", str(not_executed_with_reason), "资料不足或场景不适用", "warn")
    with cols[3]:
        render_stat_card("待补充", str(pending_record), "需补状态或原因", "info")

    if scope.get("errors"):
        st.error("；".join(scope["errors"]))

def _block_unfinished_active_run(active_run: dict) -> bool:
    """阻止未保存运行时把旧历史结果误展示为本次结果。"""
    if not isinstance(active_run, dict):
        return False
    status = active_run.get("status")
    saved_run_id = active_run.get("saved_run_id")
    if status in {"running", "failed"} and not saved_run_id:
        filename = active_run.get("filename") or "当前底稿"
        if status == "running":
            st.warning(
                f"{filename} 的复核尚未完成保存，当前步骤：{active_run.get('current_step') or '—'}。"
                "为避免误读旧结果，本页暂不展示历史运行。"
            )
        else:
            st.error(
                f"{filename} 的复核未完成保存：{active_run.get('error') or '未知错误'}。"
                "请回到执行复核页重新执行。"
            )
        if st.button("返回执行复核", key="fv_back_to_runner_for_active_run"):
            st.session_state["active_page"] = "runner"
            st.rerun()
        return True
    return False


def _render_findings_stats(data: dict) -> None:
    issues = _finding_issues(data)
    groups = {"high": [], "manual": [], "other": []}
    for issue in issues:
        groups.setdefault(_classify_priority(issue), []).append(issue)

    cols = st.columns(4)
    with cols[0]:
        render_stat_card("Findings 总数", str(len(issues)), "不含 PASS", "info")
    with cols[1]:
        render_stat_card("高优先级问题", str(len(groups["high"])), "优先查看", "high")
    with cols[2]:
        render_stat_card("需人工处理", str(len(groups["manual"])), "需复核", "review")
    with cols[3]:
        render_stat_card("其他提示", str(len(groups["other"])), "一般提示", "info")


def _render_execution_scope_stats(data: dict) -> None:
    scope = build_execution_scope_summary(data)
    if scope["ledger_rows"]:
        total = scope["total"]
        executed = scope["executed"]
        not_executed_with_reason = scope["not_executed_with_reason"]
        pending_record = scope["pending_record"]
    else:
        ledger = data.get("execution_ledger") or {}
        ledger_summary = ledger.get("summary") or {}
        total = int(ledger_summary.get("total_observed_checkpoints") or 0)
        executed = int(ledger_summary.get("executed") or 0)
        not_executed_with_reason = int(ledger_summary.get("data_insufficient") or 0) + int(
            ledger_summary.get("not_applicable") or 0
        )
        pending_record = max(total - executed - not_executed_with_reason, 0)

    cols = st.columns(4)
    with cols[0]:
        render_stat_card("本次质检点总数", str(total), "来自完整质检点清单", "info")
    with cols[1]:
        render_stat_card("已执行", str(executed), "规则流程已运行", "pass")
    with cols[2]:
        render_stat_card("未执行，原因明确", str(not_executed_with_reason), "资料不足或场景不适用", "warn")
    with cols[3]:
        render_stat_card("待补充执行记录", str(pending_record), "需补充状态或原因", "info")

    if scope.get("errors"):
        st.error("；".join(scope["errors"]))


def _render_procedure_summary(data: dict) -> None:
    """按程序汇总展示 findings。"""
    from report.procedure_labels import group_findings_by_procedure

    groups = group_findings_by_procedure(data.get("issues", []))
    if not groups:
        st.success("所有程序暂无异常 findings。")
        return

    for code, label, items in groups:
        if not items:
            continue
        from report.ui_components.findings_table import _worst_severity

        sev = _worst_severity(items)
        fail_c = sum(1 for i in items if i.get("severity") == "FAIL")
        warn_c = sum(1 for i in items if i.get("severity") == "WARN")
        review_c = sum(1 for i in items if i.get("severity") == "NEED_REVIEW")

        with st.expander(f"{label} · {render_severity_badge(sev)} · {len(items)} 条", expanded=(sev == "FAIL")):
            st.caption(f"FAIL {fail_c} · WARN {warn_c} · NEED_REVIEW {review_c}")
            from report.ui_components.findings_table import _finding_row

            st.dataframe(
                [_finding_row(i) for i in items],
                use_container_width=True,
                hide_index=True,
            )


def _format_seconds(value: object) -> str:
    try: seconds = float(value or 0)
    except (TypeError, ValueError): seconds = 0.0
    if seconds >= 60: return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"


def _render_runtime_timings(timings: dict, filename: str, *, duration_seconds: object | None = None) -> None:
    timings = dict(timings or {})
    if "total_seconds" not in timings and duration_seconds not in (None, ""):
        timings["total_seconds"] = duration_seconds
    labels = [
        ("总耗时", "total_seconds"),
        ("读取底稿", "ingest_seconds"),
        ("规则检查", "rules_seconds"),
        ("LLM", "llm_seconds"),
        ("报告生成", "json_html_seconds"),
        ("标注副本", "annotated_seconds"),
    ]
    parts = [(label, _format_seconds(timings.get(key))) for label, key in labels if key in timings]
    if not parts:
        return
    llm_note = "启用" if timings.get("llm_enabled") else "未启用"
    st.markdown(
        "<div class='qc-runtime-strip'>"
        + "".join(
            f"<div class='qc-runtime-item'><div class='qc-runtime-label'>{label}</div>"
            f"<div class='qc-runtime-value'>{value}</div></div>"
            for label, value in parts
        )
        + "</div>"
        + f"<div style='font-size:0.72rem;color:var(--gray-500);margin-bottom:6px'>{filename} · LLM {llm_note}</div>",
        unsafe_allow_html=True,
    )
    if len(parts) == 1 and parts[0][0] == "总耗时":
        st.caption("该运行未记录分项耗时。")
    llm_details = timings.get("llm_details") or []
    if llm_details:
        detail_parts = []
        for item in llm_details:
            if isinstance(item, dict):
                label = item.get("label") or item.get("key") or "LLM"
                detail_parts.append(f"{label}: {_format_seconds(item.get('seconds'))} ({item.get('calls', 0)}次)")
        if detail_parts:
            with st.expander("LLM 分项耗时", expanded=False):
                st.caption(" · ".join(detail_parts))


def _render_manual_review(data: dict) -> None:
    """基本信息摘录区。"""
    st.info("以下为底稿基础信息摘录，供对照 Canvas/A3/项目组资料使用；不代表自动完成外部资料一致性判断。")

    lead = data.get("lead_sheet_section") or {}
    basic = lead.get("basic_info_fields") or []
    if basic:
        st.subheader("Lead 基准信息摘录")
        st.dataframe(
            [{"项目": f.get("label"), "底稿值": f.get("value"), "单元格": f.get("source_cell")}
             for f in basic],
            use_container_width=True,
            hide_index=True,
        )

    for sec in data.get("manual_review_sections") or []:
        if not isinstance(sec, dict):
            continue
        code = sec.get("dict_rule_code", "")
        st.subheader(sec.get("checklist_prompt") or sec.get("title", code))
        st.caption(sec.get("instruction", ""))
        items = sec.get("items") or []
        if not items:
            for note in sec.get("notes") or []:
                st.info(note)
            continue
        st.dataframe(
            [{"项目": it.get("label"), "底稿值": it.get("workpaper_value"), "外部参考": it.get("canvas_or_external_value")}
             for it in items if isinstance(it, dict)],
            use_container_width=True,
            hide_index=True,
        )

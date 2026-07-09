# [P2-1] 运行历史页 — sortable dataframe + 筛选 + 操作
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 运行历史。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from report.ui_state.run_store import list_runs, get_run, delete_run
from report.ui_state.database import ARTIFACTS_DIR


def render_run_history() -> None:
    st.subheader("运行历史")

    runs = list_runs(limit=50)
    if not runs:
        st.info("暂无运行记录。")
        return

    df = pd.DataFrame([{
        "ID": r["id"],
        "时间": r.get("completed_at", "—"),
        "文件名": r.get("source_filename", "—"),
        "最高提示级别": r.get("overall_severity", "—"),
        "Findings": r.get("finding_count", 0),
        "FAIL": r.get("fail_count", 0),
        "WARN": r.get("warn_count", 0),
        "REVIEW": r.get("need_review_count", 0),
        "LLM": "是" if r.get("llm_enabled") else "否",
        "耗时(s)": r.get("duration_seconds", 0),
    } for r in runs])

    # 筛选
    col1, col2 = st.columns([2, 1])
    with col1:
        search = st.text_input("搜索文件名", key="hist_search")
    with col2:
        sevs = ["全部"] + sorted(set(df["最高提示级别"].tolist()))
        sev_filter = st.selectbox("最高提示级别", sevs, key="hist_sev")

    filtered = df
    if search:
        filtered = filtered[filtered["文件名"].str.contains(search, case=False, na=False)]
    if sev_filter and sev_filter != "全部":
        filtered = filtered[filtered["最高提示级别"] == sev_filter]

    st.caption(f"共 {len(filtered)} 条（总数 {len(df)} 条）")

    # 表格
    event = st.dataframe(
        filtered,
        use_container_width=True, hide_index=True,
        column_config={
            "ID": st.column_config.NumberColumn(width="small"),
            "耗时(s)": st.column_config.NumberColumn(format="%.1f", width="small"),
        },
        on_select="rerun",
        selection_mode="single-row",
        key="hist_table",
    )

    # 选中行操作
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        idx = selected_rows[0]
        selected = filtered.iloc[idx]
        run_id = int(selected["ID"])

        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            if st.button("查看详情", type="primary", key=f"hist_view_{run_id}"):
                _load_run_to_session(run_id)
                st.session_state["active_page"] = "findings"
                st.rerun()
        with col_b:
            run = get_run(run_id)
            if run:
                _download_artifacts(run)
        with col_c:
            if st.button("对比此运行", key=f"hist_cmp_{run_id}"):
                st.session_state["compare_run_b"] = run_id
                st.session_state["active_page"] = "compare"
                st.rerun()
        with col_d:
            if st.button("删除", key=f"hist_del_{run_id}"):
                delete_run(run_id)
                st.rerun()
        run = get_run(run_id)
        if run and run.get("data"):
            _render_runtime_breakdown(
                run["data"].get("runtime_timings") or {},
                duration_seconds=run.get("duration_seconds"),
            )


def _load_run_to_session(run_id: int) -> None:
    run = get_run(run_id)
    if not run or not run.get("data"):
        return
    filename = run.get("source_filename", "history")
    artifact_dir = run.get("artifact_dir")
    json_bytes = b""
    html_bytes = b""
    annotated_bytes = None
    if artifact_dir:
        ad = ARTIFACTS_DIR / artifact_dir
        if (ad / "report.json").exists():
            json_bytes = (ad / "report.json").read_bytes()
        if (ad / "review.html").exists():
            html_bytes = (ad / "review.html").read_bytes()
        xlsx_path = ad / "annotated.xlsx"
        if xlsx_path.exists():
            annotated_bytes = xlsx_path.read_bytes()
    st.session_state["qc_results"] = {
        filename: {
            "data": run["data"],
            "json_bytes": json_bytes, "html_bytes": html_bytes,
            "annotated_bytes": annotated_bytes,
            "run_id": str(run_id), "saved_run_id": run_id,
        }
    }


def _download_artifacts(run: dict) -> None:
    artifact_dir = run.get("artifact_dir")
    if not artifact_dir:
        return
    ad = ARTIFACTS_DIR / artifact_dir
    for label, fname, mime in [
        ("复核报告 JSON", "report.json", "application/json"),
        ("复核报告 HTML", "review.html", "text/html"),
        ("标注底稿", "annotated.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ]:
        path = ad / fname
        if path.exists():
            st.download_button(label, path.read_bytes(), file_name=fname, mime=mime, key=f"hist_dl_{run['id']}_{fname}")


def _render_runtime_breakdown(timings: dict, *, duration_seconds: object | None = None) -> None:
    timings = dict(timings or {})
    if "total_seconds" not in timings and duration_seconds not in (None, ""):
        timings["total_seconds"] = duration_seconds
    if not timings:
        return
    labels = [
        ("总耗时", "total_seconds"),
        ("读取底稿", "ingest_seconds"),
        ("规则检查", "rules_seconds"),
        ("LLM", "llm_seconds"),
        ("报告生成", "json_html_seconds"),
        ("标注副本", "annotated_seconds"),
    ]
    parts = [
        f"{label}: {_format_seconds(timings.get(key))}"
        for label, key in labels
        if key in timings
    ]
    if parts:
        st.caption("耗时分解：" + " · ".join(parts))
    if parts and len(parts) == 1 and "总耗时" in parts[0]:
        st.caption("该运行未记录分项耗时。")


def _format_seconds(value: object) -> str:
    try:
        seconds = float(value or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"

# [阶段二] 运行对比页 — 同一 Entity 修正前后对比
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 运行对比。

核心场景：修正底稿后重新运行，确认改进效果。
匹配逻辑：优先 (rule_id, source_sheet, asset_id)，兜底 (rule_id, source_sheet, source_row, field)。
"""

from __future__ import annotations

import streamlit as st

from report.ui_state.run_store import get_run, list_runs
from report.ui_components.cards import render_severity_badge


def render_compare() -> None:
    st.subheader("运行对比")
    st.caption("同一审计主体 · 同一科目 · 修正前后对比。对比结果为辅助参考，不代表最终审计判断。")

    runs = list_runs(limit=50)
    if len(runs) < 2:
        st.info("需要至少 2 次运行才能对比。")
        return

    run_options = {r["id"]: f"{r.get('completed_at', '—')} · {r.get('source_filename', '—')} · {r.get('overall_severity', '—')}" for r in runs}

    col_a, col_vs, col_b = st.columns([2, 0.3, 2])
    with col_a:
        run_a_id = st.selectbox("运行 A（修正前）", options=list(run_options.keys()), format_func=lambda x: run_options[x], key="cmp_a")
    with col_vs:
        st.markdown("<div style='text-align:center;font-size:1.2rem;font-weight:800;padding-top:24px'>VS</div>", unsafe_allow_html=True)
    with col_b:
        # 默认选择最近一次
        default_b = runs[0]["id"] if runs else None
        run_b_id = st.selectbox("运行 B（修正后）", options=list(run_options.keys()), format_func=lambda x: run_options[x], index=list(run_options.keys()).index(default_b) if default_b in run_options else 0, key="cmp_b")

    if run_a_id == run_b_id:
        st.warning("请选择两次不同的运行。")
        return

    run_a = get_run(run_a_id)
    run_b = get_run(run_b_id)
    if not run_a or not run_b:
        st.error("无法加载运行数据。")
        return

    issues_a = _issues_with_key(run_a.get("data", {}))
    issues_b = _issues_with_key(run_b.get("data", {}))

    keys_a = set(issues_a.keys())
    keys_b = set(issues_b.keys())

    added = keys_b - keys_a
    removed = keys_a - keys_b
    common = keys_a & keys_b

    changed = []
    for k in common:
        sev_a = (issues_a[k].get("severity") or "PASS").upper()
        sev_b = (issues_b[k].get("severity") or "PASS").upper()
        if sev_a != sev_b:
            changed.append((k, issues_a[k], issues_b[k]))

    # 摘要
    st.markdown("### 对比摘要")
    cols = st.columns(4)
    with cols[0]:
        st.metric("新增", len(added), delta_color="off")
    with cols[1]:
        st.metric("消除", len(removed), delta_color="off")
    with cols[2]:
        st.metric("级别变化", len(changed), delta_color="off")
    with cols[3]:
        st.metric("不变", len(common) - len(changed), delta_color="off")

    st.divider()

    # 差异表格
    rows = []
    for k in added:
        rows.append({"变化": "🟢 新增", "级别": (issues_b[k].get("severity") or "—"), "规则": issues_b[k].get("dict_rule_code") or issues_b[k].get("rule_id", "—"), "说明": str(issues_b[k].get("message") or "—")[:120], "运行 A 状态": "— (不存在)"})
    for k in removed:
        rows.append({"变化": "🔴 消除", "级别": (issues_a[k].get("severity") or "—"), "规则": issues_a[k].get("dict_rule_code") or issues_a[k].get("rule_id", "—"), "说明": str(issues_a[k].get("message") or "—")[:120], "运行 B 状态": "— (不存在)"})
    for k, ia, ib in changed:
        rows.append({"变化": "🟡 级别变化", "级别": f"{(ia.get('severity') or '—')} → {(ib.get('severity') or '—')}", "规则": ib.get("dict_rule_code") or ib.get("rule_id", "—"), "说明": str(ib.get("message") or "—")[:120], "运行 A 状态": ia.get("severity", "—")})

    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.success("两次运行的 findings 完全一致。")


def _issues_with_key(data: dict) -> dict[tuple, dict]:
    """以 (rule_id, source_sheet, asset_id_or_row, field) 为键建立 finding 索引。"""
    result = {}
    for issue in data.get("issues", []):
        if not isinstance(issue, dict):
            continue
        if issue.get("severity") == "PASS":
            continue
        # 优先 asset_id，兜底 source_row
        identity = (
            issue.get("rule_id", ""),
            issue.get("source_sheet", ""),
            issue.get("asset_id") or issue.get("source_row", 0),
            issue.get("field", ""),
        )
        result[identity] = issue
    return result

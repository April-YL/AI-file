# [阶段二] 项目管理页 — 创建/切换/归档 Entity
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 项目管理。"""

from __future__ import annotations

import streamlit as st

from report.ui_state.project_store import (
    list_projects,
    list_engagements,
    create_project,
    archive_project,
    get_project,
)


def render_project_manager() -> None:
    st.subheader("项目管理")

    st.caption("Engagement = 审计委托（集团项目）  ·  Entity = 审计主体（法人实体）")

    # 新建
    with st.expander("新建审计主体", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Entity 名称", placeholder="如：G科技（母公司）", key="pm_name")
            client_name = st.text_input("客户名称", placeholder="如：G科技有限公司", key="pm_client")
            period_end = st.text_input("期间截止日", placeholder="如：2025-12-31", key="pm_period")
        with col2:
            engagement_code = st.text_input("项目代码（Engagement Code）", placeholder="如：SH-2025-00128", key="pm_ecode")
            engagement_name = st.text_input("项目名称（Engagement Name）", placeholder="如：XX集团 2025年度审计", key="pm_ename")
            canvas_id = st.text_input("Canvas ID（可选）", placeholder="Canvas 系统 ID", key="pm_cid")
        if st.button("创建", type="primary", key="pm_create"):
            if name.strip():
                pid = create_project(
                    name.strip(), client_name.strip(), period_end.strip(),
                    engagement_code=engagement_code.strip(),
                    engagement_name=engagement_name.strip(),
                    canvas_id=canvas_id.strip(),
                )
                st.success(f"已创建 Entity（ID: {pid}）")
                st.rerun()
            else:
                st.error("Entity 名称不能为空")

    # 列表
    projects = list_projects()
    engagements = list_engagements()

    if not projects:
        st.info("暂无项目。请创建第一个审计主体。")
        return

    # 按 engagement 分组
    eng_projects: dict[str, list[dict]] = {}
    standalone: list[dict] = []
    for p in projects:
        ename = p.get("engagement_name", "")
        if ename:
            eng_projects.setdefault(ename, []).append(p)
        else:
            standalone.append(p)

    for ename, plist in eng_projects.items():
        ecode = plist[0].get("engagement_code", "")
        code_str = f" · {ecode}" if ecode else ""
        st.markdown(f"**📁 {ename}{code_str}**（Engagement）")
        for p in plist:
            _render_entity_card(p)
        st.divider()

    if standalone:
        st.markdown("**📁 单体公司（无集团归集）**")
        for p in standalone:
            _render_entity_card(p)

    # 当前项目切换
    st.divider()
    current_id = st.session_state.get("active_project_id")
    current = get_project(current_id) if current_id else None
    current_name = current.get("name", "未选择") if current else "未选择"
    st.caption(f"当前活跃 Entity：**{current_name}**")

    project_options = {p["id"]: f"{p['name']}" for p in projects}
    selected = st.selectbox(
        "切换活跃 Entity",
        options=list(project_options.keys()),
        format_func=lambda pid: project_options[pid],
        index=list(project_options.keys()).index(current_id) if current_id in project_options else 0,
        key="pm_switch",
    )
    if selected != current_id:
        st.session_state["active_project_id"] = selected
        st.success(f"已切换到：{project_options[selected]}")
        st.rerun()


def _render_entity_card(p: dict) -> None:
    cols = st.columns([3, 1, 1, 1])
    with cols[0]:
        st.markdown(f"**{p['name']}**  ")
        st.caption(f"客户：{p.get('client_name', '—')} · 期间：{p.get('period_end', '—')}")
    with cols[1]:
        if st.button("切换到此", key=f"pm_sel_{p['id']}"):
            st.session_state["active_project_id"] = p["id"]
            st.rerun()
    with cols[2]:
        if st.button("编辑", key=f"pm_edit_{p['id']}"):
            st.info("编辑功能将在后续版本支持。")
    with cols[3]:
        if p.get("archived"):
            st.caption("已归档")
        elif st.button("归档", key=f"pm_arch_{p['id']}"):
            archive_project(p["id"])
            st.rerun()

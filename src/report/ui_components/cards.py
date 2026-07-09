# [阶段一] UI 组件 — 统计卡片、严重性徽章、状态标签
# 从 ui_app.py 的 _render_card / _severity_badge / _severity_class 迁移
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 可复用 UI 卡片与徽章组件。"""

from __future__ import annotations

import html
import streamlit as st


def _h(text: str | None) -> str:
    """HTML 转义。"""
    return html.escape(str(text) if text is not None else "", quote=True)


# ---- CSS class helpers ----

def severity_class(sev: str | None) -> str:
    """严重性 → CSS class（qc-badge-*）。"""
    sev = (sev or "PASS").upper()
    return sev if sev in {"PASS", "WARN", "FAIL", "NEED_REVIEW"} else "PASS"


def severity_label(sev: str | None) -> str:
    """严重性 → 中文标签。"""
    return {
        "FAIL": "异常",
        "WARN": "需关注",
        "NEED_REVIEW": "待复核",
        "PASS": "无待处理 Findings",
    }.get((sev or "PASS").upper(), str(sev))


def card_tone_class(tone: str) -> str:
    """色调 → qc-stat-card-* class。"""
    return {
        "high": "qc-stat-card-high",
        "warn": "qc-stat-card-warn",
        "review": "qc-stat-card-review",
        "pass": "qc-stat-card-pass",
        "info": "qc-stat-card-info",
    }.get(tone, "")


# ---- Rendering functions ----

def render_stat_card(
    label: str,
    value: object,
    note: str = "",
    tone: str = "other",
) -> None:
    """渲染统计卡片。

    Args:
        label: 卡片标签
        value: 卡片数值（支持 str / int / HTML）
        note: 底部说明
        tone: 色调 — high / warn / review / pass / info / other
    """
    tone_class = card_tone_class(tone)
    st.markdown(
        f"""
        <div class="qc-stat-card {tone_class}">
          <div class="qc-stat-label">{_h(label)}</div>
          <div class="qc-stat-value">{value}</div>
          <div class="qc-stat-note">{_h(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_severity_badge(severity: str | None) -> str:
    """返回 severity badge HTML 字符串。

    Returns:
        '<span class="qc-badge qc-badge-fail">FAIL</span>'
    """
    cls = severity_class(severity).lower()
    label = severity_label(severity) if severity else "—"
    # 在 badge 中显示中文 + 英文
    raw = (severity or "—").upper()
    display = f"{label} ({raw})" if raw in ("FAIL", "WARN", "NEED_REVIEW") else raw
    return f'<span class="qc-badge qc-badge-{cls}">{_h(display)}</span>'


def render_overall_badge(severity: str | None) -> str:
    """返回显示最高提示级别的 badge HTML。"""
    cls = severity_class(severity).lower()
    raw = (severity or "PASS").upper()
    return f'<span class="qc-badge qc-badge-{cls}">{_h(raw)}</span>'


def render_section_title(title: str, caption: str = "") -> None:
    """渲染章节标题。"""
    st.markdown(
        f'<div class="qc-section-title">{_h(title)}</div>',
        unsafe_allow_html=True,
    )
    if caption:
        st.markdown(
            f'<div class="qc-section-caption">{_h(caption)}</div>',
            unsafe_allow_html=True,
        )


def render_info_banner(text: str) -> None:
    """渲染信息横幅（黄条）。"""
    st.markdown(
        f'<div class="qc-info-banner">{text}</div>',
        unsafe_allow_html=True,
    )

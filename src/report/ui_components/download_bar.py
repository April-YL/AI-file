# [阶段一] UI 组件 — 底稿交付物下载栏
# 从 ui_app.py 的 _render_downloads 迁移
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 底稿交付物下载组件。"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_OUTPUT_SUFFIXES = ("_qc_report", "_qc_review", "_qc_annotated")
_INVALID_FILENAME_CHARS = __import__("re").compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_OUTPUT_STEM_LENGTH = 100


def _clean_output_stem(filename: str) -> str:
    """清理文件名作为输出前缀。"""
    import re

    stem = Path(filename).stem.strip()
    lowered = stem.lower()
    for suffix in _OUTPUT_SUFFIXES:
        if lowered.endswith(suffix):
            stem = stem[: -len(suffix)].rstrip()
            break
    stem = _INVALID_FILENAME_CHARS.sub("_", stem).strip(" .")
    stem = re.sub(r"_+", "_", stem)
    stem = stem[:_MAX_OUTPUT_STEM_LENGTH].rstrip(" ._")
    return stem or "workpaper"


def _output_filename(filename: str, run_id: str, output_type: str) -> str:
    extensions = {"report": "json", "review": "html", "annotated": "xlsx"}
    if output_type not in extensions:
        raise ValueError(f"Unsupported output type: {output_type}")
    base = _clean_output_stem(filename)
    return f"{base}_{run_id}_qc_{output_type}.{extensions[output_type]}"


def render_download_bar(
    filename: str,
    run_id: str,
    json_bytes: bytes,
    html_bytes: bytes,
    annotated_bytes: bytes | None = None,
) -> None:
    """渲染底稿交付物下载栏。

    Args:
        filename: 源文件名
        run_id: 运行编号（如 "20260707_143200"）
        json_bytes: 复核报告 JSON
        html_bytes: 复核报告 HTML
        annotated_bytes: 标注底稿（可选，CSV 输入时无）
    """
    st.subheader("底稿交付物")
    st.caption(f"运行编号：`{run_id}`")

    col1, col2, col3 = st.columns(3)

    with col1:
        if annotated_bytes:
            st.download_button(
                "标注底稿（Excel）",
                annotated_bytes,
                file_name=_output_filename(filename, run_id, "annotated"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
            st.caption("含 Comments 表 + 单元格批注，供复核定位")
        else:
            st.info("CSV 输入不生成标注底稿")

    with col2:
        st.download_button(
            "复核报告（HTML）",
            html_bytes,
            file_name=_output_filename(filename, run_id, "review"),
            mime="text/html",
            use_container_width=True,
        )
        st.caption("浏览器快速查看 Findings 明细")

    with col3:
        st.download_button(
            "系统报告（JSON）",
            json_bytes,
            file_name=_output_filename(filename, run_id, "report"),
            mime="application/json",
            use_container_width=True,
        )
        st.caption("结构化归档 / 系统集成")

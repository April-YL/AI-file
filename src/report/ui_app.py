"""固定资产质检 — 本地 Web 界面（Streamlit）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from report.export_json import export_report_json
from report.export_review_html import export_review_html
from report.pipeline import run_input_qc

st.set_page_config(
    page_title="固定资产质检",
    page_icon="📋",
    layout="wide",
)

st.title("固定资产质检 Agent")
st.caption("本地运行，底稿不上传云端。支持一次选择多份 Excel / CSV。")


def _severity_color(sev: str) -> str:
    return {
        "PASS": "green",
        "WARN": "orange",
        "FAIL": "red",
        "NEED_REVIEW": "blue",
    }.get(sev, "gray")


@st.cache_data(show_spinner=False)
def _run_qc_cached(
    file_bytes: bytes,
    filename: str,
    use_llm: bool,
    fa_sheet: str | None,
    summary_sheet: str | None,
    lead_sheet: str | None,
) -> tuple[dict, bytes, bytes]:
    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / filename
        inp.write_bytes(file_bytes)
        report = run_input_qc(
            str(inp),
            fa_sheet=fa_sheet or None,
            summary_sheet=summary_sheet or None,
            lead_sheet=lead_sheet or None,
            llm=use_llm,
        )
        json_path = Path(tmp) / "report.json"
        html_path = Path(tmp) / "report.html"
        export_report_json(report, json_path)
        export_review_html(report, html_path)
        data = report.to_dict()
        return (
            data,
            json_path.read_bytes(),
            html_path.read_bytes(),
        )


with st.sidebar:
    st.header("设置")
    use_llm = st.checkbox("启用大模型增强（需 API Key）", value=False)
    if use_llm:
        st.info("请在本机设置环境变量 FA_QC_LLM_API_KEY")
    with st.expander("高级：指定工作表名称（可选）"):
        fa_sheet = st.text_input("FA list 表名", "")
        summary_sheet = st.text_input("汇总表名", "")
        lead_sheet = st.text_input("Lead 表名", "")
    st.divider()
    st.markdown(
        "**建议试跑**\n\n"
        "仓库内样例：\n"
        "`tests/fixtures/workbook_with_lead.xlsx`"
    )

uploaded = st.file_uploader(
    "选择待质检底稿（可多选）",
    type=["xlsx", "xlsm", "csv"],
    accept_multiple_files=True,
)

if not uploaded:
    st.info("👆 点击上方区域选择文件，或拖拽文件到此处。")
    st.markdown(
        """
**支持格式**

| 格式 | 说明 |
| --- | --- |
| `.xlsx` / `.xlsm` | 整本底稿（推荐）：FA list + 汇总 + Lead |
| `.csv` | 仅固定资产清单 |

**输出**

- 质检结论与 findings 列表  
- PM/TE/SAD、CRA/TT 人工核对摘录（Excel 含 Lead 时）  
- 可下载 JSON 与 HTML 报告  
        """
    )
    st.stop()

if st.button("开始质检", type="primary", use_container_width=True):
    st.session_state["results"] = {}
    st.session_state["errors"] = {}
    progress = st.progress(0, text="准备中…")
    for idx, uf in enumerate(uploaded):
        progress.progress((idx) / len(uploaded), text=f"正在质检：{uf.name}")
        try:
            data, json_bytes, html_bytes = _run_qc_cached(
                uf.getvalue(),
                uf.name,
                use_llm,
                fa_sheet.strip() or None,
                summary_sheet.strip() or None,
                lead_sheet.strip() or None,
            )
            st.session_state.setdefault("results", {})[uf.name] = {
                "data": data,
                "json_bytes": json_bytes,
                "html_bytes": html_bytes,
            }
        except Exception as e:
            st.session_state.setdefault("errors", {})[uf.name] = str(e)
        progress.progress((idx + 1) / len(uploaded), text="完成")
    progress.empty()
    st.success(f"已完成 {len(uploaded)} 个文件的质检。")

results = st.session_state.get("results", {})
errors = st.session_state.get("errors", {})

if errors:
    for name, err in errors.items():
        st.error(f"**{name}**：{err}")

if not results:
    st.stop()

for name, bundle in results.items():
    data = bundle["data"]
    summary = data.get("summary", {})
    overall = summary.get("overall_severity", "—")

    with st.expander(f"📄 {name} — 总体：**{overall}**", expanded=len(results) == 1):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("资产行数", summary.get("total_records", 0))
        c2.metric("PASS", summary.get("pass_count", 0))
        c3.metric("WARN", summary.get("warn_count", 0))
        c4.metric("FAIL", summary.get("fail_count", 0))
        c5.metric("待复核", summary.get("need_review_count", 0))

        st.markdown(
            f"总体结论：<span style='color:{_severity_color(overall)};font-weight:bold'>"
            f"{overall}</span>",
            unsafe_allow_html=True,
        )

        dl1, dl2 = st.columns(2)
        base = Path(name).stem
        dl1.download_button(
            "下载 JSON 报告",
            bundle["json_bytes"],
            file_name=f"{base}_qc_report.json",
            mime="application/json",
            use_container_width=True,
        )
        dl2.download_button(
            "下载 HTML 核对页",
            bundle["html_bytes"],
            file_name=f"{base}_qc_review.html",
            mime="text/html",
            use_container_width=True,
        )

        tab1, tab2, tab3 = st.tabs(["问题清单", "人工核对摘录", "HTML 预览"])

        with tab1:
            issues = data.get("issues", [])
            if issues:
                st.dataframe(
                    [
                        {
                            "规则": i.get("dict_rule_code") or i.get("rule_id"),
                            "级别": i.get("severity"),
                            "说明": i.get("message"),
                            "字段": i.get("field"),
                            "行": i.get("source_row"),
                        }
                        for i in issues
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("未发现 issues。")

        with tab2:
            sections = data.get("manual_review_sections", [])
            if not sections:
                st.warning("本文件无人工核对摘录（CSV 或缺少 Lead 表）。")
            for sec in sections:
                st.subheader(sec.get("checklist_prompt", sec.get("title", "")))
                st.caption(sec.get("instruction", ""))
                items = sec.get("items") or []
                if items:
                    st.dataframe(items, use_container_width=True, hide_index=True)
                for note in sec.get("notes") or []:
                    st.warning(note)

        with tab3:
            st.components.v1.html(
                bundle["html_bytes"].decode("utf-8"),
                height=600,
                scrolling=True,
            )

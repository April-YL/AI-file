"""固定资产质检 — 本地 Web 界面（Streamlit）。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[1]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

import streamlit as st

from llm.env_loader import load_project_dotenv

load_project_dotenv()

from report.export_annotated_workbook import (
    COMMENTS_SHEET_NAME,
    FA_LIST_COMMENTS_SHEET_NAME,
    export_annotated_workbook,
)
from report.export_json import export_report_json
from report.export_review_html import export_review_html
from report.pipeline import run_input_qc
from report.procedure_labels import FINDING_UI_GROUPS, procedure_label

st.set_page_config(
    page_title="固定资产质检",
    page_icon="📋",
    layout="wide",
)

st.title("固定资产质检 Agent")
st.caption("面向质检人员：Agent 处理机械化问题，专业判断留人工复核。")


def _severity_color(sev: str) -> str:
    return {
        "PASS": "green",
        "WARN": "orange",
        "FAIL": "red",
        "NEED_REVIEW": "blue",
    }.get(sev, "gray")


def _findings_row(issue: dict) -> dict:
    from openpyxl.utils import get_column_letter

    cell = ""
    sr = issue.get("source_row")
    if sr:
        cell = f"${get_column_letter(2)}${sr}"
    return {
        "级别": issue.get("severity"),
        "工作表": issue.get("source_sheet"),
        "单元格": cell or "—",
        "规则": issue.get("dict_rule_code") or issue.get("rule_id"),
        "说明": issue.get("message"),
        "建议": issue.get("suggestion"),
    }


def _group_issues(issues: list[dict]) -> list[tuple[str, str, list[dict]]]:
    buckets: dict[str, list[dict]] = {code: [] for code, _ in FINDING_UI_GROUPS}
    other: list[dict] = []
    known = {code for code, _ in FINDING_UI_GROUPS}
    for issue in issues:
        if issue.get("severity") == "PASS":
            continue
        pc = issue.get("procedure_code") or ""
        if pc in known:
            buckets[pc].append(issue)
        else:
            other.append(issue)
    out: list[tuple[str, str, list[dict]]] = [
        (code, label, buckets[code]) for code, label in FINDING_UI_GROUPS if buckets[code]
    ]
    if other:
        out.append(("_other", "其他", other))
    return out


def _render_manual_review(data: dict) -> None:
    st.warning(
        "以下摘录 **须人工与 Canvas/A3/项目组底稿核对**；Agent **不自动判定**一致与否，"
        "结论为 NEED_REVIEW 不代表底稿已错。"
    )
    lead = data.get("lead_sheet_section") or {}
    basic = lead.get("basic_info_fields") or []
    if basic:
        st.subheader("Lead 基准信息（摘录）")
        st.dataframe(
            [
                {
                    "项目": f.get("label"),
                    "底稿值": f.get("value"),
                    "单元格": f.get("source_cell"),
                }
                for f in basic
            ],
            use_container_width=True,
            hide_index=True,
        )

    for sec in data.get("manual_review_sections") or []:
        code = sec.get("dict_rule_code", "")
        st.subheader(sec.get("checklist_prompt") or sec.get("title", code))
        st.caption(sec.get("instruction", ""))
        items = sec.get("items") or []
        if not items:
            for note in sec.get("notes") or []:
                st.warning(note)
            continue
        if items and "field_key" in items[0]:
            st.dataframe(
                [
                    {
                        "项目": it.get("label"),
                        "底稿值": it.get("workpaper_value"),
                        "Canvas/外部": it.get("canvas_or_external_value"),
                        "底稿单元格": it.get("workpaper_cell"),
                    }
                    for it in items
                ],
                use_container_width=True,
                hide_index=True,
            )
        elif items and "assertion" in items[0]:
            st.dataframe(
                [
                    {
                        "认定": it.get("assertion"),
                        "CRA": it.get("cra"),
                        "TT": it.get("tt"),
                        "来源": it.get("assertion_cell"),
                    }
                    for it in items
                ],
                use_container_width=True,
                hide_index=True,
            )


def _render_findings_grouped(data: dict) -> None:
    groups = _group_issues(data.get("issues", []))
    if not groups:
        st.success("未发现 FAIL / WARN / NEED_REVIEW 级 findings。")
        return
    for code, label, items in groups:
        default_expanded = code in ("SUMMARY", "K.00", "_other")
        with st.expander(f"{label}（{len(items)} 条）", expanded=default_expanded):
            st.dataframe(
                [_findings_row(i) for i in items],
                use_container_width=True,
                hide_index=True,
            )
            if code == "FA_LIST":
                st.caption(
                    f"底稿主表仅列 **FA list 共性问题** 合并行；逐条明细见 "
                    f"**{FA_LIST_COMMENTS_SHEET_NAME}**。"
                )


@st.cache_data(show_spinner=False)
def _run_qc_cached(
    file_bytes: bytes,
    filename: str,
    use_llm: bool,
    fa_sheet: str | None,
    summary_sheet: str | None,
    lead_sheet: str | None,
) -> tuple[dict, bytes, bytes, bytes | None]:
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
        annotated_bytes: bytes | None = None
        if inp.suffix.lower() in (".xlsx", ".xlsm"):
            ann_path = Path(tmp) / f"{inp.stem}_qc_annotated.xlsx"
            export_annotated_workbook(report, inp, ann_path)
            annotated_bytes = ann_path.read_bytes()
        return report.to_dict(), json_path.read_bytes(), html_path.read_bytes(), annotated_bytes


with st.sidebar:
    st.header("设置")
    use_llm = st.checkbox("启用大模型增强（可选，低优先级）", value=False)
    if use_llm:
        st.info("需配置 `.env` 中 `FA_QC_LLM_API_KEY`；不改变规则 severity。")
    with st.expander("高级：指定工作表名称（可选）"):
        fa_sheet = st.text_input("FA list 表名", "")
        summary_sheet = st.text_input("汇总表名", "")
        lead_sheet = st.text_input("Lead 表名", "")

uploaded = st.file_uploader(
    "选择待质检底稿（可多选）",
    type=["xlsx", "xlsm", "csv"],
    accept_multiple_files=True,
)

if not uploaded:
    st.info("👆 上传 Excel 底稿后开始质检。")
    st.markdown(
        f"""
**主交付**：`*_qc_annotated.xlsx`

| Sheet | 内容 |
| --- | --- |
| `{COMMENTS_SHEET_NAME}` | 其他程序 **逐条** + FA list **共性问题合并行** |
| `{FA_LIST_COMMENTS_SHEET_NAME}` | FA list findings **逐条明细** |
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
            data, json_bytes, html_bytes, ann_bytes = _run_qc_cached(
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
                "annotated_bytes": ann_bytes,
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
        c2.metric("FAIL", summary.get("fail_count", 0))
        c3.metric("WARN", summary.get("warn_count", 0))
        c4.metric("待复核", summary.get("need_review_count", 0))
        c5.metric(
            "Findings",
            summary.get("fail_count", 0)
            + summary.get("warn_count", 0)
            + summary.get("need_review_count", 0),
        )

        st.info(
            f"**标注底稿**含两张 Comments 表：① `{COMMENTS_SHEET_NAME}` "
            f"（其他程序逐条 + FA list 共性行）② `{FA_LIST_COMMENTS_SHEET_NAME}` "
            f"（FA list 逐条）。PM/TE/SAD、CRA 见「人工复核摘录」页签。"
        )

        base = Path(name).stem
        ann = bundle.get("annotated_bytes")
        if ann:
            st.download_button(
                "下载带标注底稿（主交付）",
                ann,
                file_name=f"{base}_qc_annotated.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        else:
            st.warning("CSV 不生成标注底稿。")

        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button("下载 JSON", bundle["json_bytes"], file_name=f"{base}_qc_report.json")
        with dl2:
            st.download_button("下载 Findings HTML", bundle["html_bytes"], file_name=f"{base}_qc_review.html")

        tab0, tab1, tab2, tab3 = st.tabs(
            ["Findings（分程序）", "人工复核摘录", "质检摘要", "HTML 预览"]
        )

        with tab0:
            _render_findings_grouped(data)

        with tab1:
            _render_manual_review(data)

        with tab2:
            lead = data.get("lead_sheet_section") or {}
            lqc = lead.get("lead_qc") or {}
            st.markdown(f"**Lead 规则整体**：{lqc.get('overall_severity', '—')}")
            sec = data.get("summary_sheet_section") or {}
            psp = sec.get("psp_completion") or {}
            if sec:
                st.markdown(f"**汇总页 AE-003**：{psp.get('overall_severity', '—')}")

        with tab3:
            st.components.v1.html(
                bundle["html_bytes"].decode("utf-8"),
                height=480,
                scrolling=True,
            )

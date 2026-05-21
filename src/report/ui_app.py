"""固定资产质检 — 本地 Web 界面（Streamlit）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from report.export_json import export_report_json
from report.export_review_html import export_review_html
from report.pipeline import run_input_qc
from report.procedure_labels import procedure_filter_options, procedure_label

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


_SEV_ORDER = {"FAIL": 0, "WARN": 1, "NEED_REVIEW": 2, "PASS": 3}


def _render_lead_section(sec: dict) -> None:
    """展示 ``lead_sheet_section``（与回归表同一套 lead_qc 结构）。"""
    lqc = sec.get("lead_qc") or {}
    overall = lqc.get("overall_severity", "—")

    st.markdown(
        f"**工作表** `{sec.get('source_sheet')}` · **版式** "
        f"`{sec.get('layout_variant') or '标准 SWP'}` · "
        f"**识别块** {', '.join(sec.get('blocks_detected') or []) or '—'}"
    )
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Lead 整体", overall)
    m2.metric("Lead findings", lqc.get("issue_count", 0))
    m3.metric("CRA 行", sec.get("cra_row_count", 0))
    m4.metric("引导表行", sec.get("movement_row_count", 0))
    m5.metric("预期分析行", len(sec.get("expectations") or []))

    st.caption(
        "结论含义：**FAIL**=规则明确不通过；**WARN**=建议确认；"
        "**NEED_REVIEW**=需与 Canvas/A3 等人工比对（非判错）；**PASS**=该项自动检查通过。"
    )

    rules = lqc.get("rules") or {}
    if rules:
        rows = []
        for rule_id, rsec in rules.items():
            rows.append(
                {
                    "字典码": rsec.get("dict_rule_code") or "—",
                    "规则": rule_id,
                    "结论": rsec.get("overall_severity"),
                    "finding 数": rsec.get("issue_count", 0),
                }
            )
        rows.sort(key=lambda r: (_SEV_ORDER.get(r["结论"], 9), r["规则"]))
        st.subheader("Lead 规则矩阵（按严重度排序）")
        st.dataframe(rows, use_container_width=True, hide_index=True)

        fail_warn = [r for r in rows if r["结论"] in ("FAIL", "WARN")]
        if fail_warn:
            st.subheader("需优先处理的规则")
            for r in fail_warn:
                rsec = rules[r["规则"]]
                issues = rsec.get("issues") or []
                title = f"{r['字典码']} · {r['规则']} — **{r['结论']}** ({len(issues)} 条)"
                with st.expander(title, expanded=r["结论"] == "FAIL"):
                    if issues:
                        st.dataframe(
                            [
                                {
                                    "级别": i.get("severity"),
                                    "字段": i.get("field"),
                                    "行": i.get("source_row"),
                                    "说明": i.get("message"),
                                    "建议": i.get("suggestion"),
                                }
                                for i in issues
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption("无明细 issue（overall 由规则汇总逻辑得出）。")

    if sec.get("ingest_notes"):
        with st.expander("ingest 说明"):
            for n in sec["ingest_notes"]:
                st.text(n)


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
    use_llm = st.checkbox("启用大模型增强（整底稿摘录进 prompt）", value=False)
    if use_llm:
        st.info(
            "请配置环境变量或项目根目录 `.env`：`FA_QC_LLM_API_KEY`、"
            "可选 `FA_QC_LLM_BASE_URL` / `FA_QC_LLM_MODEL`。"
            "Excel 整本底稿会将汇总、Lead、后推、清单等结构化摘录一并送入模型；"
            "**不改变**规则引擎的 FAIL/WARN 结论。"
        )
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

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
            [
                "问题清单",
                "汇总页 (PSP)",
                "Lead (K.00)",
                "人工核对摘录",
                "大模型增强",
                "HTML 预览",
            ]
        )

        with tab1:
            issues = data.get("issues", [])
            st.caption(
                "可按程序筛选；Lead 规则矩阵见 **Lead (K.00)** 页签。"
            )
            if issues:
                codes = [i.get("procedure_code") or "" for i in issues]
                opts = procedure_filter_options(codes)
                labels = {code: label for code, label in opts}
                proc_filter = st.selectbox(
                    "程序筛选",
                    options=[code for code, _ in opts],
                    format_func=lambda c: labels.get(c, c),
                    key=f"proc_filter_{name}",
                )
                shown = (
                    issues
                    if proc_filter == "ALL"
                    else [i for i in issues if (i.get("procedure_code") or "") == proc_filter]
                )
                st.caption(f"显示 {len(shown)} / {len(issues)} 条")
                st.dataframe(
                    [
                        {
                            "程序": procedure_label(i.get("procedure_code")),
                            "规则": i.get("dict_rule_code") or i.get("rule_id"),
                            "级别": i.get("severity"),
                            "工作表": i.get("source_sheet"),
                            "说明": i.get("message"),
                            "字段": i.get("field"),
                            "行": i.get("source_row"),
                        }
                        for i in shown
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("未发现 issues。")

        with tab2:
            sec = data.get("summary_sheet_section")
            if not sec:
                st.warning("本文件未写入汇总页块（未识别汇总表或当前为 CSV-only 流程）。")
            else:
                psp = sec.get("psp_completion") or {}
                st.markdown(
                    f"**工作表** `{sec.get('source_sheet')}` · **版式** `{sec.get('layout')}` · **程序行** {sec.get('program_count')}"
                )
                st.metric(
                    "AE-003 结论",
                    psp.get("overall_severity", "—"),
                    help="psp_completion 规则；无 finding 时为 PASS",
                )
                st.caption(f"AE-003 finding 数：{psp.get('issue_count', 0)}")
                if sec.get("ingest_notes"):
                    with st.expander("ingest 说明"):
                        for n in sec["ingest_notes"]:
                            st.text(n)
                binds = sec.get("column_bindings") or []
                if binds:
                    st.subheader("列绑定")
                    st.dataframe(binds, use_container_width=True, hide_index=True)
                progs = sec.get("programs") or []
                if progs:
                    st.subheader("程序表（解析结果）")
                    st.dataframe(progs, use_container_width=True, hide_index=True)
                if sec.get("programs_truncated"):
                    st.caption(
                        f"仅展示前 {sec.get('programs_in_report')} 行（共 {sec.get('program_count')} 行）。"
                    )
                psp_issues = psp.get("issues") or []
                if psp_issues:
                    st.subheader("AE-003 findings")
                    st.dataframe(psp_issues, use_container_width=True, hide_index=True)

        with tab3:
            sec = data.get("lead_sheet_section")
            if not sec:
                st.warning(
                    "本文件未写入 Lead 块（未识别 K.00 Lead 表，或当前为 CSV-only 流程）。"
                )
            else:
                _render_lead_section(sec)

        with tab4:
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

        with tab5:
            le = data.get("llm_enrichment")
            if not le:
                st.warning(
                    "未生成大模型增强内容。请勾选侧栏「启用大模型增强」并配置 "
                    "`FA_QC_LLM_API_KEY` 后重新质检。"
                )
            elif le.get("error"):
                st.error(f"大模型调用失败：{le['error']}")
            else:
                st.caption(
                    f"模型：{le.get('model', '—')} · "
                    f"摘录块：{', '.join(le.get('workbook_sections') or []) or '—'}"
                )
                st.subheader("执行摘要")
                st.write(le.get("executive_summary") or "—")
                if le.get("lead_focus_notes"):
                    st.subheader("Lead 关注提示")
                    for note in le["lead_focus_notes"]:
                        st.markdown(f"- {note}")
                notes = le.get("need_review_notes") or []
                if notes:
                    st.subheader("NEED_REVIEW 复核建议")
                    st.dataframe(notes, use_container_width=True, hide_index=True)

        with tab6:
            st.components.v1.html(
                bundle["html_bytes"].decode("utf-8"),
                height=600,
                scrolling=True,
            )

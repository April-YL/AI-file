"""固定资产质检 Agent 本地 Web 界面（Streamlit）。"""

from __future__ import annotations

import sys
import tempfile
import re
from datetime import datetime
from pathlib import Path
from time import perf_counter

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
from report.procedure_labels import group_findings_by_procedure
from rules.delivery_completion import DeliveryCompletionContext

st.set_page_config(
    page_title="固定资产质检",
    layout="wide",
)

# 规则/ingest 变更时递增，避免 @st.cache_data 返回旧质检结果。
_QC_CACHE_VERSION = "20260611-disposal-performance"
_OUTPUT_SUFFIXES = ("_qc_report", "_qc_review", "_qc_annotated")
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_OUTPUT_STEM_LENGTH = 100


def _new_run_id(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


def _clean_output_stem(filename: str) -> str:
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
    extensions = {
        "report": "json",
        "review": "html",
        "annotated": "xlsx",
    }
    if output_type not in extensions:
        raise ValueError(f"Unsupported output type: {output_type}")
    base = _clean_output_stem(filename)
    return f"{base}_{run_id}_qc_{output_type}.{extensions[output_type]}"


def _inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ey-black: #111111;
            --ey-gray-900: #242424;
            --ey-gray-700: #4f4f4f;
            --ey-gray-100: #f4f4f4;
            --ey-yellow: #ffe600;
            --qc-fail: #b42318;
            --qc-warn: #b54708;
            --qc-review: #175cd3;
            --qc-pass: #067647;
        }
        .main .block-container {
            padding-top: 1.25rem;
            max-width: 1440px;
        }
        .qc-topbar {
            background: var(--ey-black);
            border-left: 8px solid var(--ey-yellow);
            color: #ffffff;
            padding: 18px 22px;
            margin-bottom: 18px;
        }
        .qc-topbar h1 {
            margin: 0;
            font-size: 1.45rem;
            font-weight: 650;
            letter-spacing: 0;
        }
        .qc-topbar p {
            margin: 6px 0 0 0;
            color: #d6d6d6;
            font-size: 0.92rem;
        }
        .qc-card {
            border: 1px solid #dddddd;
            border-radius: 6px;
            background: #ffffff;
            padding: 14px 16px;
            min-height: 92px;
        }
        .qc-card-label {
            color: var(--ey-gray-700);
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }
        .qc-card-value {
            color: var(--ey-black);
            font-size: 1.65rem;
            font-weight: 700;
            line-height: 1.25;
            margin-top: 6px;
        }
        .qc-card-note {
            color: var(--ey-gray-700);
            font-size: 0.82rem;
            margin-top: 4px;
        }
        .qc-status {
            display: inline-block;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0;
            border: 1px solid transparent;
        }
        .qc-status.FAIL {
            color: var(--qc-fail);
            background: #fff3f0;
            border-color: #fecdca;
        }
        .qc-status.WARN {
            color: var(--qc-warn);
            background: #fff7ed;
            border-color: #fed7aa;
        }
        .qc-status.NEED_REVIEW {
            color: var(--qc-review);
            background: #eff8ff;
            border-color: #b2ddff;
        }
        .qc-status.PASS {
            color: var(--qc-pass);
            background: #ecfdf3;
            border-color: #abefc6;
        }
        .qc-procedure-row {
            border: 1px solid #e4e4e4;
            border-left: 5px solid var(--ey-yellow);
            border-radius: 6px;
            padding: 12px 14px;
            margin-bottom: 10px;
            background: #ffffff;
        }
        .qc-procedure-title {
            font-weight: 700;
            color: var(--ey-black);
            margin-bottom: 6px;
        }
        .qc-procedure-meta {
            color: var(--ey-gray-700);
            font-size: 0.88rem;
        }
        div.stButton > button[kind="primary"],
        div.stDownloadButton > button[kind="primary"] {
            background: var(--ey-black);
            color: #ffffff;
            border: 1px solid var(--ey-black);
            border-radius: 4px;
        }
        div.stButton > button[kind="primary"]:hover,
        div.stDownloadButton > button[kind="primary"]:hover {
            background: var(--ey-gray-900);
            border-color: var(--ey-gray-900);
            color: var(--ey-yellow);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _severity_class(sev: str | None) -> str:
    sev = (sev or "PASS").upper()
    return sev if sev in {"PASS", "WARN", "FAIL", "NEED_REVIEW"} else "PASS"


def _severity_badge(sev: str | None) -> str:
    value = _severity_class(sev)
    return f'<span class="qc-status {value}">{value}</span>'


def _finding_issues(data: dict) -> list[dict]:
    return [i for i in data.get("issues", []) if i.get("severity") != "PASS"]


def _finding_count(data: dict) -> int:
    return len(_finding_issues(data))


def _worst_severity(items: list[dict]) -> str:
    rank = {"FAIL": 4, "NEED_REVIEW": 3, "WARN": 2, "PASS": 1}
    severities = [i.get("severity", "PASS") for i in items]
    if not severities:
        return "PASS"
    return max(severities, key=lambda s: rank.get(s, 0))


def _count_severity(items: list[dict], severity: str) -> int:
    return sum(1 for item in items if item.get("severity") == severity)


def _findings_row(issue: dict) -> dict:
    from openpyxl.utils import get_column_letter

    cell = ""
    sr = issue.get("source_row")
    if sr:
        cell = f"${get_column_letter(2)}${sr}"
    return {
        "级别": issue.get("severity"),
        "工作表": issue.get("source_sheet"),
        "单元格": cell or "-",
        "规则": issue.get("dict_rule_code") or issue.get("rule_id"),
        "说明": issue.get("message"),
        "建议": issue.get("suggestion"),
    }


def _render_topbar() -> None:
    st.markdown(
        """
        <div class="qc-topbar">
          <h1>固定资产质检 Agent</h1>
          <p>本地工作台 · 规则判断优先 · 报告与标注副本同步交付</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_overview(name: str, data: dict) -> None:
    summary = data.get("summary", {})
    overall = summary.get("overall_severity", "PASS")
    findings = _finding_count(data)
    cards = [
        ("Overall", _severity_badge(overall), Path(name).name),
        ("Findings", str(findings), "FAIL / WARN / NEED_REVIEW"),
        ("FAIL", str(summary.get("fail_count", 0)), "明确不符合规则"),
        ("WARN", str(summary.get("warn_count", 0)), "需关注的风险提示"),
        ("NEED_REVIEW", str(summary.get("need_review_count", 0)), "需要人工复核"),
    ]
    cols = st.columns(5)
    for col, (label, value, note) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="qc-card">
                  <div class="qc-card-label">{label}</div>
                  <div class="qc-card-value">{value}</div>
                  <div class="qc-card-note">{note}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_downloads(name: str, bundle: dict) -> None:
    run_id = bundle["run_id"]
    st.subheader("交付物下载")
    st.caption(f"本次运行编号：`{run_id}`（三个下载文件使用同一编号）")
    ann = bundle.get("annotated_bytes")
    col1, col2, col3 = st.columns([1.35, 1, 1])
    with col1:
        if ann:
            st.download_button(
                "下载标注底稿",
                ann,
                file_name=_output_filename(name, run_id, "annotated"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        else:
            st.warning("CSV 输入不生成标注底稿。")
    with col2:
        st.download_button(
            "下载 JSON 报告",
            bundle["json_bytes"],
            file_name=_output_filename(name, run_id, "report"),
            use_container_width=True,
        )
    with col3:
        st.download_button(
            "下载 HTML 预览",
            bundle["html_bytes"],
            file_name=_output_filename(name, run_id, "review"),
            use_container_width=True,
        )


def _format_seconds(value: object) -> str:
    try:
        seconds = float(value or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"


def _render_runtime_timings(data: dict) -> None:
    timings = data.get("runtime_timings") or {}
    if not timings:
        return
    labels = [
        ("读取底稿", "ingest_seconds"),
        ("规则检查", "rules_seconds"),
        ("LLM", "llm_seconds"),
        ("JSON+HTML", "json_html_seconds"),
        ("标注副本", "annotated_seconds"),
        ("总耗时", "total_seconds"),
    ]
    parts = [
        f"{label}: {_format_seconds(timings.get(key))}"
        for label, key in labels
        if key in timings
    ]
    if not parts:
        return
    llm_note = "启用" if timings.get("llm_enabled") else "未启用"
    st.markdown(
        (
            '<div style="font-size: 0.78rem; color: #666666; '
            'margin-top: 0.35rem;">'
            f"耗时诊断（LLM {llm_note}）："
            + " · ".join(parts)
            + "</div>"
        ),
        unsafe_allow_html=True,
    )
    llm_details = timings.get("llm_details") or []
    detail_parts = []
    for item in llm_details:
        if not isinstance(item, dict):
            continue
        label = item.get("label") or item.get("key") or "LLM"
        calls = item.get("calls", 0)
        detail_parts.append(
            f"{label}: {_format_seconds(item.get('seconds'))} ({calls}次)"
        )
    if detail_parts:
        st.markdown(
            (
                '<div style="font-size: 0.74rem; color: #777777; '
                'margin-top: 0.15rem;">LLM 分项：'
                + " · ".join(detail_parts)
                + "</div>"
            ),
            unsafe_allow_html=True,
        )


def _render_procedure_summary(data: dict) -> None:
    st.subheader("程序分组概览")
    groups = group_findings_by_procedure(data.get("issues", []))
    if not groups:
        st.success("所有程序暂无 FAIL / WARN / NEED_REVIEW findings。")
        return
    for _code, label, items in groups:
        sev = _worst_severity(items)
        fail = _count_severity(items, "FAIL")
        warn = _count_severity(items, "WARN")
        review = _count_severity(items, "NEED_REVIEW")
        st.markdown(
            f"""
            <div class="qc-procedure-row">
              <div class="qc-procedure-title">{label} {_severity_badge(sev)}</div>
              <div class="qc-procedure-meta">
                {len(items)} findings · FAIL {fail} · WARN {warn} · NEED_REVIEW {review}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_manual_review(data: dict) -> None:
    st.warning(
        "以下摘录须人工与 Canvas/A3/项目组底稿核对；Agent 不自动判定外部资料一致性。"
    )
    lead = data.get("lead_sheet_section") or {}
    basic = lead.get("basic_info_fields") or []
    if basic:
        st.subheader("Lead 基准信息摘录")
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
    groups = group_findings_by_procedure(data.get("issues", []))
    if not groups:
        st.success("未发现 FAIL / WARN / NEED_REVIEW 级 findings。")
        return
    for code, label, items in groups:
        sev = _worst_severity(items)
        default_expanded = code in (
            "SUMMARY",
            "K.00",
            "K.01",
            "K.02.1",
            "K.02.2",
            "K.03.1",
            "_other",
        )
        title = f"{label} · {sev} · {len(items)} 条"
        with st.expander(title, expanded=default_expanded):
            st.dataframe(
                [_findings_row(i) for i in items],
                use_container_width=True,
                hide_index=True,
            )
            if code == "FA_LIST":
                st.caption(
                    f"主 Comments 表仅列 FA list 共性问题合并行；逐条明细见 "
                    f"{FA_LIST_COMMENTS_SHEET_NAME}。"
                )


def _render_qc_summary(data: dict) -> None:
    lead = data.get("lead_sheet_section") or {}
    lqc = lead.get("lead_qc") or {}
    if lqc:
        st.markdown(
            f"**K.00 Lead**：{lqc.get('overall_severity', 'PASS')}，"
            f"{lqc.get('issue_count', 0)} findings"
        )
    sec = data.get("summary_sheet_section") or {}
    psp = sec.get("psp_completion") or {}
    if psp:
        st.markdown(
            f"**汇总页 AE-003**：{psp.get('overall_severity', 'PASS')}，"
            f"{psp.get('issue_count', 0)} findings"
        )
    rf = data.get("rollforward_sheet_section") or {}
    rqc = rf.get("rollforward_qc") or {}
    if rqc:
        st.markdown(
            f"**K.01 后推**：{rqc.get('overall_severity', 'PASS')}，"
            f"{rqc.get('issue_count', 0)} findings"
        )
    addition = data.get("addition_sheet_section") or {}
    preview = addition.get("consistency_preview") or {}
    if addition:
        test = addition.get("addition_test") or {}
        sample = addition.get("addition_sample_output") or {}
        path = addition.get("addition_execution_path") or {}
        st.markdown(
            f"**K.02 新增测试**：{path.get('path_kind', 'unknown')}，"
            f"样本匹配 {preview.get('matched_count', 0)}/{preview.get('selected_count', 0)}，"
            f"关键项 {preview.get('key_item_selected_amount') or '—'} vs {preview.get('key_item_tested_amount') or '—'}"
        )
        st.caption(
            f"测试页 {test.get('source_sheet') or '—'} · 选样输出 {sample.get('source_sheet') or '—'}"
        )
    if not any((lqc, psp, rqc, addition)):
        st.info("暂无程序级摘要。")


@st.cache_data(show_spinner=False)
def _run_qc_cached(
    file_bytes: bytes,
    filename: str,
    use_llm: bool,
    fa_sheet: str | None,
    summary_sheet: str | None,
    lead_sheet: str | None,
    delivery_stage: str,
    cache_version: str,
) -> tuple[dict, bytes, bytes, bytes | None]:
    total_t0 = perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / filename
        inp.write_bytes(file_bytes)
        delivery_context = _build_delivery_context(
            delivery_stage=delivery_stage,
        )
        report = run_input_qc(
            str(inp),
            fa_sheet=fa_sheet or None,
            summary_sheet=summary_sheet or None,
            lead_sheet=lead_sheet or None,
            llm=use_llm,
            delivery_context=delivery_context,
        )
        json_html_t0 = perf_counter()
        json_path = Path(tmp) / "report.json"
        html_path = Path(tmp) / "report.html"
        export_report_json(report, json_path)
        export_review_html(report, html_path)
        json_html_seconds = perf_counter() - json_html_t0
        annotated_bytes: bytes | None = None
        annotated_seconds = 0.0
        if inp.suffix.lower() in (".xlsx", ".xlsm"):
            annotated_t0 = perf_counter()
            ann_path = Path(tmp) / f"{inp.stem}_qc_annotated.xlsx"
            export_annotated_workbook(report, inp, ann_path)
            annotated_bytes = ann_path.read_bytes()
            annotated_seconds = perf_counter() - annotated_t0
        data = report.to_dict()
        timings = dict(data.get("runtime_timings") or {})
        timings.update(
            {
                "json_html_seconds": round(json_html_seconds, 3),
                "annotated_seconds": round(annotated_seconds, 3),
                "total_seconds": round(perf_counter() - total_t0, 3),
            }
        )
        data["runtime_timings"] = timings
        return data, json_path.read_bytes(), html_path.read_bytes(), annotated_bytes


def _build_delivery_context(
    *,
    delivery_stage: str,
) -> DeliveryCompletionContext | None:
    if delivery_stage == "first":
        return DeliveryCompletionContext(stage="first")
    if delivery_stage == "final":
        return DeliveryCompletionContext(stage="final")
    return None


_inject_style()
_render_topbar()

with st.sidebar:
    st.header("设置")
    if st.button("清除质检缓存", help="规则更新后若结果未变，清缓存后重新运行。"):
        st.cache_data.clear()
        st.success("已清除缓存")
    use_llm = st.checkbox("启用大模型规则语义复核", value=False)
    if use_llm:
        st.info("LLM 将参与汇总页/Lead 等语义类规则复核，并生成摘要；不覆盖确定性规则 severity。")
    with st.expander("高级：指定工作表名称"):
        fa_sheet = st.text_input("FA list 表名", "")
        summary_sheet = st.text_input("汇总表名", "")
        lead_sheet = st.text_input("Lead 表名", "")

st.subheader("交付完成度")
delivery_stage = st.radio(
    "交付阶段",
    options=["none", "first", "final"],
    format_func=lambda v: {
        "none": "不检查交付完成度",
        "first": "首次交付",
        "final": "整体交付",
    }[v],
    horizontal=True,
)

uploaded = st.file_uploader(
    "选择待质检底稿",
    type=["xlsx", "xlsm", "csv"],
    accept_multiple_files=True,
)

if not uploaded:
    st.info("上传 Excel 或 CSV 后开始质检。")
    st.markdown(
        f"""
**主要交付物**：`*_qc_annotated.xlsx`

| Sheet | 内容 |
| --- | --- |
| `{COMMENTS_SHEET_NAME}` | 其他程序逐条 findings + FA list 共性问题合并行 |
| `{FA_LIST_COMMENTS_SHEET_NAME}` | FA list findings 逐条明细 |
        """
    )
    st.stop()

if st.button("开始质检", type="primary", use_container_width=True):
    st.session_state["results"] = {}
    st.session_state["errors"] = {}
    run_id = _new_run_id()
    progress = st.progress(0, text="准备中")
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
                delivery_stage,
                _QC_CACHE_VERSION,
            )
            st.session_state.setdefault("results", {})[uf.name] = {
                "data": data,
                "json_bytes": json_bytes,
                "html_bytes": html_bytes,
                "annotated_bytes": ann_bytes,
                "run_id": run_id,
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
    overall = (data.get("summary") or {}).get("overall_severity", "PASS")
    expander_title = f"{name} · 总体 {overall}"

    with st.expander(expander_title, expanded=len(results) == 1):
        _render_overview(name, data)
        st.divider()
        _render_downloads(name, bundle)
        _render_runtime_timings(data)
        st.divider()
        _render_procedure_summary(data)

        tab0, tab1, tab2, tab3 = st.tabs(
            ["Findings（分程序）", "人工复核摘录", "质检摘要", "HTML 预览"]
        )

        with tab0:
            _render_findings_grouped(data)

        with tab1:
            _render_manual_review(data)

        with tab2:
            _render_qc_summary(data)

        with tab3:
            st.components.v1.html(
                bundle["html_bytes"].decode("utf-8"),
                height=520,
                scrolling=True,
            )

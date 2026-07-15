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

from build_info import get_build_info
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
from rules.registry import get_by_rule_id

st.set_page_config(
    page_title="固定资产质检",
    layout="wide",
)

# 规则/ingest 变更时递增，避免 @st.cache_data 返回旧质检结果。
_QC_CACHE_VERSION = "20260623-ui-v2-ledger-viewer"
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
            --ey-gray-700: #4b5563;
            --ey-gray-500: #667085;
            --ey-gray-200: #dadde2;
            --ey-gray-100: #f4f4f4;
            --ey-yellow: #ffe600;
            --qc-high: #b42318;
            --qc-warn: #b54708;
            --qc-pass: #067647;
            --qc-other: #4b5563;
            --qc-unknown: #344054;
        }
        .main .block-container {
            padding-top: 1rem;
            max-width: 1400px;
        }
        .qc-topbar {
            background: var(--ey-black);
            border-left: 8px solid var(--ey-yellow);
            color: #ffffff;
            padding: 16px 20px;
            margin-bottom: 16px;
        }
        .qc-topbar h1 {
            margin: 0;
            font-size: 1.38rem;
            font-weight: 650;
            letter-spacing: 0;
        }
        .qc-topbar p {
            margin: 6px 0 0 0;
            color: #d6d6d6;
            font-size: 0.9rem;
        }
        .qc-file-header {
            border: 1px solid var(--ey-gray-200);
            border-left: 6px solid var(--ey-yellow);
            border-radius: 6px;
            background: #ffffff;
            padding: 16px 18px;
            margin: 8px 0 18px 0;
        }
        .qc-file-header h2 {
            margin: 0;
            color: var(--ey-black);
            font-size: 1.42rem;
            font-weight: 700;
            letter-spacing: 0;
        }
        .qc-file-header p {
            margin: 8px 0 0 0;
            color: var(--ey-gray-500);
            font-size: 0.9rem;
        }
        .qc-section-title {
            color: var(--ey-black);
            font-size: 1.18rem;
            font-weight: 700;
            margin: 10px 0 4px 0;
        }
        .qc-section-caption {
            color: var(--ey-gray-500);
            font-size: 0.86rem;
            margin: 0 0 10px 0;
        }
        .qc-card {
            border: 1px solid var(--ey-gray-200);
            border-left: 4px solid var(--accent, var(--ey-gray-700));
            border-radius: 6px;
            background: #ffffff;
            padding: 12px 14px;
            min-height: 78px;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }
        .qc-card-high { --accent: var(--qc-high); }
        .qc-card-warn { --accent: var(--qc-warn); }
        .qc-card-pass { --accent: var(--qc-pass); }
        .qc-card-other { --accent: var(--ey-gray-700); }
        .qc-card-unknown { --accent: var(--qc-unknown); }
        .qc-card-label {
            color: var(--ey-gray-500);
            font-size: 0.8rem;
            letter-spacing: 0;
        }
        .qc-card-value {
            color: var(--ey-black);
            font-size: 1.72rem;
            font-weight: 750;
            line-height: 1.18;
            margin-top: 4px;
        }
        .qc-card-note {
            color: var(--ey-gray-500);
            font-size: 0.78rem;
            margin-top: 4px;
        }
        .qc-ledger-note {
            border-left: 4px solid var(--ey-yellow);
            background: #fffbea;
            color: var(--ey-gray-900);
            padding: 10px 12px;
            border-radius: 4px;
            font-size: 0.86rem;
            margin: 8px 0 12px 0;
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
            color: #b42318;
            background: #fff3f0;
            border-color: #fecdca;
        }
        .qc-status.WARN {
            color: #b54708;
            background: #fff7ed;
            border-color: #fed7aa;
        }
        .qc-status.NEED_REVIEW {
            color: #175cd3;
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
        div[data-testid="stExpander"] {
            border-radius: 6px;
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


_UI_FINDING_GROUPS: tuple[tuple[str, str], ...] = (
    ("audit", "高优先级问题"),
    ("manual", "需人工判断"),
    ("workpaper", "底稿规范问题"),
    ("system", "系统诊断"),
)

_SYSTEM_FINDING_KEYWORDS = (
    "annotation",
    "output",
    "diagnostic",
    "source_row",
    "export",
    "readability",
    "批注",
    "不可写",
    "无法写入",
    "英文残留",
    "导出",
    "运行诊断",
    "读取失败",
    "sheet 匹配失败",
)

_AUDIT_FINDING_KEYWORDS = (
    "reconciliation",
    "difference",
    "sample_match",
    "amount",
    "net_value",
    "depreciation",
    "rollforward",
    "asset_value_consistency",
    "tod_difference",
    "金额",
    "差异",
    "超过 sad",
    "a3",
    "tb",
    "lead",
    "后推",
    "折旧",
    "净值",
    "样本",
    "期间",
    "勾稽",
)

_MANUAL_FINDING_KEYWORDS = (
    "semantic",
    "review",
    "waiver",
    "notes",
    "explanation",
    "homogeneity",
    "classification",
    "cra",
    "sufficiency",
    "人工",
    "判断",
    "说明是否充分",
    "理由",
    "语义",
    "索引",
    "证据充分性",
    "无法自动判断",
)

_WORKPAPER_FINDING_KEYWORDS = (
    "required_fields",
    "columns_complete",
    "exists",
    "package_complete",
    "delivery_standard",
    "psp_completion",
    "template",
    "field",
    "缺少字段",
    "表头不完整",
    "未填写",
    "格式",
    "底稿结构",
    "工作表缺失",
    "程序包不完整",
)

_CHECKPOINT_STATUS_DONE = "已执行"
_CHECKPOINT_STATUS_MISSING = "数据不足，未执行"
_CHECKPOINT_STATUS_NA = "暂不适用"


def _issue_search_text(issue: dict) -> str:
    parts = [
        issue.get("rule_id"),
        issue.get("dict_rule_code"),
        issue.get("procedure_code"),
        issue.get("source_sheet"),
        issue.get("message"),
        issue.get("suggestion"),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k.lower() in text for k in keywords)


def _is_prompt_only_checkpoint(issue: dict) -> bool:
    """Mapping 中 N/No 类质检点仅作为 UI 提示项展示。"""
    checkpoint = str(issue.get("qc_checkpoint") or "").strip().lower()
    return checkpoint.startswith("n-") or checkpoint.startswith("no-")


def _is_fa_list_issue(issue: dict) -> bool:
    return str(issue.get("procedure_code") or "").upper() == "FA_LIST"


def _is_by_item_issue(rule_id: str) -> bool:
    return rule_id.startswith(_BY_ITEM_RULE_PREFIX_V2)


def _classify_finding_for_ui(issue: dict) -> str:
    """Return a UI-only priority bucket without mutating the finding."""
    text = _issue_search_text(issue)
    severity = str(issue.get("severity") or "").upper()
    if _has_any_keyword(text, _SYSTEM_FINDING_KEYWORDS):
        return "system"
    if severity == "FAIL" and _has_any_keyword(text, _AUDIT_FINDING_KEYWORDS):
        return "audit"
    if severity == "NEED_REVIEW" or _has_any_keyword(text, _MANUAL_FINDING_KEYWORDS):
        return "manual"
    if _has_any_keyword(text, _AUDIT_FINDING_KEYWORDS):
        return "audit"
    if _has_any_keyword(text, _WORKPAPER_FINDING_KEYWORDS):
        return "workpaper"
    if severity == "FAIL":
        return "audit"
    if severity == "WARN":
        return "workpaper"
    return "manual"


def _group_findings_by_ui_priority(data: dict) -> dict[str, list[dict]]:
    groups = {key: [] for key, _label in _UI_FINDING_GROUPS}
    rank = {"FAIL": 0, "NEED_REVIEW": 1, "WARN": 2, "PASS": 3}
    for issue in _finding_issues(data):
        groups[_classify_finding_for_ui(issue)].append(issue)
    for items in groups.values():
        items.sort(
            key=lambda i: (
                rank.get(str(i.get("severity")), 9),
                str(i.get("rule_id") or ""),
            )
        )
    return groups


def _render_findings_summary(data: dict) -> None:
    st.subheader("Findings 汇总")
    groups = _group_findings_by_ui_priority(data)
    metrics = [("Findings 总数", _finding_count(data), "不含 PASS")]
    metrics.extend(
        (label, len(groups[key]), "仅用于 UI 展示优先级")
        for key, label in _UI_FINDING_GROUPS
    )
    cols = st.columns(len(metrics))
    for col, (label, value, note) in zip(cols, metrics):
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
    st.caption("分类只用于页面展示，不修改 severity、原始 finding 或 JSON 报告。")


def _render_priority_findings(data: dict) -> None:
    st.subheader("优先处理 Findings")
    groups = _group_findings_by_ui_priority(data)
    if not any(groups.values()):
        st.success("未发现 FAIL / WARN / NEED_REVIEW 级 findings。")
        return
    for key, label in _UI_FINDING_GROUPS:
        items = groups[key]
        if not items:
            continue
        expanded = key in {"audit", "manual"}
        with st.expander(f"{label} · {len(items)} 条", expanded=expanded):
            st.dataframe(
                [_findings_row(i) for i in items],
                use_container_width=True,
                hide_index=True,
            )


def _issues_for_checkpoint(
    data: dict,
    *,
    procedures: set[str] | None = None,
    rule_ids: set[str] | None = None,
    rule_prefixes: tuple[str, ...] = (),
) -> list[dict]:
    out = []
    for issue in _finding_issues(data):
        procedure = str(issue.get("procedure_code") or "")
        rule_id = str(issue.get("rule_id") or "")
        if procedures and procedure in procedures:
            out.append(issue)
            continue
        if rule_ids and rule_id in rule_ids:
            out.append(issue)
            continue
        if rule_prefixes and rule_id.startswith(rule_prefixes):
            out.append(issue)
    return out


def _checkpoint_summary_text(items: list[dict]) -> str:
    if not items:
        return "未发现异常"
    groups = {
        key: len(value)
        for key, value in _group_findings_by_ui_priority({"issues": items}).items()
    }
    audit_count = groups.get("audit", 0)
    if audit_count:
        return f"产生 {len(items)} 条 findings，其中 {audit_count} 条高优先级问题"
    return f"产生 {len(items)} 条 findings"


def _has_section(data: dict, key: str) -> bool:
    return bool(data.get(key))


def _lead_has_materiality(data: dict) -> bool:
    lead = data.get("lead_sheet_section") or {}
    for field in lead.get("basic_info_fields") or []:
        text = f"{field.get('label') or ''} {field.get('value') or ''}".lower()
        if any(k in text for k in ("te", "sad", "tt", "threshold", "materiality")):
            return True
    return False


def _checkpoint_row(
    program: str,
    checkpoint: str,
    status: str,
    summary: str,
    findings: list[dict] | None = None,
    dependencies: str = "",
) -> dict:
    findings = findings or []
    return {
        "程序": program,
        "检查点": checkpoint,
        "执行状态": status,
        "结果摘要": summary,
        "findings 数量": len(findings),
        "依赖资料": dependencies,
    }


def _build_checkpoint_rows(data: dict, bundle: dict, delivery_stage: str) -> list[dict]:
    rows: list[dict] = []

    delivery_issues = _issues_for_checkpoint(
        data,
        rule_ids={"first_delivery_standard", "final_delivery_standard"},
    )
    delivery_status = (
        _CHECKPOINT_STATUS_NA if delivery_stage == "none" else _CHECKPOINT_STATUS_DONE
    )
    rows.append(
        _checkpoint_row(
            "全局",
            "交付完整性",
            delivery_status,
            "本轮未检查交付完整性"
            if delivery_status == _CHECKPOINT_STATUS_NA
            else _checkpoint_summary_text(delivery_issues),
            delivery_issues,
            "交付阶段",
        )
    )

    external_status = (
        _CHECKPOINT_STATUS_DONE if _lead_has_materiality(data) else _CHECKPOINT_STATUS_MISSING
    )
    external_summary = (
        "TE/SAD 当前优先从 Lead 识别；A3 映射、CRA 模板导入后续接入"
        if external_status == _CHECKPOINT_STATUS_DONE
        else "缺少可识别 Lead/TE/SAD；A3 映射、CRA 模板导入后续接入"
    )
    rows.append(
        _checkpoint_row(
            "全局",
            "外部参数完整性",
            external_status,
            external_summary,
            [],
            "TE/SAD、A3、CRA、Lead",
        )
    )

    annotation_available = bool(bundle.get("annotated_bytes"))
    annotation_status = _CHECKPOINT_STATUS_DONE if annotation_available else _CHECKPOINT_STATUS_NA
    annotation_summary = (
        "已生成标注底稿" if annotation_available else "当前输入不生成标注底稿或标注产物不可用"
    )
    rows.append(
        _checkpoint_row(
            "全局",
            "批注写入状态",
            annotation_status,
            annotation_summary,
            [],
            "Excel 标注副本",
        )
    )

    deliverables_ok = bool(bundle.get("json_bytes")) and bool(bundle.get("html_bytes"))
    rows.append(
        _checkpoint_row(
            "全局",
            "交付物生成状态",
            _CHECKPOINT_STATUS_DONE if deliverables_ok else _CHECKPOINT_STATUS_MISSING,
            "已生成报告 / HTML / 标注底稿" if deliverables_ok else "交付物生成不完整",
            [],
            "JSON、HTML、标注底稿",
        )
    )

    checkpoint_specs = [
        ("汇总页 / PSP / AE", "PSP 执行与拒绝理由", "summary_sheet_section", {"SUMMARY"}, (), "汇总页、工作表清单"),
        ("K.00 Lead", "Lead 基准信息与分析", "lead_sheet_section", {"K.00"}, (), "Lead、TE/SAD、CRA"),
        ("FA 清单", "FA 清单基础检查", None, {"FA_LIST"}, ("fa_list_",), "FA list"),
        ("K.01 后推", "后推与跨表勾稽", "rollforward_sheet_section", {"K.01"}, ("rollforward_",), "K.01、FA list、TB、SAD"),
        ("K.02.1 新增测试", "新增测试", "addition_sheet_section", {"K.02.1", "K.02.1a"}, ("addition_",), "新增清单、K.02.1、K.02.1a、K.01"),
        ("K.02.2 处置测试", "处置测试", None, {"K.02.2", "K.02.2a"}, ("disposal_",), "处置清单、K.02.2、K.02.2a、K.01"),
        ("K.03 折旧测试", "折旧测试", None, {"K.03.1", "K.03.2"}, ("sap_", "depreciation_tod", "depreciation_by_item"), "K.03.1、K.03.2、SAD"),
        ("K.03.3 折旧政策复核", "折旧政策复核", None, {"K.03.3"}, ("depreciation_policy",), "K.03.3、FA list"),
    ]
    matched_issue_ids: set[int] = set()
    for program, checkpoint, section_key, procedures, prefixes, dependencies in checkpoint_specs:
        items = _issues_for_checkpoint(data, procedures=procedures, rule_prefixes=prefixes)
        matched_issue_ids.update(id(i) for i in items)
        executed = bool(items) or (section_key is not None and _has_section(data, section_key))
        status = _CHECKPOINT_STATUS_DONE if executed else _CHECKPOINT_STATUS_MISSING
        rows.append(
            _checkpoint_row(
                program,
                checkpoint,
                status,
                _checkpoint_summary_text(items) if executed else f"缺少 {dependencies}，无法执行",
                items,
                dependencies,
            )
        )

    other_items = [i for i in _finding_issues(data) if id(i) not in matched_issue_ids]
    if other_items:
        rows.append(
            _checkpoint_row(
                "其他",
                "其他已识别检查",
                _CHECKPOINT_STATUS_DONE,
                _checkpoint_summary_text(other_items),
                other_items,
                "当前系统已识别的其他程序",
            )
        )
    return rows


def _render_system_diagnostics(data: dict, bundle: dict) -> None:
    with st.expander("系统诊断 / 输出质量", expanded=False):
        _render_output_quality(data)
        _render_runtime_timings(data)


def _render_artifact_preview(bundle: dict) -> None:
    with st.expander("HTML 交付物预览", expanded=False):
        st.caption("仅用于查看导出 HTML 的呈现效果；页面 Findings 明细是交互查看入口。")
        st.components.v1.html(
            bundle["html_bytes"].decode("utf-8"),
            height=520,
            scrolling=True,
        )


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
        ("最高提示级别", _severity_badge(overall), Path(name).name),
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



def _render_output_quality(data: dict) -> None:
    summary = data.get("summary") or {}
    ledger = _execution_ledger(data) or {}
    ledger_summary = ledger.get("summary") or {}
    timings = data.get("runtime_timings") or {}
    llm_enabled = "启用" if timings.get("llm_enabled") else "未启用"
    metrics = [
        ("整体级别", summary.get("overall_severity", "未生成"), "来自 summary", "other"),
        ("Findings", _finding_count(data), "不含 PASS", "warn"),
        (
            "本次记录执行点",
            ledger_summary.get("total_observed_checkpoints", len(ledger.get("items") or [])),
            "来自 execution_ledger",
            "other",
        ),
        ("LLM", llm_enabled, "仅表示是否启用辅助复核", "other"),
    ]
    st.markdown("**输出质量**")
    cols = st.columns(len(metrics))
    for col, (label, value, note, tone) in zip(cols, metrics):
        with col:
            _render_card(label, value, note, tone)

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




# UI v2 / Execution Ledger viewer overrides.
# These helpers are presentation-only: they must not mutate findings, severity,
# execution_ledger, rule results, or JSON report output.
_UI_FINDING_BUCKETS_V2: tuple[tuple[str, str, str, str], ...] = (
    ("high", "高优先级问题", "优先查看", "high"),
    ("manual", "需人工处理", "需复核", "warn"),
    ("other", "其他提示", "一般提示", "other"),
)

_HIGH_PRIORITY_RULE_IDS_V2 = {
    "psp_completion",
    "materiality_consistency",
    "risk_threshold_consistency",
    "lead_check_with_a3_row",
    "lead_rollforward_tb_reconciliation",
    "rollforward_difference_over_sad",
    "rollforward_fa_list_reconciliation",
    "rollforward_depreciation_pl_reconciliation",
    "addition_rollforward_reconciliation",
    "addition_sample_pool_purchase_amount_match",
    "disposal_rollforward_reconciliation",
    "disposal_summary_reconciliation",
    "disposal_sample_pool_amount_match",
    "k03_policy_change_without_explanation",
}

_MANUAL_KEYWORDS_V2 = (
    "semantic",
    "llm",
    "review",
    "manual",
    "人工",
    "复核",
    "判断",
    "语义",
    "解释",
    "说明是否充分",
    "证据充分性",
    "cra",
)
_BY_ITEM_RULE_PREFIX_V2 = "k03_tod_by_item_"

_LEDGER_ALLOWED_STATUSES = {"EXECUTED", "DATA_INSUFFICIENT", "NOT_APPLICABLE"}
_LEDGER_STATUS_LABELS = {
    "EXECUTED": "已执行",
    "DATA_INSUFFICIENT": "数据不足，未执行",
    "NOT_APPLICABLE": "暂不适用",
}
_LEDGER_STATUS_CARD_META = (
    ("total_observed_checkpoints", "本次记录执行点", "来自 execution_ledger", "other"),
    ("executed", "已执行", "仅表示规则流程已运行", "pass"),
    ("data_insufficient", "数据不足，未执行", "资料不足或未识别", "warn"),
    ("not_applicable", "暂不适用", "当前场景不适用", "other"),
)
_LEDGER_STATUS_ORDER = {
    "DATA_INSUFFICIENT": 0,
    "EXECUTED_WITH_FINDINGS": 1,
    "NOT_APPLICABLE": 2,
    "EXECUTED_NO_FINDINGS": 3,
    "UNKNOWN": 4,
}
_FORBIDDEN_EXECUTION_NOTE_TERMS = (
    "已完成",
    "完成",
    "成功",
    "结束",
    "通过",
    "结论",
    "complete",
    "completed",
    "success",
    "passed",
    "conclusion",
)

_PROCEDURE_ORDER = (
    "全局 / 交付检查",
    "K.00 Lead",
    "K.01 后推",
    "FA list",
    "K.02.1 新增测试",
    "K.02.2 处置测试",
    "K.03.1 SAP",
    "K.03.2 折旧测试",
    "K.03.3 折旧政策复核",
    "LLM 辅助复核",
    "其他",
)

_PROCEDURE_LABELS = {
    "GLOBAL": "全局 / 交付检查",
    "SUMMARY": "全局 / 交付检查",
    "K.00": "K.00 Lead",
    "K.01": "K.01 后推",
    "FA_LIST": "FA list",
    "FA list": "FA list",
    "FA 清单": "FA list",
    "K.02": "K.02.1 新增测试",
    "K.02.1": "K.02.1 新增测试",
    "K.02.1 新增测试": "K.02.1 新增测试",
    "K.02.2": "K.02.2 处置测试",
    "K.02.2 处置测试": "K.02.2 处置测试",
    "K.03.1": "K.03.1 SAP",
    "K.03.1 SAP": "K.03.1 SAP",
    "K.03": "K.03.2 折旧测试",
    "K.03 折旧测试": "K.03.2 折旧测试",
    "K.03.2": "K.03.2 折旧测试",
    "K.03.2 折旧测试": "K.03.2 折旧测试",
    "K.03.3": "K.03.3 折旧政策复核",
    "K.03.3 折旧政策复核": "K.03.3 折旧政策复核",
    "LLM 辅助复核": "LLM 辅助复核",
    "其他": "其他",
}

# Display mapping only. It improves readability but never creates execution rows
# and never infers whether a rule should have run.
_RULE_DISPLAY: dict[str, tuple[str, str, str]] = {
    "first_delivery_standard": ("全局 / 交付检查", "首次交付资料完整性", "交付资料检查"),
    "final_delivery_standard": ("全局 / 交付检查", "最终交付资料完整性", "交付资料检查"),
    "psp_completion": ("汇总页 / PSP / AE", "PSP 执行与拒绝理由", "程序状态检查"),
    "addition_test_package_complete": ("汇总页 / PSP / AE", "新增测试程序包完整性", "程序包完整性检查"),
    "disposal_test_package_complete": ("汇总页 / PSP / AE", "处置测试程序包完整性", "程序包完整性检查"),
    "fa_list_required_fields": ("FA 清单", "必填字段完整性", "字段完整性检查"),
    "unique_asset_id": ("FA 清单", "资产编号唯一性", "重复值检查"),
    "asset_amount_non_negative": ("FA 清单", "金额非负检查", "金额合理性检查"),
    "asset_value_consistency": ("FA 清单", "原值、累计折旧、减值、净值关系", "金额重算"),
    "useful_life_positive": ("FA 清单", "使用寿命有效性", "参数合理性检查"),
    "salvage_rate_range": ("FA 清单", "残值率范围", "参数合理性检查"),
    "lead_required_fields": ("K.00 Lead", "Lead 必填字段完整性", "字段完整性检查"),
    "lead_ingest_readability": ("K.00 Lead", "Lead 读取质量", "读取诊断"),
    "materiality_consistency": ("K.00 Lead", "TE / SAD 参数一致性", "参数勾稽核对"),
    "risk_threshold_consistency": ("K.00 Lead", "风险阈值一致性", "参数勾稽核对"),
    "lead_analysis_date_after_period_end": ("K.00 Lead", "分析日期是否晚于期末", "期间比对"),
    "lead_tt_overall_min": ("K.00 Lead", "TT 最低阈值复核", "阈值判断"),
    "lead_tt_gam_range": ("K.00 Lead", "TT / GAM 区间复核", "阈值判断"),
    "lead_expectation_analysis": ("K.00 Lead", "预期分析记录", "字段与说明检查"),
    "lead_expectation_basis_present": ("K.00 Lead", "预期基础是否记录", "说明完整性检查"),
    "lead_expectation_vs_movement_review": ("K.00 Lead", "预期与变动方向复核", "趋势比对"),
    "lead_volatility_threshold_link": ("K.00 Lead", "波动阈值关联", "阈值关联检查"),
    "lead_movement_rows_complete": ("K.00 Lead", "变动行完整性", "行项目完整性检查"),
    "lead_movement_consistency": ("K.00 Lead", "Lead 变动金额一致性", "金额勾稽核对"),
    "lead_movement_notes_required": ("K.00 Lead", "重大变动说明记录", "说明完整性检查"),
    "lead_check_with_a3_row": ("K.00 Lead", "Lead 与 A3 行勾稽", "金额勾稽核对"),
    "unexpected_movement_investigation": ("K.00 Lead", "异常变动调查记录", "说明完整性检查"),
    "lead_fluctuation_notes_refs": ("K.00 Lead", "波动说明引用", "索引与引用检查"),
    "lead_adjustment_internal_consistency": ("K.00 Lead", "调整事项内部一致性", "金额勾稽核对"),
    "lead_rollforward_tb_reconciliation": ("K.00 Lead", "Lead 后推与 TB 勾稽", "金额勾稽核对"),
    "rollforward_exists": ("K.01 后推", "后推表存在性", "工作表识别"),
    "rollforward_columns_complete": ("K.01 后推", "后推表字段完整性", "字段完整性检查"),
    "rollforward_abnormal_amounts": ("K.01 后推", "后推金额异常", "金额合理性检查"),
    "rollforward_fa_list_reconciliation": ("K.01 后推", "后推与 FA 清单勾稽", "金额勾稽核对"),
    "rollforward_difference_over_sad": ("K.01 后推", "后推差异超过 SAD", "阈值判断"),
    "rollforward_depreciation_pl_reconciliation": ("K.01 后推", "折旧与损益表勾稽", "金额勾稽核对"),
    "rollforward_notes_review": ("K.01 后推", "后推说明复核", "LLM 辅助复核"),
    "addition_required_fields": ("K.02.1 新增测试", "新增清单字段完整性", "字段完整性检查"),
    "addition_population_homogeneity": ("K.02.1 新增测试", "新增总体同质性", "分类一致性检查"),
    "addition_rollforward_reconciliation": ("K.02.1 新增测试", "新增与后推勾稽", "金额勾稽核对"),
    "addition_sample_match": ("K.02.1 新增测试", "新增样本匹配", "样本比对"),
    "addition_sample_pool_purchase_amount_match": ("K.02.1 新增测试", "新增样本池金额匹配", "金额勾稽核对"),
    "addition_sampling_te_cra_consistency": ("K.02.1 新增测试", "新增抽样 TE / CRA 一致性", "参数一致性检查"),
    "addition_sampling_assertions_scope": ("K.02.1 新增测试", "新增测试认定覆盖", "程序覆盖检查"),
    "addition_sample_replacement_reason": ("K.02.1 新增测试", "新增替换样本原因", "说明完整性检查"),
    "addition_llm_review": ("K.02.1 新增测试", "新增测试说明复核", "LLM 辅助复核"),
    "disposal_required_fields": ("K.02.2 处置测试", "处置清单字段完整性", "字段完整性检查"),
    "disposal_sample_match": ("K.02.2 处置测试", "处置样本匹配", "样本比对"),
    "disposal_reconciliation_readability": ("K.02.2 处置测试", "处置勾稽表读取质量", "读取诊断"),
    "disposal_reconciliation_formula_source": ("K.02.2 处置测试", "处置勾稽公式来源", "公式来源检查"),
    "disposal_net_value_recalculation": ("K.02.2 处置测试", "处置净值重算", "金额重算"),
    "disposal_rollforward_reconciliation": ("K.02.2 处置测试", "处置与后推勾稽", "金额勾稽核对"),
    "disposal_difference_investigation": ("K.02.2 处置测试", "处置差异调查", "说明完整性检查"),
    "disposal_list_net_value_recalculation": ("K.02.2 处置测试", "处置清单净值重算", "金额重算"),
    "disposal_method_classification": ("K.02.2 处置测试", "处置方式分类", "分类一致性检查"),
    "disposal_other_reduction_over_tt": ("K.02.2 处置测试", "其他减少超过 TT", "阈值判断"),
    "disposal_sample_pool_amount_match": ("K.02.2 处置测试", "处置样本池金额匹配", "金额勾稽核对"),
    "disposal_sampling_te_cra_consistency": ("K.02.2 处置测试", "处置抽样 TE / CRA 一致性", "参数一致性检查"),
    "disposal_sample_replacement_reason": ("K.02.2 处置测试", "处置替换样本原因", "说明完整性检查"),
    "disposal_test_attributes_complete": ("K.02.2 处置测试", "处置测试属性完整性", "字段完整性检查"),
    "disposal_test_amount_recalculation": ("K.02.2 处置测试", "处置测试金额重算", "金额重算"),
    "disposal_sale_evidence_complete": ("K.02.2 处置测试", "处置销售证据完整性", "证据完整性检查"),
    "disposal_exception_followup": ("K.02.2 处置测试", "处置例外跟进记录", "说明完整性检查"),
    "disposal_llm_review": ("K.02.2 处置测试", "处置测试说明复核", "LLM 辅助复核"),
    "k03_tod_by_item_detail_unreadable": ("K.03 折旧测试", "折旧明细读取质量", "读取诊断"),
    "k03_tod_by_item_required_fields": ("K.03 折旧测试", "折旧测试字段完整性", "字段完整性检查"),
    "k03_tod_by_item_difference_column": ("K.03 折旧测试", "折旧差异列检查", "字段完整性检查"),
    "k03_tod_by_item_sad_unavailable": ("K.03 折旧测试", "折旧测试 SAD 可用性", "参数可用性检查"),
    "k03_tod_by_item_difference_over_sad": ("K.03 折旧测试", "折旧差异超过 SAD", "阈值判断"),
    "k03_tod_by_item_conclusion_missing": ("K.03 折旧测试", "折旧测试说明记录", "说明完整性检查"),
    "k03_tod_by_item_total_difference_over_sad": ("K.03 折旧测试", "折旧总体差异超过 SAD", "阈值判断"),
    "k03_tod_by_item_rollforward_depreciation": ("K.03 折旧测试", "折旧与后推勾稽", "金额勾稽核对"),
    "k03_policy_sheet_missing": ("K.03.3 折旧政策复核", "折旧政策表存在性", "工作表识别"),
    "k03_policy_table_unreadable": ("K.03.3 折旧政策复核", "折旧政策表读取质量", "读取诊断"),
    "k03_policy_sections_incomplete": ("K.03.3 折旧政策复核", "折旧政策区块完整性", "结构完整性检查"),
    "k03_policy_difference_marker": ("K.03.3 折旧政策复核", "折旧政策差异标记", "政策一致性检查"),
    "k03_policy_change_without_explanation": ("K.03.3 折旧政策复核", "政策变更说明", "说明完整性检查"),
    "k03_policy_fa_life_out_of_range": ("K.03.3 折旧政策复核", "资产寿命与政策范围", "资产类别 / 寿命比对"),
    "k03_policy_fa_salvage_mismatch": ("K.03.3 折旧政策复核", "残值率与政策一致性", "资产类别 / 残值率比对"),
    "k03_policy_fa_unit_or_category_review": ("K.03.3 折旧政策复核", "资产单位或类别复核", "分类一致性检查"),
    "k03_policy_obvious_anomaly": ("K.03.3 折旧政策复核", "折旧政策明显异常", "政策一致性检查"),
}


def _html(value: object) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _render_card(label: str, value: object, note: str = "", tone: str = "other") -> None:
    st.markdown(
        f"""
        <div class="qc-card qc-card-{_html(tone)}">
          <div class="qc-card-label">{_html(label)}</div>
          <div class="qc-card-value">{_html(value)}</div>
          <div class="qc-card-note">{_html(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_section_title(title: str, caption: str = "") -> None:
    st.markdown(f'<div class="qc-section-title">{_html(title)}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(
            f'<div class="qc-section-caption">{_html(caption)}</div>',
            unsafe_allow_html=True,
        )


def _classify_finding_bucket_v2(issue: dict) -> str:
    text = _issue_search_text(issue)
    severity = str(issue.get("severity") or "").upper()
    review_source = str(issue.get("review_source") or "").lower()
    llm_review_type = issue.get("llm_review_type")
    rule_id = str(issue.get("rule_id") or "")
    if _is_fa_list_issue(issue) or _is_prompt_only_checkpoint(issue):
        return "other"
    if _is_by_item_issue(rule_id):
        return "manual" if severity == "NEED_REVIEW" or llm_review_type else "other"
    if (
        severity == "NEED_REVIEW"
        or llm_review_type
        or "llm" in review_source
        or _has_any_keyword(text, _MANUAL_KEYWORDS_V2)
    ):
        return "manual"
    if severity == "FAIL" and rule_id in _HIGH_PRIORITY_RULE_IDS_V2:
        return "high"
    return "other"


def _group_findings_v2(data: dict) -> dict[str, list[dict]]:
    groups = {key: [] for key, _label, _note, _tone in _UI_FINDING_BUCKETS_V2}
    rank = {"FAIL": 0, "NEED_REVIEW": 1, "WARN": 2, "PASS": 3}
    for issue in _finding_issues(data):
        groups[_classify_finding_bucket_v2(issue)].append(issue)
    for items in groups.values():
        items.sort(key=lambda i: (rank.get(str(i.get("severity")), 9), str(i.get("rule_id") or "")))
    return groups


def _rule_prompt_label(severity: str | None) -> str:
    value = _severity_class(severity)
    return {
        "FAIL": "明确不符",
        "WARN": "需关注",
        "NEED_REVIEW": "需人工复核",
        "PASS": "未产生规则提示",
    }.get(value, value)


def _render_overview(name: str, data: dict) -> None:
    summary = data.get("summary") or {}
    overall = summary.get("overall_severity") or "PASS"
    st.markdown(
        f"""
        <div class="qc-file-header">
          <h2>{_html(Path(name).name)} · Findings {_finding_count(data)} 条</h2>
          <p>最高系统规则提示：{_html(_rule_prompt_label(overall))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_findings_summary(data: dict) -> None:
    _render_section_title("Findings 结果", "异常记录按处理优先级展示；不代表最终审计判断。")
    groups = _group_findings_v2(data)
    metrics = [("Findings 总数", _finding_count(data), "不含 PASS", "other")]
    metrics.extend(
        (label, len(groups[key]), note, tone)
        for key, label, note, tone in _UI_FINDING_BUCKETS_V2
    )
    cols = st.columns(len(metrics))
    for col, (label, value, note, tone) in zip(cols, metrics):
        with col:
            _render_card(label, value, note, tone)


def _execution_ledger(data: dict) -> dict | None:
    ledger = data.get("execution_ledger")
    return ledger if isinstance(ledger, dict) else None


def _ledger_summary_value(summary: dict, key: str, fallback: int = 0) -> int:
    value = summary.get(key, fallback)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return fallback


def _ledger_status(item: dict) -> str:
    status = str(item.get("status") or "").upper()
    if status in _LEDGER_ALLOWED_STATUSES:
        return status
    if item.get("executed") is True:
        return "EXECUTED"
    return "UNKNOWN"


def _display_ledger_status(status: str) -> str:
    return _LEDGER_STATUS_LABELS.get(status, "未知状态")


def _contains_forbidden_execution_note(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in _FORBIDDEN_EXECUTION_NOTE_TERMS)


def _neutral_execution_note(status: str) -> str:
    return {
        "EXECUTED": "规则已运行",
        "DATA_INSUFFICIENT": "资料不足，未执行该项检查",
        "NOT_APPLICABLE": "当前场景不适用",
    }.get(status, "状态需诊断")


def _display_execution_note(item: dict) -> str:
    status = _ledger_status(item)
    note = str(item.get("status_note") or "").strip()
    if not note or _contains_forbidden_execution_note(note):
        return _neutral_execution_note(status)
    return note



def _procedure_display_name(procedure: object) -> str:
    value = str(procedure or "").strip()
    return _PROCEDURE_LABELS.get(value, value or "其他")

def _rule_display(rule_id: str) -> tuple[str, str, str]:
    if rule_id in _RULE_DISPLAY:
        return _RULE_DISPLAY[rule_id]
    if rule_id.startswith("lead_") or rule_id.startswith("materiality_") or rule_id.startswith("risk_"):
        return ("K.00 Lead", rule_id, "规则检查")
    if rule_id.startswith("rollforward_"):
        return ("K.01 后推", rule_id, "规则检查")
    if rule_id.startswith("addition_"):
        return ("K.02.1 新增测试", rule_id, "规则检查")
    if rule_id.startswith("disposal_"):
        return ("K.02.2 处置测试", rule_id, "规则检查")
    if rule_id.startswith("k03_policy_"):
        return ("K.03.3 折旧政策复核", rule_id, "规则检查")
    if rule_id.startswith("k03_"):
        return ("K.03 折旧测试", rule_id, "规则检查")
    if rule_id in {"fa_list_required_fields", "unique_asset_id", "asset_amount_non_negative", "asset_value_consistency", "useful_life_positive", "salvage_rate_range"}:
        return ("FA 清单", rule_id, "规则检查")
    if "llm" in rule_id or "semantic" in rule_id:
        return ("LLM 辅助复核", rule_id, "LLM 辅助识别")
    return ("其他", rule_id, "规则检查")


def _render_execution_ledger_summary(data: dict) -> None:
    _render_section_title("质检点执行摘要", "执行状态只表示系统是否运行该检查流程，不表示审计判断。")
    ledger = _execution_ledger(data)
    if not ledger:
        st.warning("本次报告未包含 execution_ledger，无法展示质检点执行台账。")
        return
    summary = ledger.get("summary") or {}
    items = ledger.get("items") or []
    metrics: list[tuple[str, int, str, str]] = []
    for key, label, note, tone in _LEDGER_STATUS_CARD_META:
        if key == "total_observed_checkpoints":
            value = _ledger_summary_value(summary, key, len(items))
        else:
            value = _ledger_summary_value(summary, key, 0)
        metrics.append((label, value, note, tone))
    cols = st.columns(len(metrics))
    for col, (label, value, note, tone) in zip(cols, metrics):
        with col:
            _render_card(label, value, note, tone)


def _render_priority_findings(data: dict) -> None:
    groups = _group_findings_v2(data)
    if not any(groups.values()):
        st.info("本次未记录需展示的 findings。")
        return
    for key, label, _note, _tone in _UI_FINDING_BUCKETS_V2:
        items = groups[key]
        if not items:
            continue
        with st.expander(f"{label} · {len(items)} 条", expanded=False):
            st.dataframe(
                [_findings_row(i) for i in items],
                use_container_width=True,
                hide_index=True,
            )



_OBSERVATION_PATH_LABELS = {
    "primary": "主路径",
    "fallback": "兜底路径",
    "alternative": "替代路径",
    "skipped": "已跳过",
    "data_insufficient": "数据不足",
    "not_applicable": "暂不适用",
}

_OBSERVATION_CHECK_RESULT_LABELS = {
    "passed": "未触发规则提示",
    "triggered": "触发异常",
    "not_applicable": "不适用",
    "data_insufficient": "数据不足",
}


def _observation(item: dict) -> dict:
    observation = item.get("observation")
    return observation if isinstance(observation, dict) else {}


def _has_evidence_how(item: dict) -> bool:
    observation = _observation(item)
    return {
        "checked_data",
        "check_logic",
        "expected_result",
        "actual_result",
        "result_summary",
    }.issubset(set(observation))


def _has_legacy_how(item: dict) -> bool:
    observation = _observation(item)
    return {"path", "inputs", "checks", "notes"}.issubset(set(observation))


def _display_how_status(item: dict) -> str:
    if _has_evidence_how(item):
        return "证据级取数与判断说明已记录"
    if _has_legacy_how(item):
        return "基础取数与判断说明已记录"
    if _ledger_status(item) == "EXECUTED":
        return "未记录取数与判断说明"
    return "未执行说明见状态"


def _display_observation_path(item: dict) -> str:
    path = str(_observation(item).get("path") or "").strip()
    return _OBSERVATION_PATH_LABELS.get(path, path or "未记录")


def _display_observation_inputs(item: dict) -> str:
    inputs = _observation(item).get("inputs") or []
    if not isinstance(inputs, list) or not inputs:
        return "未记录"
    parts: list[str] = []
    for raw in inputs:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source_sheet") or "").strip()
        section = str(raw.get("section") or "").strip()
        field = str(raw.get("field") or "").strip()
        row = raw.get("row")
        column = raw.get("column")
        range_ref = str(raw.get("range") or "").strip()
        item_parts = [part for part in (source, section, field) if part]
        if row:
            item_parts.append(f"row {row}")
        if column:
            item_parts.append(f"col {column}")
        if range_ref:
            item_parts.append(range_ref)
        if item_parts:
            parts.append(" / ".join(item_parts))
    return "；".join(parts) if parts else "未记录"



def _format_check_side(label: object, value: object) -> str:
    label_text = str(label or "").strip()
    value_text = str(value or "").strip()
    if label_text and value_text:
        return f"{label_text}={value_text}"
    return label_text or value_text


def _display_observation_checks(item: dict) -> str:
    checks = _observation(item).get("checks") or []
    if not isinstance(checks, list) or not checks:
        return "未记录"
    parts: list[str] = []
    for raw in checks:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        left = _format_check_side(raw.get("left_label"), raw.get("left_value"))
        operator = str(raw.get("operator") or "").strip()
        right = _format_check_side(raw.get("right_label"), raw.get("right_value"))
        result_key = str(raw.get("result") or "").strip()
        result = _OBSERVATION_CHECK_RESULT_LABELS.get(result_key, result_key)
        comparison = " ".join(part for part in (left, operator, right) if part)
        if name and comparison:
            parts.append(f"{name}: {comparison} -> {result}")
        elif comparison:
            parts.append(f"{comparison} -> {result}")
        elif name:
            parts.append(f"{name} -> {result}")
    return "；".join(parts) if parts else "未记录"


def _render_evidence_how(item: dict) -> None:
    observation = _observation(item)
    checked_data = observation.get("checked_data") or []
    st.markdown("**检查资料**")
    if isinstance(checked_data, list) and checked_data:
        for idx, raw in enumerate(checked_data, start=1):
            if not isinstance(raw, dict):
                continue
            title_parts = [
                str(raw.get("sheet") or "未记录工作表"),
                str(raw.get("section") or "未记录资料区块"),
            ]
            with st.expander(f"检查资料 {idx} · " + " / ".join(title_parts), expanded=False):
                st.write(
                    {
                        "工作表": raw.get("sheet") or "",
                        "资料区块": raw.get("section") or "",
                        "位置": raw.get("location") or "",
                        "关键列": "；".join(str(v) for v in (raw.get("key_columns") or [])),
                    }
                )
                identified = raw.get("identified_by") or {}
                if isinstance(identified, dict):
                    st.write(
                        {
                            "命中的工作表名": identified.get("sheet_name") or "",
                            "命中的资料区块": identified.get("section") or "",
                            "命中的标题/关键词": "；".join(
                                str(v) for v in (identified.get("matched_keywords") or [])
                            ),
                            "命中的行": "；".join(
                                str(v) for v in (identified.get("matched_rows") or [])
                            ),
                            "命中的列": "；".join(
                                str(v) for v in (identified.get("matched_columns") or [])
                            ),
                        }
                    )
                values_read = raw.get("values_read") or []
                if isinstance(values_read, list) and values_read:
                    st.markdown("**实际读取值**")
                    st.dataframe(
                        [
                            {
                                "标签": value.get("label") or "",
                                "值": value.get("value") or "",
                                "行": value.get("row") or "",
                                "列": value.get("column") or "",
                                "单元格": value.get("cell") or "",
                                "单位": value.get("unit") or "",
                                "金额类型": value.get("amount_type") or "",
                            }
                            for value in values_read
                            if isinstance(value, dict)
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                missing = raw.get("missing_data") or []
                if isinstance(missing, list) and missing:
                    st.warning("缺失资料：" + "；".join(str(v) for v in missing))
    else:
        st.info("检查资料未记录。")
    for label, key in (
        ("检查逻辑", "check_logic"),
        ("判断标准", "expected_result"),
        ("实际结果", "actual_result"),
        ("执行结果", "result_summary"),
    ):
        text = str(observation.get(key) or "").strip()
        if text:
            st.markdown(f"**{label}**")
            st.write(text)


def _render_legacy_how(item: dict) -> None:
    st.info("该规则已记录基础取数与判断说明，但尚未补充证据级执行说明。")
    st.write(
        {
            "检查方式": _display_observation_path(item),
            "依赖资料": _display_observation_inputs(item),
            "关键检查摘要": _display_observation_checks(item),
        }
    )


def _rule_execution_matrix(data: dict) -> list[dict]:
    matrix = data.get("rule_execution_matrix")
    return matrix if isinstance(matrix, list) else []


def _rule_execution_summary(data: dict) -> dict:
    summary = data.get("rule_execution_summary")
    return summary if isinstance(summary, dict) else {}


def _audit_text(value: object, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _audit_count(value: object) -> str:
    if value is None:
        return "—"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "—"


def _audit_detail_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _audit_values_read(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows: list[dict] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                "标签": _audit_text(raw.get("label")),
                "读取值": _audit_text(raw.get("value")),
                "行": _audit_text(raw.get("row")),
                "列": _audit_text(raw.get("column")),
                "单元格": _audit_text(raw.get("cell")),
                "单位": _audit_text(raw.get("unit")),
                "金额类型": _audit_text(raw.get("amount_type")),
            }
        )
    return rows


def _audit_matrix_row(row: dict) -> dict:
    return {
        "程序": _audit_text(row.get("module")),
        "规则编号": _audit_text(row.get("rule_code") or row.get("rule_id")),
        "规则名称": _audit_text(row.get("rule_name")),
        "执行状态": _audit_text(row.get("execution_status_label")),
        "未执行原因": _audit_text(row.get("non_execution_reason")),
        "异常数量": _audit_count(row.get("finding_count")),
        "取数来源摘要": _audit_text(row.get("source_summary")),
        "取数与判断说明": _audit_text(row.get("trace_label")),
        "_row": row,
    }


def _audit_matrix_sort_key(row: dict) -> tuple[int, str, str]:
    program = str(row.get("程序") or "")
    program_index = (
        _PROCEDURE_ORDER.index(program)
        if program in _PROCEDURE_ORDER
        else len(_PROCEDURE_ORDER)
    )
    return program_index, str(row.get("规则编号") or ""), str(row.get("规则名称") or "")


def _render_audit_detail(label: str, value: object) -> None:
    st.markdown(f"**{label}**")
    values = _audit_detail_list(value)
    if values:
        for item in values:
            st.write(item)
        return
    st.write(_audit_text(value))


def _render_trace_detail(row: dict) -> None:
    source = row.get("_row") if isinstance(row.get("_row"), dict) else {}
    detail = source.get("trace_detail")
    if not isinstance(detail, dict):
        detail = {}
    _render_audit_detail("检查资料", detail.get("checked_materials"))
    _render_audit_detail("取数位置", detail.get("source_locations"))
    values_read = _audit_values_read(detail.get("values_read"))
    st.markdown("**读取内容**")
    if values_read:
        st.dataframe(values_read, use_container_width=True, hide_index=True)
    else:
        st.write("—")
    _render_audit_detail("检查方法", detail.get("check_method"))
    _render_audit_detail("判断标准", detail.get("expected_result"))
    _render_audit_detail("本次检查结果", detail.get("actual_result"))
    _render_audit_detail("缺失资料", detail.get("missing_data"))
    _render_audit_detail("说明", detail.get("notes"))

_PROCEDURE_CODE_LABELS: dict[str, str] = {
    "K.00": "K.00 Lead",
    "K.01": "K.01",
    "K.02.1": "K.02.1",
    "K.02.2": "K.02.2",
    "K.03": "K.03",
    "K.03.1": "K.03.1",
    "K.03.2": "K.03.2",
    "K.03.3": "K.03.3",
    "FA_LIST": "FA list",
    "SUMMARY": "汇总",
    "GLOBAL": "全局",
    "WORKBOOK": "工作簿",
}


def _render_execution_trace_table(data: dict) -> None:
    """渲染 6 列执行台账，按 execution_ledger.items 原始执行顺序。"""
    from report.summary import summarize_source_location

    ledger = _execution_ledger(data)
    _render_section_title("质检点执行台账", "展示系统实际执行顺序。执行状态仅表示流程是否运行，不代表审计判断。")
    if not ledger:
        st.info("本次报告未包含 execution_ledger。")
        return
    items = ledger.get("items") or []
    if not items:
        st.info("本次未记录到质检点执行台账。")
        return

    visible_columns = ["程序", "规则编号", "规则名称", "执行状态", "未执行原因", "取数来源"]
    rows: list[dict] = []
    for item in items:
        rule_id = item.get("rule_id", "")
        status = item.get("status", "")
        status_label = {"EXECUTED": "已执行", "DATA_INSUFFICIENT": "数据不足", "NOT_APPLICABLE": "暂不适用"}.get(status, status)
        proc_code = item.get("procedure_code", "")
        proc_label = _PROCEDURE_CODE_LABELS.get(proc_code, proc_code or "—")
        dict_code = item.get("dict_code", "") or rule_id
        rule_name = item.get("rule_name", "") or ""
        status_note = ""
        if status != "EXECUTED":
            status_note = item.get("status_note", "") or "—"
        source_loc = summarize_source_location(item.get("observation"))

        rows.append({
            "程序": proc_label,
            "规则编号": dict_code,
            "规则名称": rule_name,
            "执行状态": status_label,
            "未执行原因": status_note,
            "取数来源": source_loc,
            "_item": item,
            "_status": status,
        })

    st.dataframe(
        [{c: row[c] for c in visible_columns} for row in rows],
        use_container_width=True,
        hide_index=True,
    )

    # 每行可点击展开"检查明细"
    for row in rows:
        item = row["_item"]
        status = row["_status"]
        obs = item.get("observation") if isinstance(item, dict) else None
        if not obs:
            continue
        rule_name = row["规则名称"] or row["规则编号"]
        with st.expander(f"检查明细 · {rule_name} · {row['执行状态']}", expanded=False):
            if _has_evidence_how(item):
                _render_evidence_how(item)
            elif _has_legacy_how(item):
                _render_legacy_how(item)
            elif status == "EXECUTED":
                st.info("执行明细未记录：该规则已执行，但尚未补充证据级执行说明。")


def _render_coverage_diagnostics(data: dict) -> None:
    matrix = _rule_execution_matrix(data)
    summary = _rule_execution_summary(data)
    _render_section_title("质检点执行台账", "展示规则是否执行、取数来源和本次判断过程。")
    st.markdown(
        '<div class="qc-ledger-note">执行状态仅表示系统本次是否运行该规则；未执行不等于无待处理 Findings，异常记录仍以 Findings 明细为准。</div>',
        unsafe_allow_html=True,
    )
    if not matrix:
        st.info("本次报告未包含规则执行矩阵，无法展示质检点执行台账。")
        return
    rows = sorted((_audit_matrix_row(row) for row in matrix), key=_audit_matrix_sort_key)
    visible_columns = [
        "程序",
        "规则编号",
        "规则名称",
        "执行状态",
        "未执行原因",
        "异常数量",
        "取数来源摘要",
        "取数与判断说明",
    ]
    status_counts = summary.get("execution_status_counts") or {}
    st.caption(
        "全部规则 {total}；已执行 {executed}；资料不足 {insufficient}；本次不适用 {na}；未进入执行 {not_triggered}".format(
            total=summary.get("matrix_rule_count", len(rows)),
            executed=status_counts.get("EXECUTED", 0),
            insufficient=status_counts.get("DATA_INSUFFICIENT", 0),
            na=status_counts.get("NOT_APPLICABLE", 0),
            not_triggered=status_counts.get("NOT_TRIGGERED_BY_CONTEXT", 0),
        )
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("程序") or "其他"), []).append(row)
    for program, group_rows in grouped.items():
        expanded = any(row.get("异常数量") not in {"—", "0"} for row in group_rows)
        with st.expander(f"{program} · 规则 {len(group_rows)}", expanded=expanded):
            st.dataframe(
                [
                    {column: row.get(column, "") for column in visible_columns}
                    for row in group_rows
                ],
                use_container_width=True,
                hide_index=True,
            )
            for row in group_rows:
                title = (
                    f"取数与判断说明 · {row.get('规则编号') or ''} · "
                    f"{row.get('执行状态') or ''} · 异常 {row.get('异常数量') or '—'}"
                )
                with st.expander(title, expanded=False):
                    _render_trace_detail(row)


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


def _render_result_view(results: dict, errors: dict) -> None:
    st.subheader("质检结果")
    message = st.session_state.get("last_run_message")
    if message:
        st.success(message)
    if errors:
        for file_name, err in errors.items():
            st.error(f"**{file_name}**：{err}")

    names = list(results.keys())
    if not names:
        return
    selected_name = (
        st.selectbox("查看文件", names, key="result_file_selector")
        if len(names) > 1
        else names[0]
    )
    bundle = results[selected_name]
    data = bundle["data"]

    st.caption(f"当前文件：{selected_name}")
    _render_downloads(selected_name, bundle)
    st.divider()

    _render_findings_summary(data)
    st.divider()
    _render_execution_ledger_summary(data)
    st.divider()

    findings_tab, ledger_tab, procedure_tab, preview_tab, diagnostics_tab = st.tabs(
        ["Findings 明细", "质检点执行台账", "程序分组明细", "交付物预览", "系统诊断"]
    )
    with findings_tab:
        _render_priority_findings(data)
    with ledger_tab:
        _render_execution_trace_table(data)
    with procedure_tab:
        _render_procedure_summary(data)
        _render_findings_grouped(data)
        st.divider()
        _render_manual_review(data)
        st.divider()
        _render_qc_summary(data)
    with preview_tab:
        _render_artifact_preview(bundle)
    with diagnostics_tab:
        _render_system_diagnostics(data, bundle)
        st.divider()
        _render_coverage_diagnostics(data)


def _render_upload_panel(*, collapsed_after_results: bool) -> None:
    container = st.expander("重新上传 / 修改参数", expanded=False) if collapsed_after_results else st.container()
    with container:
        st.subheader("交付完整性")
        delivery_stage = st.radio(
            "交付阶段",
            options=["none", "first", "final"],
            format_func=lambda v: {
                "none": "不检查交付完整性",
                "first": "首次交付",
                "final": "整体交付",
            }[v],
            horizontal=True,
        )

        st.info("外部数据状态：TE/SAD 当前优先从 Lead 识别，手工确认后续接入；A3 审定金额表映射后续接入；CRA 标准模板导入后续接入。未提供外部资料不会阻断运行，相关检查点会显示为数据不足，未执行。")
        uploaded = st.file_uploader(
            "选择待质检底稿",
            type=["xlsx", "xlsm", "csv"],
            accept_multiple_files=True,
        )

        if not uploaded:
            st.info("上传 Excel 或 CSV 后开始质检。")
            st.markdown(
                f'''
**主要交付物**：`*_qc_annotated.xlsx`

| Sheet | 内容 |
| --- | --- |
| `{COMMENTS_SHEET_NAME}` | 其他程序逐条 findings + FA list 共性问题合并行 |
| `{FA_LIST_COMMENTS_SHEET_NAME}` | FA list findings 逐条明细 |
                '''
            )
            return

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
                progress.progress((idx + 1) / len(uploaded), text="已处理")
            progress.empty()
            st.session_state["last_run_message"] = f"已处理 {len(uploaded)} 个文件，结果如下。"
            st.rerun()


# ---- v3 入口：使用新设计系统 + 侧边导航 ----
from report.ui_components.styles import get_global_css
st.markdown(get_global_css(), unsafe_allow_html=True)
def main() -> None:
    # 页面路由
    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "workbench"

    with st.sidebar:
        # 品牌区
        st.markdown(
            '<div class="sidebar-brand-text">审计底稿复核 Agent</div>'
            '<div class="sidebar-subtitle">Audit Workpaper Review</div>'
            '<div class="sidebar-subject-tag">固定资产 K1</div>',
            unsafe_allow_html=True,
        )

        # 工作台组
        st.markdown('<div class="sidebar-section-label">工作台</div>', unsafe_allow_html=True)
        for key, label in [("workbench", "复核工作台"), ("runner", "执行复核"), ("findings", "复核结果")]:
            if st.button(label, key=f"nav_{key}",
                         type="primary" if st.session_state["active_page"] == key else "secondary",
                         use_container_width=True):
                st.session_state["active_page"] = key
                st.rerun()

        st.divider()
        # 记录组
        st.markdown('<div class="sidebar-section-label">记录</div>', unsafe_allow_html=True)
        for key, label in [("history", "运行历史"), ("compare", "运行对比")]:
            if st.button(label, key=f"nav_{key}",
                         type="primary" if st.session_state["active_page"] == key else "secondary",
                         use_container_width=True):
                st.session_state["active_page"] = key
                st.rerun()

        st.divider()
        # 管理组
        st.markdown('<div class="sidebar-section-label">管理</div>', unsafe_allow_html=True)
        for key, label in [("projects", "项目管理")]:
            if st.button(label, key=f"nav_{key}",
                         type="primary" if st.session_state["active_page"] == key else "secondary",
                         use_container_width=True):
                st.session_state["active_page"] = key
                st.rerun()

        st.divider()
        if st.button("清除缓存", use_container_width=True, key="cache_btn"):
            st.cache_data.clear()
            st.success("已清除")

        build_info = get_build_info()
        lock_label = "已锁定" if build_info["lock_status"] == "LOCKED" else "未锁定"
        st.markdown(
            '<div class="sidebar-footer-text">'
            f'固定资产质检 Agent v{_html(build_info["agent_version"])}<br>'
            f'{_html(build_info["pilot_build"])} · {lock_label}'
            '</div>',
            unsafe_allow_html=True,
        )

    # ---- 页面渲染 ----
    active = st.session_state["active_page"]

    if active == "workbench":
        from report.ui_pages.workbench import render_workbench
        render_workbench()

    elif active == "runner":
        from report.ui_pages.qc_runner import render_qc_runner
        render_qc_runner()

    elif active == "findings":
        from report.ui_pages.findings_viewer import render_findings_viewer
        render_findings_viewer()

    elif active == "coverage":
        st.session_state["active_page"] = "findings"
        st.info("检查范围已合并到复核结果页的质检点执行台账。")
        from report.ui_pages.findings_viewer import render_findings_viewer
        render_findings_viewer()

    elif active == "history":
        from report.ui_pages.run_history import render_run_history
        render_run_history()

    elif active == "projects":
        from report.ui_pages.project_manager import render_project_manager
        render_project_manager()

    elif active == "compare":
        from report.ui_pages.compare import render_compare
        render_compare()

    elif active == "legacy":
        st.session_state["active_page"] = "runner"
        st.info("旧版界面已停用，请使用当前执行复核页面。")
        from report.ui_pages.qc_runner import render_qc_runner
        render_qc_runner()
        return
        # 旧版完整界面（旁路访问，不做删除）
        _inject_style()
        with st.sidebar:
            st.header("设置")
            if st.button("清除质检缓存（旧版）", help="规则更新后若结果未变，清缓存后重新运行。"):
                st.cache_data.clear()
                st.success("已清除缓存")
            use_llm = st.checkbox("启用大模型规则语义复核", value=False)
            if use_llm:
                st.info("LLM 将参与汇总页/Lead 等语义类规则复核，并生成摘要；不覆盖确定性规则 severity。")
            with st.expander("高级：指定工作表名称"):
                fa_sheet = st.text_input("FA list 表名", "")
                summary_sheet = st.text_input("汇总表名", "")
                lead_sheet = st.text_input("Lead 表名", "")
                st.caption("当前仅支持部分工作表名称指定；不填则自动识别。完整 K.01/K.02/K.03 表名指定后续单独扩展。")

        st.session_state.setdefault("use_llm_legacy", False)
        use_llm = st.session_state["use_llm_legacy"]

        results = st.session_state.get("results", {})
        errors = st.session_state.get("errors", {})

        if results:
            _render_result_view(results, errors)
            st.divider()
            _render_upload_panel(collapsed_after_results=True)
        else:
            if errors:
                for file_name, err in errors.items():
                    st.error(f"**{file_name}**：{err}")
            _render_upload_panel(collapsed_after_results=False)


if __name__ == "__main__":
    main()



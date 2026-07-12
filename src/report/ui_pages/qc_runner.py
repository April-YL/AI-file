# [阶段一] 执行复核页 — 上传 + 参数 + 分步进度 + 持久化
# 从 ui_app.py 的 _render_upload_panel + _run_qc_cached 迁移
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 执行复核页。

上传底稿 → 选择参数 → 执行 → 自动持久化 → 跳转 Findings 浏览器。
"""

from __future__ import annotations

import tempfile
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from time import perf_counter

import streamlit as st

from report.export_annotated_workbook import export_annotated_workbook
from report.export_json import export_report_json
from report.export_review_html import export_review_html
from report.pipeline import run_input_qc
from report.ui_state.project_store import ensure_default_project
from report.ui_state.database import ARTIFACTS_DIR
from report.ui_state.run_store import get_run, save_run
from rules.delivery_completion import DeliveryCompletionContext

_QC_CACHE_VERSION = "20260708-ui-v3-workbench"

_LLM_PRESETS: dict[str, dict[str, object]] = {
    "OpenAI": {
        "api_url": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"],
    },
    "Anthropic": {
        "api_url": "https://api.anthropic.com/v1/messages",
        "models": ["claude-fable-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
    },
    "Gemini": {
        "api_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    },
    "DeepSeek": {
        "api_url": "https://api.deepseek.com/chat/completions",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
    },
    "阿里云百炼": {
        "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "models": ["qwen3.7-max", "qwen3.7-plus", "qwen3.6-flash"],
    },
    "自定义": {"api_url": "", "models": ["自定义模型"]},
}

_RUNNER_STEPS = [
    "读取底稿",
    "识别工作表",
    "规则检查",
    "LLM 辅助",
    "生成报告",
    "生成标注副本",
    "保存运行记录",
]

_ACTIVE_RUN_KEY = "active_run"


def _new_run_id(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


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
    """执行 QC 流水线（缓存加速相同输入的重复运行）。"""
    total_t0 = perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / filename
        inp.write_bytes(file_bytes)

        delivery_context = None
        if delivery_stage in ("first", "final"):
            delivery_context = DeliveryCompletionContext(stage=delivery_stage)

        report = run_input_qc(
            str(inp),
            fa_sheet=fa_sheet or None,
            summary_sheet=summary_sheet or None,
            lead_sheet=lead_sheet or None,
            llm=use_llm,
            delivery_context=delivery_context,
        )

        json_path = Path(tmp) / "report.json"
        html_path = Path(tmp) / "report.html"
        json_html_t0 = perf_counter()
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
        timings["json_html_seconds"] = round(json_html_seconds, 3)
        timings["annotated_seconds"] = round(annotated_seconds, 3)
        timings["total_seconds"] = round(perf_counter() - total_t0, 3)
        data["runtime_timings"] = timings
        data["delivery_stage"] = delivery_stage
        data["subject_code"] = "FA_K1"

        return data, json_path.read_bytes(), html_path.read_bytes(), annotated_bytes


def render_qc_runner() -> None:
    """渲染执行复核页。"""
    st.subheader("执行复核")
    runner_state = _runner_state()

    # --- 项目选择 ---
    project_id = _ensure_project()

    # --- 1. 复核配置 ---
    st.markdown("### 复核配置")
    with st.container(border=True):
        delivery_stage_options = ["none", "first", "final"]
        delivery_stage = st.radio(
            "交付阶段",
            options=delivery_stage_options,
            index=delivery_stage_options.index(runner_state.get("delivery_stage", "none"))
            if runner_state.get("delivery_stage", "none") in delivery_stage_options
            else 0,
            format_func=lambda v: {"none": "不检查", "first": "首次交付", "final": "整体交付"}[v],
            horizontal=True,
            key="runner_delivery_stage",
        )
        review_mode = st.radio(
            "复核模式",
            options=["rules", "llm"],
            index=1 if runner_state.get("use_llm") else 0,
            format_func=lambda v: {"rules": "纯规则复核", "llm": "启用 LLM 辅助复核"}[v],
            horizontal=True,
            key="runner_review_mode",
        )
        use_llm = review_mode == "llm"
        st.caption("科目：固定资产 K1。LLM 默认关闭；开启后仅辅助语义类复核，不改变确定性规则。")
        if use_llm:
            with st.expander("LLM 配置", expanded=True):
                provider_options = list(_LLM_PRESETS)
                saved_provider = str(runner_state.get("llm_provider") or "OpenAI")
                provider = st.selectbox(
                    "服务商",
                    provider_options,
                    index=provider_options.index(saved_provider) if saved_provider in provider_options else 0,
                    key="runner_llm_provider",
                )
                preset = _LLM_PRESETS[provider]
                models = list(preset["models"])
                llm_col1, llm_col2 = st.columns(2)
                with llm_col1:
                    if provider == "自定义":
                        api_url = st.text_input(
                            "API 地址",
                            value=str(runner_state.get("llm_api_url") or ""),
                            placeholder="https://api.example.com/v1/chat/completions",
                            key="runner_llm_custom_url",
                        )
                        model_name = st.text_input(
                            "模型名称",
                            value=str(runner_state.get("llm_model") or ""),
                            placeholder="输入自定义模型名",
                            key="runner_llm_custom_model",
                        )
                    else:
                        api_url = str(preset["api_url"])
                        saved_model = str(runner_state.get("llm_model") or models[0])
                        model_name = st.selectbox(
                            "模型名称",
                            models,
                            index=models.index(saved_model) if saved_model in models else 0,
                            key="runner_llm_model",
                        )
                with llm_col2:
                    api_key = st.text_input("API Key", type="password", placeholder="仅用于本次界面配置", key="runner_llm_key")
                    st.number_input("超时（秒）", min_value=10, max_value=300, value=60, step=10, key="runner_llm_timeout")
                    if st.button("测试连接", use_container_width=True, key="runner_llm_test"):
                        _persist_runner_config(
                            runner_state,
                            delivery_stage=delivery_stage,
                            use_llm=True,
                            provider=provider,
                            model_name=model_name,
                            api_url=api_url,
                            api_key_present=bool(api_key),
                            uploaded=st.session_state.get("runner_uploaded_files") or [],
                        )
                        runner_state["llm_test_result"] = _test_llm_connection(
                            provider=provider,
                            api_url=api_url,
                            model_name=model_name,
                            api_key=api_key,
                            timeout=int(st.session_state.get("runner_llm_timeout") or 60),
                        )
                _render_llm_test_result(runner_state.get("llm_test_result"))
                st.caption("当前配置区不保存真实密钥；后端 LLM 调用逻辑保持不变。")
        else:
            provider = ""
            model_name = ""
            api_url = ""
            api_key = ""

    # --- 2. 外部资料核对 ---
    st.markdown("### 外部资料核对")
    with st.container(border=True):
        use_external_check = st.checkbox("核对 TE / SAD / A3 / CRA", value=False, key="runner_external_check")
        if use_external_check:
            st.caption("外部资料用于辅助核对基础信息准确性；不改变规则引擎和报告结构。")
            ext_col1, ext_col2 = st.columns(2)
            with ext_col1:
                st.text_input("TE", placeholder="可填写 TE 摘要或来源说明", key="runner_te_note")
                st.text_input("SAD", placeholder="可填写 SAD 摘要或来源说明", key="runner_sad_note")
            with ext_col2:
                st.selectbox("A3 审定表", ["不提供", "从当前 Excel 选择", "上传独立文件"], key="a3_source")
                st.file_uploader("CRA 模板 (.xlsx/.csv)", type=["xlsx", "csv"], key="cra_upload")
        else:
            st.caption("未进行外部资料核对；相关事项保留给审计师判断。")

    # --- 3. 待复核底稿 ---
    st.markdown("### 待复核底稿")
    uploaded = st.file_uploader(
        "拖拽 Excel 到此处或点击选择",
        help="支持 .xlsx / .xlsm / .csv，可一次上传多个底稿。",
        type=["xlsx", "xlsm", "csv"],
        accept_multiple_files=True,
        key="runner_uploaded_files",
    )

    if not uploaded:
        _persist_runner_config(
            runner_state,
            delivery_stage=delivery_stage,
            use_llm=use_llm,
            provider=provider,
            model_name=model_name,
            api_url=api_url,
            api_key_present=bool(api_key),
            uploaded=[],
        )
        _render_upload_summary([])
        _render_execute_area([])
        _render_runner_status_panel(runner_state)
        _render_unfinished_run_notice()
        return
    _persist_runner_config(
        runner_state,
        delivery_stage=delivery_stage,
        use_llm=use_llm,
        provider=provider,
        model_name=model_name,
        api_url=api_url,
        api_key_present=bool(api_key),
        uploaded=uploaded,
    )
    _render_upload_summary(uploaded)

    # --- 4. 执行复核 ---
    if _render_execute_area(uploaded):
        st.session_state["qc_results"] = {}
        st.session_state["qc_errors"] = {}
        st.session_state.pop("last_saved_run_id", None)
        run_id = _new_run_id()
        runner_state["status"] = "running"
        runner_state["started_at"] = datetime.now().isoformat(timespec="seconds")
        runner_state["current_step"] = "读取底稿"
        runner_state["finished_at"] = ""
        runner_state["last_error"] = ""
        runner_state["step_statuses"] = {step: "未开始" for step in _RUNNER_STEPS}
        runner_state["step_timings"] = {}
        status_placeholder = st.empty()
        _render_runner_status_placeholder(status_placeholder, runner_state)
        progress = st.progress(0, text="准备中...")

        for idx, uf in enumerate(uploaded):
            progress.progress(idx / len(uploaded), text=f"读取底稿：{uf.name}")
            _start_active_run(uf.name, run_id)
            _render_runner_status_placeholder(status_placeholder, runner_state)
            try:
                _mark_runner_step(runner_state, "读取底稿", status="进行中")
                _mark_runner_step(runner_state, "识别工作表", status="进行中")
                _mark_runner_step(runner_state, "规则检查", status="进行中")
                if use_llm:
                    _mark_runner_step(runner_state, "LLM 辅助", status="进行中")
                progress.progress((idx + 0.2) / len(uploaded), text=f"规则检查与 LLM 辅助：{uf.name}")
                _render_runner_status_placeholder(status_placeholder, runner_state)
                data, json_bytes, html_bytes, ann_bytes = _run_qc_cached(
                    uf.getvalue(),
                    uf.name,
                    use_llm,
                    None,
                    None,
                    None,
                    delivery_stage,
                    _QC_CACHE_VERSION,
                )
                for step in _RUNNER_STEPS[:-1]:
                    _mark_runner_step(runner_state, step, data.get("runtime_timings") or {}, status="已完成")
                progress.progress((idx + 0.85) / len(uploaded), text=f"保存运行记录：{uf.name}")
                _mark_runner_step(runner_state, "保存运行记录", status="进行中")
                _render_runner_status_placeholder(status_placeholder, runner_state)
                saved_run_id = save_run(project_id, uf.name, data, json_bytes, html_bytes, ann_bytes)
                _validate_saved_run(saved_run_id, expect_annotated=ann_bytes is not None)
                _mark_runner_step(runner_state, "保存运行记录", status="已完成")
                _finish_active_run(saved_run_id)
                st.session_state["last_saved_run_id"] = saved_run_id
                st.session_state.setdefault("qc_results", {})[uf.name] = {
                    "data": data,
                    "json_bytes": json_bytes,
                    "html_bytes": html_bytes,
                    "annotated_bytes": ann_bytes,
                    "run_id": run_id,
                    "saved_run_id": saved_run_id,
                }
            except Exception as e:
                st.session_state.setdefault("qc_errors", {})[uf.name] = str(e)
                runner_state["status"] = "failed"
                runner_state["current_step"] = "执行异常"
                runner_state["last_error"] = str(e)
                _fail_active_run(str(e))
                _mark_runner_step(runner_state, runner_state.get("current_step") or "执行异常", status="失败")
                _render_runner_status_placeholder(status_placeholder, runner_state)
            progress.progress((idx + 1) / len(uploaded), text="已处理")

        progress.empty()
        status_placeholder.empty()

        # 真实耗时存 session_state（rerun 后由 Findings 页面展示）
        timing_info: dict[str, dict] = {}
        for name, bundle in st.session_state.get("qc_results", {}).items():
            data = bundle.get("data") or {}
            timings = data.get("runtime_timings") or {}
            if timings:
                timing_info[name] = timings
        if timing_info:
            st.session_state["qc_timings"] = timing_info

        if st.session_state.get("qc_errors"):
            runner_state["status"] = "failed"
            st.error("本次复核未完成保存，请查看最近错误后重新执行。")
            return
        else:
            runner_state["status"] = "finished"
            runner_state["current_step"] = "保存运行记录"
            runner_state["finished_at"] = datetime.now().isoformat(timespec="seconds")
        st.session_state["active_page"] = "findings"
        st.rerun()
    _render_runner_status_panel(runner_state)


def render_info_banner() -> None:
    """渲染科目信息横幅。"""
    st.markdown(
        """
        <div class="qc-info-banner">
          当前科目：<strong>固定资产 K1</strong>。
          所有运行结果自动存入本地数据库，可在「运行历史」中回溯和对比。
        </div>
        """,
        unsafe_allow_html=True,
    )


def _runner_state() -> dict:
    state = st.session_state.setdefault("runner_state", {})
    state.setdefault("status", "idle")
    state.setdefault("current_step", "待执行")
    state.setdefault("uploaded_files", [])
    state.setdefault("step_statuses", {step: "未开始" for step in _RUNNER_STEPS})
    state.setdefault("step_timings", {})
    state.setdefault("last_error", "")
    state.setdefault("api_key_present", False)
    return state


def _start_active_run(filename: str, run_id: str) -> dict:
    """记录当前同步执行草稿，避免结果页误展示旧运行。"""
    active = {
        "status": "running",
        "filename": filename,
        "run_id": run_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "current_step": "读取底稿",
        "saved_run_id": None,
        "error": "",
        "step_statuses": {step: "未开始" for step in _RUNNER_STEPS},
    }
    st.session_state[_ACTIVE_RUN_KEY] = active
    return active


def _active_run() -> dict:
    active = st.session_state.setdefault(_ACTIVE_RUN_KEY, {})
    return active if isinstance(active, dict) else {}


def _finish_active_run(saved_run_id: int) -> None:
    active = _active_run()
    active.update(
        {
            "status": "finished",
            "current_step": "保存运行记录",
            "saved_run_id": saved_run_id,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "error": "",
        }
    )


def _fail_active_run(error: str) -> None:
    active = _active_run()
    active.update(
        {
            "status": "failed",
            "current_step": "执行异常",
            "error": error,
            "failed_at": datetime.now().isoformat(timespec="seconds"),
        }
    )


def _validate_saved_run(saved_run_id: int, *, expect_annotated: bool) -> None:
    saved = get_run(saved_run_id)
    if not saved or not saved.get("data"):
        raise RuntimeError(f"运行记录 {saved_run_id} 保存后无法读取")
    artifact_dir = saved.get("artifact_dir")
    if not artifact_dir:
        raise RuntimeError(f"运行记录 {saved_run_id} 未记录产物目录")
    artifact_path = ARTIFACTS_DIR / str(artifact_dir)
    required = ["report.json", "review.html"]
    if expect_annotated:
        required.append("annotated.xlsx")
    missing = [name for name in required if not (artifact_path / name).exists()]
    if missing:
        raise RuntimeError(f"运行记录 {saved_run_id} 缺少产物：{', '.join(missing)}")


def _render_unfinished_run_notice() -> bool:
    active = _active_run()
    status = active.get("status")
    if status not in {"running", "failed"}:
        return False
    filename = active.get("filename") or "上一份底稿"
    if status == "running":
        st.warning(
            f"{filename} 的复核状态尚未完成保存。当前步骤：{active.get('current_step') or '—'}。"
            "请等待执行完成，或刷新后重新上传执行。"
        )
    else:
        st.error(f"{filename} 的复核未完成保存：{active.get('error') or '未知错误'}")
        if st.button("清除本次失败状态", key="runner_clear_failed_run"):
            st.session_state.pop(_ACTIVE_RUN_KEY, None)
            runner_state = st.session_state.get("runner_state")
            if isinstance(runner_state, dict):
                runner_state["status"] = "idle"
                runner_state["current_step"] = "待执行"
                runner_state["last_error"] = ""
                runner_state["step_statuses"] = {step: "未开始" for step in _RUNNER_STEPS}
            st.rerun()
    return True


def _render_runner_status_panel(state: dict) -> None:
    status = state.get("status")
    if not status:
        return
    label = {
        "idle": "待执行",
        "running": "正在复核",
        "finished": "复核已处理",
        "failed": "复核异常",
    }.get(str(status), str(status))
    current = state.get("current_step") or "—"
    files = state.get("uploaded_files") or []
    file_note = "、".join(str(name) for name in files[:2])
    if len(files) > 2:
        file_note += f" 等 {len(files)} 个文件"
    status_class = {
        "idle": "idle",
        "running": "running",
        "finished": "finished",
        "failed": "failed",
    }.get(str(status), "idle")
    st.markdown(
        f"""
        <div class="qc-runner-status qc-runner-status-{status_class}">
          <div>
            <strong>{label}</strong> · 当前步骤：{current}
            {f" · {file_note}" if file_note else ""}
          </div>
          <div class="qc-runner-status-meta">
            LLM：{state.get('llm_provider') or '未启用'} {state.get('llm_model') or ''}
            · API Key：{'已填写' if state.get('api_key_present') else '未填写'}
            · 开始：{state.get('started_at') or '—'}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if str(status) == "running":
        _render_current_execution_state(state)
    elif str(status) == "finished":
        _render_completed_runtime_summary(state)
    if state.get("last_error"):
        st.error(f"最近错误：{state['last_error']}")


def _render_runner_status_placeholder(placeholder, state: dict) -> None:
    placeholder.empty()
    with placeholder.container():
        _render_runner_status_panel(state)


def _render_current_execution_state(state: dict) -> None:
    """执行中只展示可信粗状态，不伪装成精确实时阶段。"""
    step_statuses = state.get("step_statuses") or {}
    if step_statuses.get("保存运行记录") == "进行中":
        stage = "保存结果"
        note = "正在保存运行记录和交付物，完成后会进入复核结果。"
    elif step_statuses.get("生成报告") == "已完成" or step_statuses.get("生成标注副本") == "已完成":
        stage = "生成交付物"
        note = "正在生成报告与标注副本。"
    elif any(step_statuses.get(step) == "进行中" for step in ("规则检查", "LLM 辅助")):
        stage = "质检执行中"
        note = "正在执行规则检查与 LLM 辅助，完成前请勿刷新或切换页面。"
    elif step_statuses.get("读取底稿") == "进行中" or step_statuses.get("识别工作表") == "进行中":
        stage = "读取与识别底稿"
        note = "正在读取底稿并识别工作表结构。"
    else:
        stage = "准备中"
        note = "正在准备本次复核。"
    st.markdown(f"**当前执行状态：{stage}**")
    st.caption(note)


def _render_completed_runtime_summary(state: dict) -> None:
    """完成后展示真实耗时拆分；数据只来自 runtime_timings。"""
    step_timings = state.get("step_timings") or {}
    if not step_timings:
        return
    st.markdown("**本次运行耗时**")
    labels = [
        ("读取底稿", "读取底稿"),
        ("规则检查", "规则检查"),
        ("LLM", "LLM 辅助"),
        ("报告生成", "生成报告"),
        ("标注副本", "生成标注副本"),
    ]
    columns = st.columns(min(len(labels), 5))
    for column, (label, step) in zip(columns, labels):
        seconds = step_timings.get(step)
        with column:
            st.markdown(
                f"""
                <div class="qc-step-chip qc-step-done">
                  <div class="qc-step-name">{label}</div>
                  <div class="qc-step-status">{_format_seconds(seconds) if seconds else "—"}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _persist_runner_config(
    state: dict,
    *,
    delivery_stage: str,
    use_llm: bool,
    provider: str,
    model_name: str,
    api_url: str,
    api_key_present: bool,
    uploaded: list,
) -> None:
    state.update(
        {
            "delivery_stage": delivery_stage,
            "use_llm": use_llm,
            "llm_provider": provider,
            "llm_model": model_name,
            "llm_api_url": api_url if provider == "自定义" else "",
            "api_key_present": api_key_present,
            "uploaded_files": [getattr(uf, "name", "未命名文件") for uf in uploaded],
            "status": state.get("status") or "idle",
        }
    )


def _mark_runner_step(
    state: dict,
    step: str,
    timings: dict | None = None,
    *,
    status: str | None = None,
) -> None:
    state["current_step"] = step
    active = _active_run()
    if active.get("status") == "running":
        active["current_step"] = step
    if status and step in _RUNNER_STEPS:
        state.setdefault("step_statuses", {})[step] = status
        if active.get("status") == "running":
            active.setdefault("step_statuses", {})[step] = status
    step_timings = state.setdefault("step_timings", {})
    mapping = {
        "读取底稿": "ingest_seconds",
        "规则检查": "rules_seconds",
        "LLM 辅助": "llm_seconds",
        "生成报告": "json_html_seconds",
        "生成标注副本": "annotated_seconds",
    }
    key = mapping.get(step)
    if key and timings and key in timings:
        step_timings[step] = timings.get(key)


def _format_file_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _format_seconds(value: object) -> str:
    try:
        seconds = float(value or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"


def _step_status_class(status: str) -> str:
    return {
        "已完成": "done",
        "进行中": "active",
        "失败": "failed",
    }.get(status, "pending")


def _render_upload_summary(uploaded: list) -> None:
    if not uploaded:
        st.info("上传 Excel 或 CSV 后开始复核。")
        return
    total_size = sum(len(uf.getvalue()) for uf in uploaded)
    st.caption(
        f"已选择 {len(uploaded)} 个文件，总大小 {_format_file_size(total_size)}："
        + "；".join(f"{uf.name}（{_format_file_size(len(uf.getvalue()))}）" for uf in uploaded)
    )


def _render_execute_area(uploaded: list) -> bool:
    """渲染执行入口；未上传时入口保持可见但不可执行。"""
    st.markdown("### 执行复核")
    if not uploaded:
        st.button("执行复核", type="primary", use_container_width=True, disabled=True, key="runner_execute_disabled")
        st.caption("请先上传底稿，再开始质检。")
        return False
    return st.button("执行复核", type="primary", use_container_width=True, key="runner_execute")


def _test_llm_connection(
    *,
    provider: str,
    api_url: str,
    model_name: str,
    api_key: str,
    timeout: int,
) -> dict[str, str]:
    if not api_key:
        return {"status": "failed", "message": "请先输入 API Key。"}
    if provider in {"Anthropic", "Gemini"}:
        return {"status": "unsupported", "message": f"{provider} 的连接测试暂未接入当前 UI。"}
    if provider == "自定义" and (not api_url or not model_name):
        return {"status": "failed", "message": "自定义模式需要填写 API 地址和模型名称。"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return {"status": "ok", "message": "连接测试成功。"}
            return {"status": "failed", "message": f"连接测试失败：HTTP {response.status}"}
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "message": f"连接测试失败：HTTP {exc.code}"}
    except Exception as exc:
        return {"status": "failed", "message": f"连接测试失败：{exc}"}


def _render_llm_test_result(result: object) -> None:
    if not isinstance(result, dict) or not result:
        return
    status = result.get("status")
    message = str(result.get("message") or "")
    if status == "ok":
        st.success(message)
    elif status == "unsupported":
        st.warning(message)
    else:
        st.error(message)


def _render_runtime_timings(timings: dict, filename: str) -> None:
    """展示真实耗时（从旧 _render_runtime_timings 迁移）。"""
    labels = [
        ("读取底稿", "ingest_seconds"),
        ("规则检查", "rules_seconds"),
        ("LLM", "llm_seconds"),
        ("JSON+HTML", "json_html_seconds"),
        ("标注副本", "annotated_seconds"),
        ("总耗时", "total_seconds"),
    ]
    parts = [f"{label}: {_format_seconds(timings.get(key))}" for label, key in labels if key in timings]
    if not parts:
        return
    llm_note = "启用" if timings.get("llm_enabled") else "未启用"
    st.markdown(
        f'<div style="font-size:0.78rem;color:#666;margin-top:0.35rem">'
        f'{filename} 耗时（LLM {llm_note}）：' + " · ".join(parts) + "</div>",
        unsafe_allow_html=True,
    )
    llm_details = timings.get("llm_details") or []
    detail_parts = []
    for item in llm_details:
        if not isinstance(item, dict):
            continue
        label = item.get("label") or item.get("key") or "LLM"
        calls = item.get("calls", 0)
        detail_parts.append(f"{label}: {_format_seconds(item.get('seconds'))} ({calls}次)")
    if detail_parts:
        st.markdown(
            f'<div style="font-size:0.74rem;color:#777;margin-top:0.15rem">LLM 分项：' + " · ".join(detail_parts) + "</div>",
            unsafe_allow_html=True,
        )


def _ensure_project() -> int:
    """确保有默认项目，返回 project_id。"""
    if "active_project_id" not in st.session_state:
        st.session_state["active_project_id"] = ensure_default_project()
    return st.session_state["active_project_id"]

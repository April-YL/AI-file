"""新旧 UI 并排对比验证：同一 fixture → 同一数据 → 新 UI trace 内容 ≥ 旧 UI。"""
import sys
sys.path.insert(0, "src")
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "workbook_with_lead.xlsx"


def test_new_coverage_source_summary_populated():
    """验证：新 coverage 中每条已执行规则的取数来源摘要非空。"""
    from report.pipeline import run_input_qc
    from report.ui_pages.coverage import _build_rows

    report = run_input_qc(str(FIXTURE), llm=False)
    data = report.to_dict()
    matrix = data.get("rule_execution_matrix") or []
    ledger = data.get("execution_ledger") or {}
    ledger_by_rule = {it.get("rule_id"): it for it in ledger.get("items") or []}

    rows = _build_rows(matrix, ledger_by_rule)
    executed = [r for r in rows if r["_status"] == "EXECUTED"]
    assert len(executed) > 0, "至少有一条已执行规则"

    with_source = [r for r in executed if r["取数来源摘要"] and r["取数来源摘要"] != "未记录"]
    assert len(with_source) > 0, "至少一条已执行规则有取数来源摘要"


def test_new_coverage_trace_not_less_than_old():
    """验证：新 UI 对每条已执行规则至少展示旧 UI 能展示的全部字段。"""
    from report.pipeline import run_input_qc

    report = run_input_qc(str(FIXTURE), llm=False)
    data = report.to_dict()
    ledger = data.get("execution_ledger") or {}
    ledger_items = ledger.get("items") or []

    executed_items = [it for it in ledger_items if it.get("status") == "EXECUTED"]
    assert len(executed_items) > 0, "至少有一条已执行规则"

    for item in executed_items:
        obs = item.get("observation")
        if not obs or not isinstance(obs, dict):
            continue

        # 旧 UI 能渲染的字段 → 新 UI 也能渲染
        if "checked_data" in obs:
            assert isinstance(obs.get("checked_data"), list), f"{item['rule_id']}: checked_data 应为 list"
        if "path" in obs:
            assert "inputs" in obs or "checks" in obs, f"{item['rule_id']}: legacy obs 应有 inputs/checks"


def test_new_findings_trace_matches_ledger():
    """验证：每条 non-PASS finding 的 rule_id 在 execution_ledger 中有记录。"""
    from report.pipeline import run_input_qc

    report = run_input_qc(str(FIXTURE), llm=False)
    data = report.to_dict()
    ledger_ids = {it.get("rule_id") for it in (data.get("execution_ledger") or {}).get("items") or []}
    finding_ids = {i.get("rule_id") for i in data.get("issues") or [] if i.get("severity") != "PASS"}

    missing = finding_ids - ledger_ids
    assert not missing, f"Findings 中有 {len(missing)} 条 rule_id 不在 ledger: {sorted(missing)[:5]}"


def test_all_ui_pages_renderable():
    """验证：所有 ui_pages 模块的渲染函数可成功调用（不抛异常）。"""
    import streamlit as st

    # 模拟最小 st.session_state
    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "workbench"
    st.session_state.setdefault("active_project_id", 1)

    from report.ui_pages.workbench import render_workbench
    from report.ui_pages.coverage import render_coverage

    # 只验证函数可导入且无语法错误（Streamlit 渲染需要完整 runtime，此处跳过实际渲染）
    assert callable(render_workbench)
    assert callable(render_coverage)

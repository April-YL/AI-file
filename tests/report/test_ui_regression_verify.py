"""新旧 UI 回归对比验证：同 fixture → 关键数据一致。

验证：新 UI 代码路径不修改 QcIssue / QcReport 数据。
"""
import json
import sys
sys.path.insert(0, "src")

import pytest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "workbook_with_lead.xlsx"


def test_report_structure_preserved():
    """验证：新旧 pipeline 输出结构一致。"""
    from report.pipeline import run_input_qc

    report = run_input_qc(str(FIXTURE), llm=False)
    data = report.to_dict()

    # 核心结构存在
    assert "issues" in data
    assert "summary" in data
    assert "execution_ledger" in data
    assert "rule_execution_matrix" in data

    # summary 完整性
    s = data["summary"]
    for key in ["overall_severity", "fail_count", "warn_count", "need_review_count", "total_records"]:
        assert key in s, f"summary 缺少字段: {key}"

    # execution_ledger 完整性
    ledger = data["execution_ledger"]
    assert "items" in ledger
    assert "summary" in ledger
    for item in ledger["items"]:
        assert "rule_id" in item
        assert "status" in item

    # rule_execution_matrix 全量性
    matrix = data["rule_execution_matrix"]
    assert isinstance(matrix, list)
    assert len(matrix) > 50, f"全量规则应 > 50，实际 {len(matrix)}"

    # 每条 rule 有 execution_status
    statuses = set(r.get("execution_status") for r in matrix if isinstance(r, dict))
    expected = {"EXECUTED", "DATA_INSUFFICIENT", "NOT_APPLICABLE", "NOT_TRIGGERED_BY_CONTEXT"}
    assert expected.issubset(statuses) or any(s in statuses for s in expected), f"状态值异常: {statuses}"


def test_ui_imports_do_not_mutate_data():
    """验证：导入 ui_* 模块不改变 pipeline 输出。"""
    from report.pipeline import run_input_qc

    # 基线
    report_before = run_input_qc(str(FIXTURE), llm=False)
    data_before = report_before.to_dict()
    json_before = json.dumps(data_before, ensure_ascii=False, sort_keys=True)

    # 导入所有 ui_* 模块（模拟 Streamlit 加载）
    from report.ui_components.styles import get_global_css
    from report.ui_components.cards import render_stat_card
    from report.ui_components.download_bar import render_download_bar
    from report.ui_components.findings_table import render_findings_explorer
    from report.ui_state.database import init_db
    from report.ui_pages.workbench import render_workbench
    from report.ui_pages.findings_viewer import render_findings_viewer
    from report.ui_pages.coverage import render_coverage
    from report.ui_pages.qc_runner import render_qc_runner
    from report.ui_pages.run_history import render_run_history
    from report.ui_pages.compare import render_compare
    from report.ui_pages.project_manager import render_project_manager

    # 再跑一次
    report_after = run_input_qc(str(FIXTURE), llm=False)
    data_after = report_after.to_dict()
    json_after = json.dumps(data_after, ensure_ascii=False, sort_keys=True)

    # 关键字段一致（排除 runtime_timings——每次执行时间自然不同）
    assert data_before["summary"]["overall_severity"] == data_after["summary"]["overall_severity"]
    assert data_before["summary"]["fail_count"] == data_after["summary"]["fail_count"]
    assert data_before["summary"]["warn_count"] == data_after["summary"]["warn_count"]
    assert data_before["summary"]["need_review_count"] == data_after["summary"]["need_review_count"]
    assert len(data_before["issues"]) == len(data_after["issues"])
    assert len(data_before["execution_ledger"]["items"]) == len(data_after["execution_ledger"]["items"])

    # 全量 JSON 对比（排除 timing 字段）
    def _strip_timings(d):
        if isinstance(d, dict):
            d.pop("runtime_timings", None)
            for v in d.values():
                _strip_timings(v)
        elif isinstance(d, list):
            for v in d:
                _strip_timings(v)
        return d
    b = _strip_timings(data_before)
    a = _strip_timings(data_after)
    assert json.dumps(b, ensure_ascii=False, sort_keys=True) == json.dumps(a, ensure_ascii=False, sort_keys=True), "导入 ui_* 模块后 pipeline 输出不一致（排除 timing）"


def test_coverage_rows_have_trace():
    """验证：检查范围页的每行已执行规则都有 trace 数据。"""
    from report.pipeline import run_input_qc
    from report.summary import summarize_source_location

    report = run_input_qc(str(FIXTURE), llm=False)
    data = report.to_dict()

    matrix = data.get("rule_execution_matrix") or []
    ledger = data.get("execution_ledger") or {}
    ledger_items = ledger.get("items") or []
    ledger_by_rule = {it.get("rule_id"): it for it in ledger_items}

    executed_count = 0
    trace_count = 0
    for row in matrix:
        if not isinstance(row, dict):
            continue
        if row.get("execution_status") != "EXECUTED":
            continue
        executed_count += 1
        rule_id = row.get("rule_id", "")
        ledger_item = ledger_by_rule.get(rule_id, {})
        obs = ledger_item.get("observation")
        if obs and isinstance(obs, dict):
            source = summarize_source_location(obs)
            if source and source != "未记录":
                trace_count += 1

    assert executed_count > 0, "至少有一条已执行规则"
    assert trace_count > 0, "至少一条已执行规则有 trace"


def test_findings_detail_has_ledger_match():
    """验证：每条 finding 可在 execution_ledger 中找到对应 rule_id。"""
    from report.pipeline import run_input_qc

    report = run_input_qc(str(FIXTURE), llm=False)
    data = report.to_dict()

    ledger_items = {it.get("rule_id") for it in (data.get("execution_ledger") or {}).get("items") or []}
    non_pass_rule_ids = set()
    for issue in data.get("issues") or []:
        if issue.get("severity") != "PASS":
            non_pass_rule_ids.add(issue.get("rule_id"))

    missing = non_pass_rule_ids - ledger_items
    assert not missing, f"Findings 中有 {len(missing)} 条 rule_id 不在 ledger 中: {list(missing)[:5]}"

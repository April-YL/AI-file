from __future__ import annotations

import inspect


def test_workbench_pending_queue_is_summary_only():
    from report.ui_pages.workbench import _group_by_priority, _render_pending_queue

    issues = [
        {"severity": "WARN", "rule_id": "w1", "message": "warn"},
        {"severity": "FAIL", "rule_id": "f1", "message": "fail"},
        {"severity": "NEED_REVIEW", "rule_id": "n1", "message": "review"},
        {"severity": "WARN", "rule_id": "w2", "message": "warn 2"},
    ]
    groups = _group_by_priority(issues)
    top_items = (groups["high"] + groups["manual"] + groups["other"])[:3]

    assert len(top_items) == 3

    source = inspect.getsource(_render_pending_queue)
    assert "st.expander" not in source
    assert "[:3]" in source
    assert "查看完整复核结果" in source


def test_runner_uses_vertical_audit_workflow():
    from report.ui_pages.qc_runner import _LLM_PRESETS, _RUNNER_STEPS, render_qc_runner

    source = inspect.getsource(render_qc_runner)

    assert "复核配置" in source
    assert "外部资料核对" in source
    assert "待复核底稿" in source
    assert "执行复核" in source
    assert "核对 TE / SAD / A3 / CRA" in source
    assert 'value=False, key="runner_external_check"' in source
    assert "LLM 默认关闭" in source
    assert "后端 LLM 调用逻辑保持不变" in source
    assert "runner_state" in source
    assert "服务商" in source
    assert "模型名称" in source
    assert "拖拽 Excel 到此处或点击选择" in source
    assert "测试连接" in source
    assert "deepseek-v4-flash" in _LLM_PRESETS["DeepSeek"]["models"]
    assert "deepseek-v4-pro" in _LLM_PRESETS["DeepSeek"]["models"]
    assert "gpt-5.4-nano" in _LLM_PRESETS["OpenAI"]["models"]
    for step in ["读取底稿", "识别工作表", "规则检查", "LLM 辅助", "生成报告", "生成标注副本", "保存运行记录"]:
        assert step in _RUNNER_STEPS
    assert "工作表识别" not in source


def test_project_manager_has_enterprise_actions_without_store_changes():
    from report.ui_pages.project_manager import render_project_manager, _render_entity_card

    manager_source = inspect.getsource(render_project_manager)
    card_source = inspect.getsource(_render_entity_card)

    assert "新建审计主体" in manager_source
    assert "切换到此" in card_source
    assert "编辑" in card_source
    assert "归档" in card_source
    assert "archive_project" in card_source


def test_execution_ledger_uses_fixed_fact_columns_and_evidence_link():
    from report.ui_components.execution_ledger_table import (
        build_execution_ledger_rows,
        render_execution_ledger_table,
        _evidence_rows_from_observation,
    )

    data = {
        "rule_execution_matrix": [
            {
                "rule_id": "lead_required_fields",
                "rule_code": "AE-001",
                "rule_name": "Lead 基本信息复核",
                "module": "K.00",
                "execution_status": "EXECUTED",
            }
        ],
        "execution_ledger": {
            "items": [
                {
                    "rule_id": "lead_required_fields",
                    "status": "EXECUTED",
                    "observation": {
                        "checked_data": [
                            {
                                "sheet": "K.00 Lead Sheet",
                                "section": "PM/TE/SAD 摘录",
                                "values_read": [
                                    {"label": "TE", "value": 1961000, "cell": "C5"},
                                    {"label": "SAD", "value": 261000, "cell": "C6"},
                                ],
                            }
                        ]
                    },
                }
            ]
        },
        "issues": [],
    }

    rows = build_execution_ledger_rows(data)
    assert len(rows) == len(data["rule_execution_matrix"])
    assert rows[0]["质检点ID"] == "AE-001"
    assert rows[0]["取数来源"] == "K.00 Lead Sheet!C5；K.00 Lead Sheet!C6"
    assert rows[0]["证据摘要"] == "查看详情"
    assert "None" not in " ".join(str(value) for value in rows[0].values())

    source = inspect.getsource(render_execution_ledger_table)
    for column in ["程序", "质检点ID", "质检点名称", "执行状态", "未执行原因", "异常记录", "取数来源", "证据摘要"]:
        assert f'"{column}"' in source
    assert '"执行结果"' not in source
    assert '"取数与判断说明"' not in source
    assert "detail_col" in source
    evidence_rows = _evidence_rows_from_observation(data["execution_ledger"]["items"][0]["observation"])
    assert evidence_rows == [
        {"sheet": "K.00 Lead Sheet", "section": "PM/TE/SAD 摘录", "cell": "C5", "row": "—", "label": "TE", "value": "1961000"},
        {"sheet": "K.00 Lead Sheet", "section": "PM/TE/SAD 摘录", "cell": "C6", "row": "—", "label": "SAD", "value": "261000"},
    ]


def test_findings_result_tabs_are_not_duplicate_or_ambiguous():
    from report.ui_pages.findings_viewer import render_findings_viewer
    from report.ui_components.findings_table import _render_finding_trace

    viewer_source = inspect.getsource(render_findings_viewer)
    trace_source = inspect.getsource(_render_finding_trace)

    assert "Findings 明细" in viewer_source
    assert "质检点执行台账" in viewer_source
    assert "基本信息摘录" in viewer_source
    assert "程序分组" not in viewer_source
    assert "人工复核" not in viewer_source
    assert "系统取数证据" in trace_source
    assert "expanded=False" in trace_source
    assert "取数与判断说明" not in trace_source


def test_runtime_breakdown_and_compact_layout_are_present():
    from report.ui_pages.findings_viewer import _render_runtime_timings
    from report.ui_pages.run_history import _render_runtime_breakdown
    from report.ui_components.styles import GLOBAL_STYLES, TOPBAR_STYLES, FILE_HEADER_STYLES, SIDEBAR_STYLES

    assert "ingest_seconds" in inspect.getsource(_render_runtime_timings)
    assert "rules_seconds" in inspect.getsource(_render_runtime_breakdown)
    assert "padding-top: 0.1rem" in GLOBAL_STYLES
    assert "padding: 7px 14px" in TOPBAR_STYLES
    assert "padding: 8px 12px" in FILE_HEADER_STYLES
    assert "background: #ffffff" in TOPBAR_STYLES
    assert "color: var(--ey-ink)" in TOPBAR_STYLES
    assert "background: var(--ey-yellow-muted)" not in SIDEBAR_STYLES
    assert "background: rgba(255,255,255,0.08)" in SIDEBAR_STYLES

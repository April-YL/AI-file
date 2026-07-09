from __future__ import annotations

from report.ui_components.execution_ledger_table import (
    build_execution_ledger_rows,
    build_execution_scope_summary,
)


def test_build_execution_ledger_rows_uses_matrix_as_only_skeleton():
    data = {
        "rule_execution_matrix": [
            {
                "rule_id": "lead_required_fields",
                "rule_code": "LEAD-001",
                "rule_name": "Lead 必填字段完整性",
                "module": "K.00",
                "execution_status": "EXECUTED",
                "finding_count": 1,
            },
            {
                "rule_id": "addition_llm_review",
                "rule_code": "AT-LLM-001",
                "rule_name": "新增测试说明复核",
                "module": "K.02.1",
                "execution_status": "LLM_DISABLED",
                "non_execution_reason": "本次 LLM 未开启。",
                "finding_count": None,
            },
            {
                "rule_id": "matrix_only_rule",
                "rule_code": "MX-001",
                "rule_name": "仅在矩阵登记的规则",
                "module": "UNKNOWN",
                "execution_status": "NOT_WIRED",
            },
        ],
        "execution_ledger": {
            "items": [
                {
                    "rule_id": "lead_required_fields",
                    "status": "EXECUTED",
                    "finding_count": 1,
                    "observation": {
                        "checked_data": [
                            {
                                "sheet": "K.00 Lead Sheet",
                                "section": "基准信息",
                                "values_read": [
                                    {
                                        "label": "分析日期",
                                        "value": "",
                                        "cell": "$B$8",
                                    }
                                ],
                            }
                        ],
                        "result_summary": "分析日期为空，触发 1 条规则提示。",
                    },
                },
                {
                    "rule_id": "ledger_extra_rule",
                    "status": "EXECUTED",
                    "finding_count": 0,
                },
            ],
        },
        "issues": [
            {
                "rule_id": "lead_required_fields",
                "severity": "FAIL",
                "message": "Lead 基准信息缺少分析日期。",
            },
            {
                "rule_id": "lead_required_fields",
                "severity": "PASS",
                "message": "PASS 不应进入异常摘要。",
            },
            {
                "rule_id": "ledger_extra_rule",
                "severity": "FAIL",
                "message": "ledger 额外项不应新增台账行。",
            },
        ],
    }

    rows = build_execution_ledger_rows(data)

    assert len(rows) == len(data["rule_execution_matrix"])
    assert {row["_rule_id"] for row in rows} == {
        "lead_required_fields",
        "addition_llm_review",
        "matrix_only_rule",
    }

    lead_row = rows[0]
    assert lead_row["质检点编号"] == "LEAD-001"
    assert lead_row["程序"] == "K.00 Lead"
    assert lead_row["执行状态"] == "已执行"
    assert lead_row["异常记录"] == "1 条"
    assert lead_row["取数来源"] == "K.00 Lead Sheet!$B$8"
    assert lead_row["取数与判断说明"] == "可查看系统取数证据"
    assert lead_row["异常摘要"] == "Lead 基准信息缺少分析日期。"

    llm_row = next(row for row in rows if row["_rule_id"] == "addition_llm_review")
    assert llm_row["执行状态"] == "LLM 未开启"
    assert llm_row["未执行原因"] == "本次 LLM 未开启。"
    assert llm_row["异常记录"] == "无"

    matrix_only = next(row for row in rows if row["_rule_id"] == "matrix_only_rule")
    assert matrix_only["执行状态"] == "待接入"
    assert matrix_only["取数来源"] == "未记录"
    assert matrix_only["取数与判断说明"] == "未记录取数与判断说明"


def test_build_execution_ledger_rows_returns_empty_when_matrix_missing():
    data = {
        "execution_ledger": {
            "items": [
                {
                    "rule_id": "ledger_only_rule",
                    "status": "EXECUTED",
                    "finding_count": 1,
                }
            ]
        },
        "issues": [
            {
                "rule_id": "ledger_only_rule",
                "severity": "FAIL",
                "message": "不应伪造完整台账。",
            }
        ],
    }

    assert build_execution_ledger_rows(data) == []


def test_execution_scope_summary_is_closed_with_pending_unknown_records():
    data = {
        "rule_execution_matrix": [
            {
                "rule_id": f"executed_rule_{idx}",
                "rule_code": f"EX-{idx:03d}",
                "rule_name": "已执行质检点",
                "module": "K.00",
                "execution_status": "EXECUTED",
            }
            for idx in range(80)
        ]
        + [
            {
                "rule_id": f"unknown_rule_{idx}",
                "rule_code": f"UN-{idx:03d}",
                "rule_name": "待补充执行记录质检点",
                "module": "K.01",
                "execution_status": "UNKNOWN",
            }
            for idx in range(10)
        ],
        "execution_ledger": {
            "items": [
                {
                    "rule_id": f"executed_rule_{idx}",
                    "status": "EXECUTED",
                    "finding_count": 0,
                }
                for idx in range(80)
            ]
        },
        "issues": [],
    }

    rows = build_execution_ledger_rows(data)
    summary = build_execution_scope_summary(data)

    assert len(rows) == len(data["rule_execution_matrix"])
    assert summary["total"] == 90
    assert summary["executed"] == 80
    assert summary["not_executed_with_reason"] == 0
    assert summary["pending_record"] == 10
    assert (
        summary["total"]
        == summary["executed"]
        + summary["not_executed_with_reason"]
        + summary["pending_record"]
    )
    assert summary["is_valid"] is True
    assert summary["errors"] == []

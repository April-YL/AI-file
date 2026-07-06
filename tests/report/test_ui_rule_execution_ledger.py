from __future__ import annotations

from report.ui_app import _audit_matrix_row


def test_ui_rule_execution_row_uses_backend_labels_without_how_terms():
    row = _audit_matrix_row(
        {
            "rule_id": "fa_list_required_fields",
            "rule_code": "FA-RC-001",
            "rule_name": "FA list 必填字段完整性",
            "module": "FA list",
            "execution_status": "EXECUTED",
            "execution_status_label": "已执行",
            "non_execution_reason": None,
            "finding_count": 0,
            "source_summary": "FA list / 资产清单",
            "trace_label": "可查看取数与判断说明",
            "trace_detail": {},
        }
    )

    assert row["执行状态"] == "已执行"
    assert row["取数来源摘要"] == "FA list / 资产清单"
    assert row["取数与判断说明"] == "可查看取数与判断说明"
    visible_text = " ".join(str(value) for key, value in row.items() if not key.startswith("_"))
    assert "HOW状态" not in visible_text
    assert "HOW明细" not in visible_text
    assert "execution_status" not in visible_text
    assert "how_status" not in visible_text


def test_ui_rule_execution_row_does_not_mark_unexecuted_as_passed():
    row = _audit_matrix_row(
        {
            "rule_id": "addition_semantic_review",
            "rule_code": "AT-LLM-001",
            "rule_name": "新增语义复核",
            "module": "K.02.1",
            "execution_status": "LLM_DISABLED",
            "execution_status_label": "LLM 未开启，语义复核未执行",
            "non_execution_reason": "本次 LLM 未开启。",
            "finding_count": None,
            "source_summary": "—",
            "trace_label": "不适用",
            "trace_detail": {},
        }
    )

    visible_text = " ".join(str(value) for key, value in row.items() if not key.startswith("_"))
    assert row["异常数量"] == "—"
    assert "通过" not in visible_text
    assert "成功" not in visible_text
    assert "完成" not in visible_text

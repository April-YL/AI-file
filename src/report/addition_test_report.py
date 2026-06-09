from __future__ import annotations

from typing import Any

from ingest.addition_test_sheet import (
    AdditionExecutionPathDataset,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
)
from rules.addition_consistency import build_addition_consistency_preview
from rules.models import QcIssue


def _module_payload(items) -> list[dict[str, Any]]:
    return [m.to_dict() for m in items or []]


def build_addition_sheet_section(
    addition_test: AdditionTestSheetDataset | None,
    addition_sample_output: AdditionSampleOutputDataset | None,
    addition_execution_path: AdditionExecutionPathDataset | None,
    issues: list[QcIssue] | None = None,
) -> dict[str, Any] | None:
    if addition_test is None and addition_sample_output is None and addition_execution_path is None:
        return None

    preview = build_addition_consistency_preview(
        addition_test,
        addition_sample_output,
        execution_path=addition_execution_path,
    )

    return {
        "source_file": addition_test.source_file if addition_test else (
            addition_sample_output.source_file if addition_sample_output else None
        ),
        "addition_test": {
            "source_sheet": addition_test.source_sheet if addition_test else None,
            "waiver_note_text": addition_test.waiver_note_text if addition_test else None,
            "waiver_note_rows": list(addition_test.waiver_note_rows) if addition_test else [],
            "amounts": (
                {k: v.to_dict() for k, v in addition_test.amounts.items()}
                if addition_test
                else {}
            ),
            "tested_samples": (
                [row.to_dict() for row in addition_test.tested_samples]
                if addition_test
                else []
            ),
            "module_assessments": _module_payload(
                addition_test.module_assessments if addition_test else []
            ),
            "recognition_confidence": addition_test.recognition_confidence if addition_test else None,
            "notes": list(addition_test.notes) if addition_test else [],
        },
        "addition_sample_output": {
            "source_sheet": addition_sample_output.source_sheet if addition_sample_output else None,
            "parameters": (
                {k: v.to_dict() for k, v in addition_sample_output.parameters.items()}
                if addition_sample_output
                else {}
            ),
            "amounts": (
                {k: v.to_dict() for k, v in addition_sample_output.amounts.items()}
                if addition_sample_output
                else {}
            ),
            "selected_samples": (
                [row.to_dict() for row in addition_sample_output.selected_samples]
                if addition_sample_output
                else []
            ),
            "module_assessments": _module_payload(
                addition_sample_output.module_assessments if addition_sample_output else []
            ),
            "recognition_confidence": (
                addition_sample_output.recognition_confidence if addition_sample_output else None
            ),
            "notes": list(addition_sample_output.notes) if addition_sample_output else [],
        },
        "addition_execution_path": (
            addition_execution_path.to_dict() if addition_execution_path else None
        ),
        "consistency_preview": preview.to_dict(),
        "finding_count": len([i for i in (issues or []) if i.rule_id.startswith("addition_")]),
        "issues": [i.to_dict() for i in (issues or []) if i.rule_id.startswith("addition_")],
    }

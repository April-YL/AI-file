from __future__ import annotations

import json
from pathlib import Path

from ingest.records import FaListDataset
from llm.config import LlmConfig, load_llm_config
from llm.review import enrich_report_with_llm
from report.summary import QcReport, build_report
from rules.execution_recorder import RuleExecutionRecorder, validate_execution_ledger
from rules.models import ColumnContext
from rules.runner import run_fa_list_rules


def run_fa_list_qc(
    dataset: FaListDataset,
    *,
    llm: bool | None = None,
) -> QcReport:
    ctx = ColumnContext(
        mapped_fields={m.standard_field for m in dataset.mapped_fields},
        source_sheet=dataset.source_sheet,
        procedure_code="FA_LIST",
    )
    recorder = RuleExecutionRecorder()
    issues = run_fa_list_rules(dataset.records, ctx, recorder=recorder)
    execution_ledger = recorder.to_ledger()
    validate_execution_ledger(execution_ledger, issues)
    report = build_report(
        source_file=dataset.source_file,
        source_sheet=dataset.source_sheet,
        procedure_code="FA_LIST",
        rule_ids=recorder.executed_rule_ids(),
        records=dataset.records,
        issues=issues,
        execution_ledger=execution_ledger,
    )
    config = load_llm_config(cli_enabled=llm)
    if config.enabled:
        report = enrich_report_with_llm(report, config, summary=None)
    return report


def export_report_json(report: QcReport, path: str | Path, *, indent: int = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=indent)

from __future__ import annotations

import json
from pathlib import Path

from ingest.records import FaListDataset
from report.summary import QcReport, build_report
from rules.models import ColumnContext
from rules.runner import FA_LIST_RULE_IDS, run_fa_list_rules


def run_fa_list_qc(dataset: FaListDataset) -> QcReport:
    ctx = ColumnContext(
        mapped_fields={m.standard_field for m in dataset.mapped_fields},
        source_sheet=dataset.source_sheet,
        procedure_code="FA_LIST",
    )
    issues = run_fa_list_rules(dataset.records, ctx)
    return build_report(
        source_file=dataset.source_file,
        source_sheet=dataset.source_sheet,
        procedure_code="FA_LIST",
        rule_ids=list(FA_LIST_RULE_IDS),
        records=dataset.records,
        issues=issues,
    )


def export_report_json(report: QcReport, path: str | Path, *, indent: int = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=indent)

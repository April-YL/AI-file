from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ingest.models import SheetKind
from ingest.records import (
    apply_verified_field_selections,
    rebuild_list_dataset_after_verified_selections,
)
from ingest.workbook_context import refresh_list_context_derivatives
from ingest.sheet_loader import load_asset_sheet_from_workbook
from llm.config import load_llm_config
from llm.ingest_review import (
    run_amount_group_identification_fallback,
    run_field_identification_fallback,
    run_sheet_identification_fallback,
)
from llm.router import LlmRouter
from agent.bulk_anomaly_guard import evaluate_bulk_anomaly_guard


WorkbookRunner = Callable[..., Any]


@dataclass(frozen=True)
class WorkbookQcOrchestrator:
    """Single controlled entry for an already loaded workbook QC run.

    The first migration slice deliberately delegates business work to the
    existing core runner.  Later slices attach shared runtime controls here;
    ingest, rules and reporting remain owned by their current modules.
    """

    core_runner: WorkbookRunner

    def run(self, workbook_context: Any, **kwargs: Any) -> Any:
        config = kwargs.get("llm_config")
        if config is None:
            config = load_llm_config(cli_enabled=kwargs.get("llm"))
        router = LlmRouter(config)
        source_path = Path(str(getattr(workbook_context, "source_file", "")))
        if source_path.suffix.lower() in {".xlsx", ".xlsm", ".xlsb"} and source_path.exists():
            reorganized = False
            structure = getattr(workbook_context, "structure", None)
            if structure is not None:
                for attr_name, collection_name, sheet_kind in (
                    ("fa_list", "fa_list_sheets", SheetKind.FA_LIST),
                    ("addition_list", "addition_lists", SheetKind.ADDITION_LIST),
                    ("disposal_list", "disposal_lists", SheetKind.DISPOSAL_LIST),
                ):
                    if getattr(workbook_context, attr_name, None) is not None:
                        continue
                    decision = run_sheet_identification_fallback(
                        config,
                        structure,
                        sheet_kind,
                        router=router,
                    )
                    if decision is None:
                        continue
                    dataset = load_asset_sheet_from_workbook(
                        source_path,
                        sheet_kind,
                        sheet_name=decision.sheet_name,
                        max_rows=None,
                        sheet_resolution=decision,
                    )
                    setattr(workbook_context, attr_name, dataset)
                    collection = getattr(workbook_context, collection_name, None)
                    if isinstance(collection, list):
                        collection.append(dataset)
                    structure.sheet_resolutions[decision.sheet_name] = decision
                    reorganized = True
            for dataset, sheet_kind in (
                (getattr(workbook_context, "fa_list", None), SheetKind.FA_LIST),
                (getattr(workbook_context, "addition_list", None), SheetKind.ADDITION_LIST),
                (getattr(workbook_context, "disposal_list", None), SheetKind.DISPOSAL_LIST),
            ):
                if dataset is None:
                    continue
                selections = run_field_identification_fallback(
                    config,
                    dataset,
                    router=router,
                )
                applied = apply_verified_field_selections(
                    dataset,
                    workbook_path=source_path,
                    selections=selections,
                )
                verified_amount_group_id = (
                    run_amount_group_identification_fallback(
                        config,
                        dataset,
                        sheet_kind,
                        router=router,
                    )
                    if sheet_kind in {SheetKind.ADDITION_LIST, SheetKind.DISPOSAL_LIST}
                    else None
                )
                if applied or verified_amount_group_id:
                    reorganized = rebuild_list_dataset_after_verified_selections(
                        dataset,
                        workbook_path=source_path,
                        sheet_kind=sheet_kind,
                        applied_fields=applied,
                        verified_amount_group_id=verified_amount_group_id,
                    ) or reorganized
            if reorganized:
                refresh_list_context_derivatives(workbook_context)
        kwargs["llm_config"] = config
        kwargs["llm_router"] = router
        report = self.core_runner(workbook_context, **kwargs)
        guard = evaluate_bulk_anomaly_guard(report, workbook_context)
        runtime_timings = getattr(report, "runtime_timings", None)
        if isinstance(runtime_timings, dict):
            runtime_timings["delivery_guard"] = guard
        return report

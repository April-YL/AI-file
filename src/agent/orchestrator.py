from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ingest.records import apply_verified_field_selections
from llm.config import load_llm_config
from llm.ingest_review import run_field_identification_fallback
from llm.router import LlmRouter


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
            for dataset in (
                getattr(workbook_context, "fa_list", None),
                getattr(workbook_context, "addition_list", None),
                getattr(workbook_context, "disposal_list", None),
            ):
                if dataset is None:
                    continue
                selections = run_field_identification_fallback(
                    config,
                    dataset,
                    router=router,
                )
                apply_verified_field_selections(
                    dataset,
                    workbook_path=source_path,
                    selections=selections,
                )
        kwargs["llm_config"] = config
        kwargs["llm_router"] = router
        return self.core_runner(workbook_context, **kwargs)

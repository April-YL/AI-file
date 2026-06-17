# Frozen Architecture Code Mapping

This document maps the current repository codebase to the frozen target architecture contract.

This is a documentation-only mapping artifact. It does not redesign the system, introduce new layers, propose refactors, or modify runtime behavior.

Source of truth: `docs/frozen-top-level-architecture.md`

## Scope

- Purpose: map current files and responsibilities to the frozen architecture.
- Basis: current repository structure and Stage 3-7 architecture documents.
- Status: current-state mapping with known legacy exceptions.
- Non-goal: implementation plan, refactor plan, architecture evolution, or code change.

## Frozen Runtime Chain

```text
INPUT
  -> ORCHESTRATOR
  -> INGEST ENGINE
       - deterministic parsing
       - IDENTIFIER (semantic sub-layer)
       - ingest confidence
  -> STANDARDIZED MODEL DRAFT
  -> EARLY VALIDATION LOOP
  -> STANDARDIZED MODEL
  -> RULE ENGINE
  -> DECISION GATE
  -> CONTROL PLANE (SINGLETON)
  -> FINDING MODEL
  -> REPORT
```

`LLM ROUTER` is an infrastructure layer, not a runtime pipeline stage.

## Current Architecture Mapping

| Frozen module | Current files / locations | Current responsibility | Alignment status |
| --- | --- | --- | --- |
| INPUT / entry wrappers | `pyproject.toml`; `src/report/cli.py`; `src/report/ui_app.py`; `src/fa_qc_ui.py`; `src/report/ui_launcher.py`; `src/ingest/cli.py`; `scripts/start-ui.*`; `启动质检界面.bat` | CLI, UI, and diagnostic startup surfaces. `fa-qc-run` and UI enter the QC path through report pipeline functions. `fa-qc-diagnose` enters an ingest diagnostic path. | Mostly aligned as wrappers. Diagnostic and scripts paths are secondary paths, not the primary runtime chain. |
| ORCHESTRATOR | `src/report/pipeline.py` (`run_input_qc`, `run_workbook_qc_from_path`, `run_workbook_qc`) | Main execution control for workbook/CSV input, ingest loading, rule ordering, LLM option handling, report assembly, and export handoff. | Partially aligned. This file is the current control node, but it also contains Control Plane-like routing, Decision Gate-like aggregation, LLM orchestration, and report assembly behavior. |
| INGEST ENGINE | `src/ingest/workbook_ingest.py`; `src/ingest/workbook_context.py`; `src/ingest/workbook_reader.py`; `src/ingest/workbook_structure.py`; `src/ingest/sheet_classifier.py`; `src/ingest/sheet_loader.py`; `src/ingest/field_mapping.py`; `src/ingest/field_mapping_policy.py`; `src/ingest/header_detection.py`; `src/ingest/records.py`; `src/ingest/summary_sheet.py`; `src/ingest/lead_sheet.py`; `src/ingest/lead_sheet_blocks.py`; `src/ingest/rollforward_sheet.py`; `src/ingest/addition_test_sheet.py`; `src/ingest/disposal_test_sheet.py`; `src/ingest/k02_test_sheet.py`; `src/ingest/k03_sheet.py`; `src/ingest/reconciliation.py`; `src/ingest/sheet_period_routing.py`; `src/ingest/constants.py`; `src/ingest/models.py`; `src/ingest/case_library.py` | Workbook reading, sheet classification, header detection, field mapping, table extraction, sheet-specific semantic parsing, and context construction. | Mostly aligned. Ingest already performs technical parsing and some semantic enrichment. Current legacy coupling: `src/ingest/reconciliation.py` and `src/ingest/rollforward_sheet.py` import utility functions from `src/rules/`. |
| IDENTIFIER semantic sub-layer | `src/llm/ingest_review.py`; `src/llm/ingest_profiles.py`; `src/ingest/lead_adjustment_grid.py`; `src/ingest/k03_sheet.py` LLM candidate context; parts of `src/llm/summary_psp_review.py` | Semantic recognition support for noisy sheets, workbook profile review, layout/section interpretation, and contextual field recognition. | Concept exists, but current code places LLM-assisted identifier behavior mostly in `src/llm/` and calls it from `src/report/pipeline.py`. In the frozen architecture, IDENTIFIER is an ingest-owned semantic sub-layer. |
| STANDARDIZED MODEL DRAFT | `src/ingest/workbook_ingest.py`; `src/ingest/workbook_context.py`; sheet/domain dataclasses in `src/ingest/*` | Intermediate workbook context and parsed sheet objects before full readiness is established. | Partially aligned. The model carriers exist, but draft vs finalized model is not explicit in current code. |
| EARLY VALIDATION LOOP | Ingest confidence fields and warnings such as `usable_for_rules`, `recognition_confidence`, `section_conflicts`, `missing_components`; `src/llm/ingest_review.py` review outputs | Structural readiness, confidence, and missing-component signals used before or around rule execution. | Implicit only. There is no centralized early validation stage yet. |
| STANDARDIZED MODEL | `src/ingest/workbook_context.py` (`WorkbookQcContext`); `src/ingest/workbook_ingest.py` (`WorkbookIngestContext`); parsed datasets from `src/ingest/*` | The structured workbook context consumed by rule execution and report construction. | Mostly aligned as current model carrier. |
| RULE ENGINE | `src/rules/*`, including `runner.py`, `lead_runner.py`, `rollforward_runner.py`, `addition_runner.py`, `disposal_runner.py`, `k03_runner.py`, `delivery_completion.py`, `psp_completion.py`, `registry.py`, and rule-specific modules | Deterministic QC checks, rule execution, rule metadata, and `QcIssue` creation. | Mostly aligned. Current nuance: `psp_completion.py` can consume optional LLM review results supplied by pipeline; it does not call the model itself. |
| DECISION GATE | Embedded in `src/report/pipeline.py`; `src/report/summary.py` (`build_report`, `worst_severity`) | Collects rule outputs, attaches metadata, derives overall severity/counts, and prepares report-level issue structure. | Not explicit. Current decision gate behavior is split across pipeline and report summary aggregation. |
| CONTROL PLANE (SINGLETON) | Embedded in `src/report/pipeline.py`; LLM flags in `src/report/cli.py` and `src/report/ui_app.py`; helper-level `should_review_*` logic in `src/llm/*` | Decides whether optional LLM review/enrichment is triggered, handles fallback-like behavior, and routes some ambiguity review. | Not explicit and not singleton in code. Current policy is distributed across pipeline, CLI/UI flags, and LLM helper modules. |
| LLM ROUTER infrastructure | Current low-level and helper modules in `src/llm/*`, especially `client.py`, `config.py`, `env_loader.py`, `redact.py`, `workbook_payload.py`, `prompts.py`, and review modules | LLM configuration, HTTP calls, redaction, prompt helpers, workbook payload construction, semantic review, and report enrichment. | Router is not implemented as a single infrastructure service. Current model calls are inside `src/llm/*` helpers and a diagnostic script. Current legacy coupling: `src/llm/review.py` depends on `report.summary.QcReport`. |
| FINDING MODEL | `src/rules/models.py` (`Severity`, `QcIssue`, `ColumnContext`); `src/report/summary.py` (`QcReport`, `ReportSummary`, `AssetResult`); LLM review issue outputs; ingest review report sections | Carries findings, severities, issue metadata, report summaries, ingest risks, and manual review sections. | Partially aligned. `QcIssue` is the de facto finding carrier, but final impact is currently split across rules, LLM helpers, and report structures. |
| REPORT / presentation and delivery | `src/report/summary.py`; `src/report/export_json.py`; `src/report/export_review_html.py`; `src/report/export_annotated_workbook.py`; `src/report/*_sheet_report.py`; `src/report/manual_review.py`; `src/report/procedure_labels.py`; `src/report/ooxml_workbook.py`; UI/CLI output handling | Builds JSON/HTML/XLSX outputs, annotated workbook copies, section summaries, manual review displays, and UI/CLI delivery artifacts. | Mostly aligned as delivery. Current exceptions: some report/export code performs derived severity/stat aggregation, and `export_json.py` also contains a legacy standalone FA-list QC path with optional LLM enrichment. |
| Tests | `tests/*` | Unit, regression, and behavior checks for ingest, rules, reports, LLM helpers, and pipeline behavior. | Test-only. Not part of runtime architecture. |
| Scripts / diagnostics | `scripts/*` | Local diagnostics, regression helpers, data inspection, LLM connection tests, and utility scripts. | Auxiliary. Not part of the primary runtime chain. |
| Test fixtures | `tests/fixtures/*` | Sanitized CSV/XLSX/JSON fixtures used by tests and regression checks. | Verification assets. They are not runtime input sources for production QC execution. |
| Domain / source materials | `固定资产质检agent/资料库/*` | Tracked SOP, checklist, template workbooks, SAP depreciation samples, and source PDFs used as domain reference material. | Domain assets. They inform development and testing but are not part of the primary runtime pipeline. |
| Agent collaboration assets | `.cursor/agents/*`; `.cursor/rules/*`; `.cursor/skills/*`; `AGENTS.md`; `docs/agent-collaboration.md`; `docs/data-security.md` | Agent prompts, collaboration rules, safety rules, and project working agreements. | Governance and collaboration layer. These files affect how agents work on the repository, but they are not QC runtime modules. |
| Project configuration | `.gitignore`; `.env.example`; `pyproject.toml` | Ignore rules, non-secret environment template, package metadata, dependencies, pytest configuration, and console-script entry points. | Project governance/configuration. Not a pipeline layer, but relevant to reproducibility and guard enforcement. |
| Planning / architecture docs | `docs/*.md`; `docs/decisions/*`; `docs/handoff/*`; tracked `docs/planning/*.md` | Architecture contracts, ADRs, handoff notes, rule planning, and methodology docs. | Documentation artifacts. They define or explain behavior but do not execute QC logic. |
| Tracked diagnostic artifacts | tracked files under `artifacts/` such as `case_*.json` and `case_*.md` | Historical diagnostic outputs and regression notes that were committed in the current repository state. | Non-runtime artifacts. They should not be interpreted as current pipeline output generation logic. |

## Current Responsibility Drift And Legacy Exceptions

These items describe current repository reality. They are not refactor instructions.

1. `src/report/pipeline.py` is the current runtime control center, but it also performs LLM trigger decisions, issue collection, delivery checks, report section assembly, and some post-report mutation.

2. The frozen architecture has a single `LLM ROUTER` infrastructure layer. Current code does not yet have a single router. Model calls are made by multiple helper modules inside `src/llm/`.

3. IDENTIFIER behavior exists, but is not fully owned by `src/ingest/`. Current LLM-assisted ingest review lives mainly in `src/llm/ingest_review.py` and is triggered from the report pipeline.

4. Early Validation Loop behavior is implicit. Confidence, missing-component, and readiness signals exist, but there is no centralized early validation module or stage.

5. Control Plane behavior is distributed. Runtime flags, pipeline branches, helper-level `should_review_*` functions, and fallback handling collectively decide when LLM review is invoked.

6. Some LLM helpers create `QcIssue` objects directly. Under the frozen architecture, the Finding Model is the only impact carrier and Control Plane owns decision routing.

7. `src/report/export_json.py` can invoke final LLM enrichment. This is a legacy exception because report/export should be presentation and delivery only under the frozen architecture.

8. `src/report/export_json.py` also contains `run_fa_list_qc()`, a legacy standalone FA-list QC path that runs rules and may invoke LLM enrichment. This is not the primary workbook runtime chain.

9. Report builders and workbook annotation exporters compute derived severities and summary statistics for display. These are presentation-derived aggregations today, but they blur the frozen boundary between Finding Model and Report.

10. `src/rules/psp_completion.py` can consume optional LLM review results through a callback supplied by the pipeline. It does not call LLM directly, but it has a semantic-review dependency embedded in rule execution.

11. `src/ingest/reconciliation.py` and `src/ingest/rollforward_sheet.py` import parsing or helper functions from `src/rules/`. This creates an ingest-to-rules dependency even though ingest is expected to prepare data before rule execution.

12. `src/llm/review.py` imports `report.summary.QcReport`, so final LLM enrichment is coupled to report data structures instead of going through a neutral LLM Router and Finding Model boundary.

## Direct LLM Call Inventory

The current production model call boundary is concentrated in `src/llm/*`, with one diagnostic script exception.

| Location | Current role | Architecture note |
| --- | --- | --- |
| `src/llm/client.py` | Low-level OpenAI-compatible HTTP client via `chat_completion_json`. | Infrastructure primitive. In the frozen architecture, this should be used behind LLM Router. |
| `src/llm/addition_review.py` | K.02 Addition semantic review. | Current helper calls model directly through client. |
| `src/llm/disposal_review.py` | K.02 Disposal semantic review. | Current helper calls model directly through client. |
| `src/llm/ingest_review.py` | Workbook ingest semantic review. | Current helper calls model directly; conceptually belongs to ingest IDENTIFIER usage through router. |
| `src/llm/lead_adjustment_review.py` | Lead adjustment semantic review. | Current helper calls model directly through client. |
| `src/llm/lead_review.py` | Lead semantic review. | Current helper calls model directly through client. |
| `src/llm/review.py` | Generic FA-list/report enrichment review. | Current helper calls model directly through client. |
| `src/llm/rollforward_notes_review.py` | K.01 rollforward notes review. | Current helper calls model directly through client. |
| `src/llm/summary_psp_review.py` | Summary PSP and package review. | Current helper calls model directly through client. |
| `scripts/test_llm_connection.py` | Local LLM connectivity diagnostic. | Diagnostic-only exception, not primary runtime pipeline. |

## Non-Core Runtime Paths

The following paths should not be interpreted as the primary QC runtime chain:

- `src/ingest/cli.py` and `fa-qc-diagnose`: ingest diagnostic path.
- `scripts/*`: local diagnostics, regression, data inspection, transcript, and utility paths.
- `outputs/`, `.tmp/`, `.pytest_cache/`, `.venv/`, `__pycache__/`: runtime, cache, environment, or generated artifacts.
- `src/fixed_asset_qc_agent.egg-info/`: ignored packaging/build metadata.
- `agent-transcripts/`: agent interaction artifacts.
- ignored files under `artifacts/`: local diagnostic outputs not part of the runtime chain.
- tracked files under `artifacts/`: historical diagnostic artifacts preserved in the current repository state, not core logic.
- `固定资产质检agent/案例库/`: ignored local case workbooks.
- `固定资产质检agent/质检测试结果/`: ignored local QC outputs.
- ignored generated files under `固定资产质检agent/资料库/`, such as annotated workbook copies.
- `docs/history/`, `docs/reports/`, and ignored files under `docs/planning/`: local history, reporting, or generated planning artifacts not part of runtime execution.
- `tests/*`: verification paths, not production execution paths.

## Guard Implications For Later Stages

This section records enforcement implications only. It does not implement a guard.

1. Because current code has legacy boundary exceptions, any Architecture Guard should start in warning or report mode.

2. A safe first guard rule is: no new direct `chat_completion_json` calls outside `src/llm/` and approved diagnostic scripts.

3. A safe first guard rule is: `src/rules/` must not directly import `llm` modules or LLM clients.

4. A safe first guard rule is: report/export code should not add new LLM calls beyond documented legacy exceptions.

5. A safe first guard rule is: new pipeline stages should not be added without updating the frozen architecture contract.

## Mapping Conclusion

The current repository already contains the functional ingredients of the frozen architecture, but several target responsibilities are still implemented as mixed or implicit behavior:

- Orchestration, Control Plane, Decision Gate, and report assembly are currently concentrated in `src/report/pipeline.py`.
- LLM routing is not centralized as infrastructure.
- IDENTIFIER exists as behavior, but is not fully owned by ingest.
- Finding impact is carried mainly by `QcIssue`, then expanded into report structures.
- Report is mostly delivery, but still contains some legacy enrichment and aggregation behavior.

This document should be used as the baseline for future implementation alignment work. It must not be read as permission to change architecture or runtime behavior.

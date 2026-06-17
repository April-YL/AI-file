# Unified System Architecture

This document is a synthesis of the system reality already mapped in Stage 3
through Stage 6. It is a system reality mapping artifact, not a design proposal.

Scope constraints:

- This is a summary of the current runtime structure.
- It does not introduce a new architecture.
- It does not idealize the code into a desired layered design.
- It is based only on current code behavior and the Stage 3-6 analysis outputs.
- It does not change pipeline, rules, ingest, LLM prompts, report exports, or
  runtime behavior.

## Unified Layered Architecture

The current system naturally presents six runtime layers. These layers are a
fact-based reading of the existing code path, not a requested refactor target.

| Layer | Current Runtime Nodes | Actual Responsibility | Output To Next Layer |
| --- | --- | --- | --- |
| Execution Layer | CLI `fa-qc-run`, UI `fa-qc-ui` / Streamlit, `run_input_qc()` | Accepts user-triggered input, routes CSV vs Excel, passes control into the QC pipeline. | File path, sheet overrides, LLM flag, delivery context |
| Data Layer | `load_workbook_context()`, `load_workbook_ingest()`, sheet classifier, per-sheet parsers | Converts workbook/CSV into semantic datasets such as Summary, Lead, K.01, K.02, K.03, FA list, reconciliation objects. | `WorkbookQcContext` or `FaListDataset` |
| Rule Decision Layer | `run_workbook_qc()`, `run_fa_list_rules()`, `run_lead_rules()`, `run_addition_rules()`, `run_disposal_rules()`, `run_k03_rules()`, `run_rollforward_rules()`, delivery rules | Applies deterministic checks for fields, totals, thresholds, reconciliations, samples, package completeness, and delivery blockers. | Deterministic `QcIssue` list and report sections |
| LLM Cognitive Layer | Summary PSP review, Lead semantic review, K.02 semantic reviews, K.01 notes review, ingest review, final enrichment | Adds bounded semantic review, ambiguity surfacing, narrative sufficiency checks, and report enrichment when enabled. | Additive LLM `QcIssue`, `ingest_review_section`, `llm_enrichment` |
| Impact Layer | `QcIssue`, `attach_rule_metadata()`, `build_report()`, severity aggregation, manual review sections | Converts rule and allowed LLM outputs into structured findings, severity counts, by-rule grouping, and review routing. | `QcReport` |
| Presentation Layer | JSON export, HTML review export, annotated workbook export, UI display, CLI output | Presents the completed report and workbook annotations for reviewer action. | JSON / HTML / annotated XLSX / UI downloads |

Condensed architecture:

```text
Execution
-> Data semantic model
-> Rule decision engine
-> Bounded LLM cognition
-> QcIssue and review routing
-> Report/export presentation
```

## Cross-Layer Interaction Graph

The system is not a pure one-way chain because LLM and delivery checks consume
prior rule outputs, and report exports consume the completed `QcReport`. The
current interaction graph is:

```text
CLI / UI / scripts
-> run_input_qc()
-> CSV branch or Excel workbook branch

CSV branch
-> load_fa_list_csv()
-> run_fa_list_qc()
-> QcReport
-> JSON / HTML

Excel branch
-> run_workbook_qc_from_path()
-> load_workbook_context()
-> load_workbook_ingest()
-> WorkbookQcContext
-> run_workbook_qc()
   -> deterministic rules
   -> optional bounded LLM reviews
   -> optional delivery checks
   -> build_report()
   -> manual review sections
   -> optional final LLM enrichment
-> QcReport
-> JSON / HTML / annotated XLSX
```

### Data Across Layers

| From | To | Actual Transfer |
| --- | --- | --- |
| Execution Layer | Data Layer | Input path, optional sheet overrides, CSV/Excel decision. |
| Data Layer | Rule Decision Layer | `WorkbookQcContext` containing Summary, Lead, Rollforward, FA list, K.02 objects, K.03 sheets, reconciliations, structure metadata. |
| Data Layer | LLM Cognitive Layer | Semantic excerpts, workbook sheet titles, previews, recognition confidence, notes, prior deterministic issues. |
| Rule Decision Layer | LLM Cognitive Layer | Prior `QcIssue` list for semantic context. LLM uses this as already-determined fact, not as something to override. |
| Rule Decision Layer | Impact Layer | Deterministic `QcIssue` objects and category-specific sections. |
| LLM Cognitive Layer | Impact Layer | Additive semantic `QcIssue`, ingest review results, or final enrichment only. |
| Impact Layer | Presentation Layer | `QcReport` with issues, summary counts, manual sections, ingest review section, optional LLM enrichment. |

### How Rules Consume Semantic Data

| Semantic Data | Rule Consumers | Decision Type |
| --- | --- | --- |
| Summary PSP rows | PSP completion, addition/disposal package checks | Procedure execution and package completeness |
| Lead materiality, SAD, TE, CRA, TT | Lead rules, K.01, K.02, K.03 | Threshold and risk-context decisions |
| K.01 rollforward totals, movements, notes | K.01 rules, K.02 reconciliation, K.03 context | Reconciliation and material difference decisions |
| FA list records and mapped fields | FA list rules, K.03 policy review, reconciliation context | Asset master-data and policy-context decisions |
| K.02 addition/disposal tests and sample outputs | K.02 addition/disposal runners | Sample matching, sampling parameter, package and detailed-test decisions |
| K.03 sheets | K.03 runner | Depreciation TOD and policy review decisions |
| Prior issues | Delivery checks | First/final delivery readiness decisions |

### How LLM Interacts With Rules And Report

| Interaction | Current Behavior |
| --- | --- |
| LLM before a rule | Summary waiver review produces `WaiverSemanticReview`, which PSP rules may consume. |
| LLM beside a rule | Lead, K.02, and K.01 notes reviews add semantic issues alongside deterministic findings. |
| LLM after ingest | Ingest review produces a separate `ingest_review_section`, not a business finding. |
| LLM after report | Final enrichment attaches `llm_enrichment` to the finished `QcReport`. |
| LLM vs deterministic conflict | Rules win. LLM cannot convert deterministic `FAIL` to `PASS`. |

### Failure Modes And Propagation

| Failure Mode | Control In Unified Architecture |
| --- | --- |
| Over-interpretation | LLM sufficiency does not create PASS and cannot remove existing findings. |
| Judgment drift | Existing deterministic `QcIssue.severity` is not modified by LLM. |
| Hallucinated justification | LLM is bounded to supplied workbook context, previews, excerpts, and prior issues. |
| Missing data completion | Missing ingest or missing rule input remains missing until data/ingest changes. |
| Invalid or failed LLM call | Deterministic rules continue and the report remains valid without LLM output. |

## Single Source Of Truth Identification

| System Role | Current Node | Why It Is The Source Of Truth |
| --- | --- | --- |
| Control node | `run_input_qc()` | Shared by CLI and UI. It performs the first runtime branch: CSV vs Excel workbook. |
| Workbook orchestration node | `run_workbook_qc()` | Governs the workbook execution sequence: Summary, Lead, K.02, K.03, ingest review, K.01, delivery, report, final enrichment. |
| Data semantic source | `WorkbookQcContext` | Holds the structured workbook semantic model consumed by rules and LLM. |
| Decision engine | `src/rules/*` runners and checks | Owns deterministic truth: fields, thresholds, reconciliations, sampling, severity-producing business findings. |
| Cognitive assistant | `src/llm/*` helpers | Provides bounded semantic review, explanation, ambiguity surfacing, and report enrichment. |
| Finding object | `QcIssue` | Common carrier for deterministic and allowed LLM-assisted business findings. |
| Report object | `QcReport` | Aggregates issues, severity counts, sections, manual review prompts, ingest review, and enrichment. |
| Presentation surface | export functions and Streamlit UI | Converts `QcReport` into JSON, HTML, annotated workbook, and interactive display. |

Important authority split:

```text
Control truth: run_input_qc()
Workbook orchestration truth: run_workbook_qc()
Data truth for this run: WorkbookQcContext
Decision truth: rules
Cognitive assistance: LLM
Delivery artifact truth: QcReport and exports
```

## End-to-End System Flow

### Full Excel Workbook Lifecycle

```text
Input workbook
-> CLI/UI calls run_input_qc()
-> Excel branch calls run_workbook_qc_from_path()
-> load_workbook_context()
-> load_workbook_ingest()
-> sheet classification and per-sheet parsing
-> WorkbookQcContext
-> run_workbook_qc()
   -> FA list rules if FA list exists
   -> Summary PSP and package checks
   -> Lead rules
   -> K.02 Addition rules
   -> K.02 Disposal rules
   -> K.03 Depreciation rules
   -> optional LLM ingest review
   -> K.01 Rollforward rules
   -> optional delivery checks
   -> build_report()
   -> manual review sections
   -> optional final LLM enrichment
-> QcReport
-> export_report_json()
-> export_review_html()
-> export_annotated_workbook()
-> JSON / HTML / annotated XLSX
```

### CSV Lifecycle

```text
Input CSV
-> run_input_qc()
-> CSV branch
-> load_fa_list_csv()
-> run_fa_list_qc()
-> FA list rules
-> optional delivery issue append
-> manual review sections
-> QcReport
-> JSON / HTML outputs
```

### QcIssue Lifecycle

```text
Semantic data condition
-> deterministic rule trigger or allowed LLM semantic trigger
-> QcIssue
-> attach_rule_metadata()
-> build_report()
-> severity counts and by-rule grouping
-> report/export/annotation
-> reviewer action
```

## System Boundary Definition

### Deterministic Boundary

Deterministic means the system uses structured fields, amounts, thresholds,
reconciliations, or explicit execution state.

Current deterministic areas:

- Sheet existence and recognized semantic objects, subject to ingest confidence.
- Required fields and mapped standard columns.
- Asset id uniqueness and asset-level amount consistency.
- Rollforward existence, sections, movements, abnormal amounts, and differences.
- SAD/TE/CRA/TT-driven checks where the values are available.
- Addition and disposal sample matching and package completeness.
- K.03 TOD and policy checks.
- Delivery readiness based on prior issues and workbook evidence.
- Report severity aggregation from `QcIssue.severity`.

### Semantic Boundary

Semantic means the system evaluates explanation quality, ambiguity, narrative
sufficiency, or uncertain reading context.

Current semantic areas:

- PSP refusal reason sufficiency.
- Summary sheet semantic matching in ambiguous cases.
- Lead expectation and fluctuation explanation sufficiency.
- Lead adjustment layout and cross-account explanation review.
- K.02 addition/disposal explanation and evidence narrative review.
- K.01 notes sufficiency for material differences.
- Ingest low-confidence or missing-object review.
- Final report narrative enrichment.

Semantic outputs are bounded:

- They may add review-oriented findings or review prompts.
- They may route reviewer attention.
- They may enrich the report.
- They may not override deterministic rule conclusions.

### Presentation Boundary

Presentation means the system displays, exports, or annotates already-produced
findings and review prompts.

Current presentation areas:

- `QcReport.to_dict()`
- JSON report export
- HTML review export
- annotated workbook export
- Streamlit UI display and downloads
- CLI summary and exit code behavior
- `llm_enrichment` display
- `ingest_review_section` display and annotated workbook ingest review sheet

Presentation does not create deterministic audit truth. It carries the result
of rules, allowed LLM assistance, and report aggregation to the reviewer.

### Excluded From Decision Making

The following are outside the authoritative decision path:

- Bootstrap scripts that only start the UI or prepare `.venv`.
- Diagnostic CLI output from `fa-qc-diagnose`, unless its findings lead to later
  code or data changes.
- Regression scripts and maintenance scripts under `scripts/`.
- Runtime outputs under `outputs/` or local artifact directories.
- Agent transcripts, history exports, and collaboration records.
- Final LLM report enrichment text.
- LLM ingest review prompts as business findings; they are reading-layer review
  prompts only.
- Any LLM statement that conflicts with deterministic rules.

## Unified Architecture Summary

The current QC system is best described as a shared execution pipeline centered
on `run_input_qc()` and `run_workbook_qc()`.

Its data layer turns workbooks into semantic audit objects. Its rule layer owns
deterministic QC decisions and creates the authoritative findings. Its LLM layer
is a bounded cognitive assistant that can add semantic review signals, explain
ambiguity, and route attention, but cannot replace the rule engine. Its impact
and presentation layers convert `QcIssue` objects into `QcReport`, JSON, HTML,
annotated workbook outputs, and UI/CLI surfaces.

The natural architecture is therefore:

```text
User-triggered execution
-> semantic workbook model
-> deterministic rule decisions
-> bounded semantic assistance
-> QcIssue/report impact model
-> reviewer-facing exports
```


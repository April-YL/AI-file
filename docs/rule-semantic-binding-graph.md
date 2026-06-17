# Rule Semantic Binding Graph

This document maps the current QC rule system as it works in code. It does not
enumerate every raw rule implementation. The purpose is to show which semantic
objects, fields, and contexts actually drive QC decisions.

## Rule Category Map

| Rule Category | Runtime Entry | Semantic Role | Main Output |
| --- | --- | --- | --- |
| Summary | `check_psp_completion`, `check_addition_test_package`, `check_disposal_test_package` | Confirms PSP execution status, refusal reasons, and whether K.02 workpaper packages exist. | `QcIssue` plus `summary_sheet_section` |
| Lead | `run_lead_rules` | Provides materiality, risk, expectation analysis, movement context, and adjustment context. | `QcIssue`, `lead_sheet_section`, manual review sections |
| FA List | `run_fa_list_rules` | Checks asset-level master data integrity when an FA list is available. | Asset-level `QcIssue` |
| K.01 Rollforward | `run_rollforward_rules` | Checks rollforward existence, columns, abnormal amounts, reconciliation, SAD differences, and depreciation P/L linkage. | `QcIssue` plus `rollforward_sheet_section` |
| K.02 Addition | `run_addition_rules` | Checks addition list completeness, population logic, rollforward tie-out, sampling output, and detailed test linkage. | `QcIssue` plus `addition_sheet_section` |
| K.02 Disposal | `run_disposal_rules` | Checks disposal reconciliation, disposal list, sampling output, detailed test, and sample linkage. | `QcIssue` |
| K.03 Depreciation | `run_k03_rules` | Checks depreciation TOD by item and policy review workpapers. | `QcIssue` |
| Delivery | `check_delivery_completion` | Checks first/final delivery readiness using prior findings and workbook evidence. | Workbook-level `QcIssue` |

## Rule Binding Graph

Format: `Rule Category -> Data Object -> Field -> Context Role`.

| Binding | Context Role |
| --- | --- |
| Summary -> `SummarySheetDataset` -> `programs.execution_status` | Decides whether PSP procedures are executed, refused, or need review. |
| Summary -> `SummarySheetDataset` -> `programs.sheet_ref` | Links PSP rows to workbook sheet titles and K.02 package detection. |
| Summary -> `SummarySheetDataset` -> refusal / waiver text | Drives deterministic PSP review and optional LLM waiver reason review. |
| Lead -> `LeadSheetDataset` -> materiality / SAD / TE / TT / CRA | Supplies thresholds and risk context used by Lead, K.01, K.02, and K.03 checks. |
| Lead -> `LeadSheetDataset` -> `movement_rows`, `check_with_a3`, notes | Supports movement completeness, volatility, A3 tie-out, and rollforward reconciliation. |
| Lead -> `LeadSheetDataset` -> expectation and fluctuation narrative fields | Feeds deterministic sufficiency checks and optional LLM semantic review. |
| Lead -> `LeadSheetDataset` -> adjustment rows / extracted adjustment rows | Feeds Lead adjustment consistency and LLM layout review. |
| FA List -> `FaListDataset.records` -> asset id / original value / accumulated depreciation / NBV | Supports asset identity, amount consistency, and potential cross-check context. |
| FA List -> `ColumnContext.mapped_fields` -> mapped standard fields | Decides whether a field-level rule can run or must issue missing-field findings. |
| K.01 Rollforward -> `RollforwardSheetDataset` -> opening / additions / disposals / depreciation / closing | Drives movement, abnormal amount, and reconciliation checks. |
| K.01 Rollforward -> `ReconciliationCheck` -> source/target amount and difference | Links rollforward amounts to FA list or related sheets. |
| K.01 Rollforward -> Lead SAD and notes | Determines whether differences above SAD need explanation or review. |
| K.02 Addition -> `FaListDataset` addition list -> purchase amount / asset id / asset name | Drives list completeness, population homogeneity, and rollforward addition tie-out. |
| K.02 Addition -> `AdditionSampleOutputDataset` -> selected samples / TE / CRA / assertions / scope | Drives sampling output and sample pool consistency checks. |
| K.02 Addition -> `AdditionTestSheetDataset` -> tested samples / replacement reason / evidence fields | Drives sample matching and replacement reason checks. |
| K.02 Addition -> `AdditionExecutionPathDataset.path_kind` | Decides whether sampling rules are executed or skipped for waiver paths. |
| K.02 Disposal -> `DisposalListSummary` / disposal list -> disposal totals and row details | Drives disposal list and rollforward disposal reconciliation. |
| K.02 Disposal -> `DisposalSampleOutputDataset` and `DisposalTestSheetDataset` | Drives sampling, detailed test, and selected-vs-tested sample matching. |
| K.02 Disposal -> `DisposalExecutionPathDataset.path_kind` | Decides whether list, sampling, and detailed test checks are skipped. |
| K.03 Depreciation -> `K03SheetDataset` -> execution path, TOD rows, recalculation fields | Drives depreciation by-item test checks. |
| K.03 Depreciation -> policy review dataset plus FA list | Drives depreciation policy review against available asset master data. |
| Delivery -> `DeliveryCompletionContext.stage` -> first/final | Selects first-delivery or final-delivery readiness criteria. |
| Delivery -> prior `QcIssue` list -> open procedure, adjustment, or risk findings | Prevents delivery PASS when earlier unresolved findings remain. |
| Delivery -> workbook path / sheet titles / workbook context | Supports comments cleanup scan and sample evidence completeness checks. |

## Dependency Graph

### Data Dependency

`A -> B` means B needs data produced or held by A.

| Dependency | Meaning |
| --- | --- |
| Workbook ingest -> all rule categories | Rules run against structured datasets created by workbook ingestion, not raw Excel cells directly. |
| Summary -> K.02 Addition / K.02 Disposal | Summary programs and sheet references help identify execution path and package completeness. |
| Lead -> K.01 Rollforward | K.01 uses Lead materiality/SAD and movement context for difference and reconciliation checks. |
| Lead -> K.02 Addition / K.02 Disposal | K.02 uses Lead TE/CRA/SAD/risk context for sampling and reconciliation judgments. |
| Lead -> K.03 Depreciation | K.03 receives Lead context for TOD and policy checks. |
| Rollforward -> K.02 Addition / K.02 Disposal | K.02 addition and disposal amounts are tied back to rollforward movements. |
| Rollforward -> K.03 Depreciation | K.03 receives rollforward context for depreciation-related checks. |
| FA List -> FA List rules / K.03 Policy Review | FA list records drive asset master checks and support depreciation policy review when available. |
| Addition sample output -> Addition detailed test checks | Selected sample rows are compared with detailed test rows. |
| Disposal sample output -> Disposal detailed test checks | Selected disposal sample rows are compared with disposal detailed test rows. |
| Prior issues + workbook evidence -> Delivery | Delivery checks depend on unresolved earlier findings and workbook evidence status. |

### Evaluation Dependency

`A -> B` means A's result can affect B's judgment or presentation.

| Dependency | Meaning |
| --- | --- |
| LLM Lead adjustment layout result -> Lead adjustment total rule | Low-confidence layout recognition can gate strict adjustment total comparison. |
| Deterministic Lead issues -> Lead LLM semantic review context | Lead LLM review sees existing rule findings and adds semantic findings where needed. |
| Deterministic Addition issues -> Addition LLM semantic review context | Addition LLM review receives prior deterministic issues and adds semantic sufficiency findings. |
| Deterministic Disposal issues -> Disposal LLM semantic review context | Disposal LLM review receives prior deterministic issues and adds semantic sufficiency findings. |
| Deterministic K.01 issues -> Rollforward notes LLM review | K.01 notes LLM review focuses on differences already identified by deterministic checks. |
| All prior issues -> Delivery checks | Delivery readiness can fail because earlier procedure, evidence, adjustment, or risk issues remain open. |
| Rule issues -> `attach_rule_metadata` | Registry metadata enriches findings for reporting but does not change the underlying business conclusion. |
| All issues -> `build_report` | Report severity counts, overall severity, and by-rule summaries are derived from accumulated issues. |

### Pipeline Order

This is the current execution sequence inside `run_workbook_qc`. It is an
implementation order, not always a semantic dependency.

1. Build workbook sheet titles and semantic workbook wrapper.
2. Run FA list rules when `ctx.fa_list` exists.
3. Run Summary PSP and K.02 package checks when `ctx.summary` exists.
4. Run Lead rules and Lead semantic review when `ctx.lead` exists.
5. Run K.02 Addition rules when addition-related datasets exist.
6. Run K.02 Disposal rules.
7. Run K.03 Depreciation rules.
8. Run LLM ingest review when LLM is enabled.
9. Run K.01 Rollforward rules when `ctx.rollforward` exists.
10. Run Delivery checks when a delivery context is supplied.
11. Build `QcReport`.
12. Build manual review sections.
13. Run final report LLM enrichment when LLM is enabled.

## Decision Semantics Model

| Outcome | Current Meaning in Code |
| --- | --- |
| PASS | Usually represented by absence of non-PASS `QcIssue` for a check. It means required structured data was readable and no implemented rule produced a finding. |
| FAIL | Deterministic evidence contradicts the expected workpaper state: missing required fields, inconsistent totals, sample mismatch, required package missing, unresolved delivery blockers, or material unexplained differences. |
| WARN | A soft risk or quality concern exists but the code does not treat it as a hard failure. Examples include weak narratives, possible population issues, or policy review concerns that need attention. |
| NEED_REVIEW | The rule cannot safely conclude from structured data. Typical causes are unreadable or low-confidence ingest, missing context, ambiguous notes, external evidence references, or semantic sufficiency questions. |

Threshold behavior:

| Threshold / Context | Current Role |
| --- | --- |
| SAD | Used as a materiality threshold for K.01 rollforward differences and K.02 reconciliation investigation logic when Lead provides it. Missing SAD generally prevents a clean deterministic conclusion. |
| TE | Used mainly in K.02 sampling consistency and Lead volatility or threshold linkage contexts. It supports rule judgment but does not globally override all findings. |
| CRA | Used as risk/sampling context, especially in K.02 sampling output consistency and Lead risk threshold checks. |
| TT / GAM | Used inside Lead threshold and materiality-related checks. |
| Amount tolerance / rounding | Used by amount comparison rules to avoid false mismatches from Excel rounding or formatting differences. |

Ambiguity behavior:

| Situation | Actual Handling Pattern |
| --- | --- |
| Core dataset missing | The relevant category either skips dependent checks or emits `NEED_REVIEW` / package-completeness issues depending on the runner. |
| Lead not usable for rules | Lead runner emits a readability `NEED_REVIEW` and pauses dependent Lead checks. |
| Waiver / refusal path exists | Some K.02 sampling/list checks are skipped according to execution path; PSP and waiver reason sufficiency remain review subjects. |
| Difference exists but explanation quality is semantic | Deterministic checks identify the difference; LLM may add semantic review findings when enabled. |
| LLM fails or is disabled | Deterministic rules still run. LLM-only semantic findings or enrichment are absent, except where rules ask reviewer to enable LLM or perform manual review. |

## LLM Boundary Model

LLM is optional and controlled by `load_llm_config` through CLI/UI flags and
environment variables. The default configuration keeps LLM disabled unless
explicitly enabled.

### Where LLM Is Used

| Area | Runtime Use |
| --- | --- |
| Summary PSP | Reviews waiver/refusal reason sufficiency and sheet semantic matching. |
| Lead | Reviews adjustment layout, adjustment semantics, expectation analysis, and fluctuation explanation sufficiency. |
| K.02 Addition | Reviews semantic sufficiency of addition testing context, evidence, and explanations. |
| K.02 Disposal | Reviews semantic sufficiency of disposal testing context, evidence, and explanations. |
| Ingest review | Reviews selected ingest stability concerns using recognition metadata and previews; results go to a separate ingest review section. |
| K.01 Rollforward | Reviews notes explaining material rollforward differences. |
| Final report | Adds `llm_enrichment` summary and focus notes to the finished report. |

### Where LLM Is Not Allowed

| Boundary | Meaning |
| --- | --- |
| No deterministic override | LLM does not change deterministic rule severity from FAIL to PASS. |
| No amount recalculation authority | LLM does not become the source for formulas, totals, reconciliations, or threshold math. |
| No field mapping mutation in this pipeline | LLM review may flag ingest concerns, but it does not rewrite `WorkbookQcContext` during `run_workbook_qc`. |
| No execution routing authority | LLM findings do not add new rule categories or change the fixed pipeline order. |

### Interaction With Rule Engine

LLM-assisted outputs are converted to `QcIssue` when they represent business
review findings. Those issues explicitly carry `review_source` and
`llm_review_type`. LLM ingest review is different: it is stored in
`ingest_review_section` and is described as a reading-layer review prompt, not
the same as a business rule finding.

## Rule -> Report Mapping

| Source | Mapping Path | Report Location |
| --- | --- | --- |
| Deterministic rule issue | Rule function -> `QcIssue` -> optional `attach_rule_metadata` -> `build_report` | Main issue list, severity counts, by-rule summary |
| LLM semantic business issue | LLM review helper -> `QcIssue` with LLM source fields -> optional metadata -> `build_report` | Main issue list and comments output, marked as LLM-assisted |
| Summary category | Summary checks -> issues plus `build_summary_sheet_section` | Main issue list plus `summary_sheet_section` |
| Lead category | Lead checks -> issues plus `build_lead_sheet_section` | Main issue list plus `lead_sheet_section` |
| K.01 Rollforward | Rollforward checks -> issues plus `build_rollforward_sheet_section` | Main issue list plus `rollforward_sheet_section` |
| K.02 Addition | Addition checks -> issues plus `build_addition_sheet_section` | Main issue list plus `addition_sheet_section` |
| K.02 Disposal | Disposal checks -> issues | Main issue list and procedure/by-rule grouping; no dedicated disposal section in `QcReport` currently. |
| K.03 Depreciation | K.03 checks -> issues | Main issue list and procedure/by-rule grouping; no dedicated K.03 section in `QcReport` currently. |
| Delivery | Delivery checks -> workbook-level issues | Main issue list, workbook-level severity counts, and delivery blockers. |
| LLM ingest review | `run_workbook_ingest_reviews` -> ingest review result dictionaries | `ingest_review_section`; annotated workbook can create `LLM识别复核【归档前删除】`. |
| Final LLM enrichment | `enrich_report_with_llm` -> `LlmEnrichment` | `llm_enrichment`; does not alter rule findings. |

Severity aggregation is centralized in `build_report`: overall severity follows
`FAIL > NEED_REVIEW > WARN > PASS`. Asset-level issues are separated from
sheet/workbook-level issues by whether `asset_id` is present.

## Rule Causality Chain

Causality in this system means:

`Data condition -> Rule trigger -> Evaluation result -> QcIssue -> Report impact`

This layer explains how a workbook fact becomes a QC finding. It is different
from dependency mapping: dependency mapping shows what a rule needs; causality
shows how a detected condition propagates into review consequences.

### Causality Types

| Type | Meaning | Decision Authority |
| --- | --- | --- |
| Deterministic causality | Structured data, thresholds, reconciliations, execution paths, or required fields directly trigger rule outcomes. | Can create FAIL, WARN, or NEED_REVIEW findings. |
| LLM-assisted causality | Existing ambiguity, weak narrative, waiver language, or semantic sufficiency concerns trigger LLM review when enabled. | Can add contextual findings or annotations, but does not override deterministic FAIL to PASS. |

### Materiality Breach Chain

| Step | Causal Propagation |
| --- | --- |
| Data condition | Lead provides SAD / materiality context; K.01 rollforward or related reconciliation data shows a difference above the relevant threshold. |
| Rule trigger | K.01 difference and reconciliation checks evaluate rollforward, Lead context, and notes. K.02 may also use Lead thresholds when checking addition/disposal reconciliation impact. |
| Evaluation result | If the difference is material and not adequately explained, deterministic rules produce FAIL or NEED_REVIEW depending on whether the data is conclusive. If explanation exists but sufficiency is semantic, optional LLM review can add review context. |
| `QcIssue` | The issue carries the relevant rule id, field, severity, source sheet/row when available, and recommendation. |
| Report impact | The issue increases report severity counts. Material unresolved findings can affect delivery readiness because delivery checks consume prior issues and may block first/final delivery. |

Condensed chain:

`Lead.SAD / materiality context -> K.01 difference detection -> K.02 reconciliation or adjustment impact context -> QcIssue -> delivery blockage or WARN/NEED_REVIEW escalation`

### Sampling Insufficiency Chain

| Step | Causal Propagation |
| --- | --- |
| Data condition | K.02 addition/disposal sample output, selected samples, detailed test rows, or execution path data is missing, incomplete, or inconsistent. |
| Rule trigger | Addition and disposal runners compare sample output with detailed test sheets and inspect whether sampling checks should run or be skipped based on waiver path. |
| Evaluation result | Missing or unmatched sample evidence leads to sample matching findings, package-completeness findings, or NEED_REVIEW when the system cannot verify the testing state. |
| `QcIssue` | The finding is emitted as a K.02-related issue with severity based on whether the problem is a hard inconsistency or an incomplete/ambiguous testing record. |
| Report impact | The report flags K.02 work as incomplete or needing review. Addition findings also appear in `addition_sheet_section`; disposal findings flow through the main issue list and procedure/by-rule grouping. |

Condensed chain:

`K.02 sample output missing/incomplete -> sample matching or package check triggered -> FAIL/NEED_REVIEW -> QcIssue -> report section or issue list marked incomplete`

### Data Inconsistency Chain

| Step | Causal Propagation |
| --- | --- |
| Data condition | FA list totals, asset records, rollforward movement rows, or reconciliation checks disagree with each other. |
| Rule trigger | FA list rules check asset-level field integrity; rollforward rules check movement totals and reconciliations; K.03 receives FA list and rollforward context for depreciation review. |
| Evaluation result | A direct contradiction produces deterministic FAIL. If the contradiction depends on missing sheets, weak mapping, or unclear source references, the result can become NEED_REVIEW. |
| `QcIssue` | The inconsistency is captured at asset, sheet, or workbook level depending on whether an asset id and source row are available. |
| Report impact | The report aggregates the inconsistency under the rule/procedure. Related K.01 or K.03 findings can raise the overall report severity and create follow-up review focus. |

Condensed chain:

`FA list mismatch or rollforward inconsistency -> reconciliation check failure -> K.01/K.03 secondary review context -> QcIssue -> severity escalation in report`

### LLM-Assisted Review Chain

| Step | Causal Propagation |
| --- | --- |
| Data condition | Deterministic rules detect WARN, ambiguity, material difference with notes, waiver reason, weak narrative, or ingest instability. |
| Rule trigger | When LLM is enabled, the pipeline invokes the relevant semantic review helper for Summary, Lead, K.02 Addition, K.02 Disposal, K.01 notes, or ingest review. |
| Evaluation result | LLM returns semantic sufficiency observations, contextual explanations, or reading-layer concerns. It does not recalculate amounts or change deterministic rule conclusions. |
| `QcIssue` | Business semantic findings are converted into `QcIssue` with `review_source` and `llm_review_type`. Ingest review results are stored separately in `ingest_review_section`. |
| Report impact | LLM findings or annotations enrich report review focus. Deterministic FAIL findings remain FAIL; LLM can add context but not erase them. |

Condensed chain:

`deterministic WARN or ambiguity -> LLM semantic review -> contextual issue/enrichment -> report annotation or issue -> no override of deterministic FAIL`


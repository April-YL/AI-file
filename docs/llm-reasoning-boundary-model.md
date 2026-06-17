# LLM Reasoning Boundary Model

This document defines the current LLM reasoning boundary in the QC system. It
does not change prompts, code, pipeline order, rules, or runtime behavior.

Classification labels in this document mean:

| Label | Meaning |
| --- | --- |
| NECESSARY | Required in an automated system context to handle semantic ambiguity, explanation quality, or incomplete structured information. This does not mean irreplaceable by humans. |
| OPTIONAL | The rule engine can handle core decision logic, but LLM improves semantic quality, explanation, aggregation, or review usability. |
| REDUNDANT | Deterministic rules fully cover the decision logic; LLM should not affect outcomes. |

Core principle:

`Rules = deterministic truth source. LLM = semantic reasoning assistant.`

Rules own numbers, thresholds, reconciliation, matching, required fields, and
pipeline control. LLM can explain, enrich, and flag ambiguity, but must never
override deterministic `FAIL`.

## LLM Usage Inventory

| Usage Area | Runtime Location | Current Input | Current Output | Report Surface |
| --- | --- | --- | --- | --- |
| Summary PSP waiver review | `run_workbook_qc` -> `review_waiver_reasons_batch_with_llm` -> `check_psp_completion` | Summary PSP rows, waiver reasons, workbook semantic context | `WaiverSemanticReview` consumed by PSP rule | `QcIssue` from PSP rule when reason is insufficient/unclear |
| Summary sheet semantic matching | `run_workbook_qc` -> `build_sheet_semantic_issues` | Summary sheet references, candidate workbook sheet previews | `QcIssue` with LLM source | Main issue list and comments output |
| Lead adjustment review | `run_workbook_qc` -> `run_lead_adjustment_llm_review` | Lead adjustment block, movement guidance, extracted grid, deterministic hints | LLM issues plus layout data used for strict adjustment gating | Main issue list; can affect strict Lead adjustment check gating |
| Lead expectation/fluctuation semantic review | `run_workbook_qc` -> `build_lead_semantic_issues` | Lead expectations, movement rows, fluctuation notes, workbook context | LLM-assisted `QcIssue` | Main issue list and Lead section |
| K.02 Addition semantic review | `run_workbook_qc` -> `build_addition_llm_issues` | Addition list/test/sample output/execution path plus prior rule issues | LLM-assisted `QcIssue` | Main issue list and addition section |
| K.02 Disposal semantic review | `run_workbook_qc` -> `build_disposal_llm_issues` | Disposal test/sample output/execution path/list summary plus prior rule issues | LLM-assisted `QcIssue` | Main issue list |
| Ingest semantic review | `run_workbook_qc` -> `run_workbook_ingest_reviews` | Missing-object candidates, low-confidence ingest metadata, previews | `IngestReviewResult` dictionaries | `ingest_review_section`; annotated workbook may create LLM ingest review sheet |
| K.01 Rollforward notes review | `run_workbook_qc` -> `build_rollforward_notes_issues` | Rollforward differences above SAD, topic-specific notes, prior deterministic issues | LLM-assisted `QcIssue` | Main issue list and rollforward section |
| Final report enrichment | `run_workbook_qc` -> `enrich_report_with_llm` | Finished report issues, summary rows, compact workbook payload | `LlmEnrichment` | `llm_enrichment` only |
| CSV report enrichment | `run_fa_list_qc` in `report.export_json` -> `enrich_report_with_llm` | FA list report issues | `LlmEnrichment` | `llm_enrichment` only |

## LLM Role Classification

| Usage Area | Classification | LLM Role | Reason |
| --- | --- | --- | --- |
| Summary PSP waiver review | NECESSARY | Reviewer | In an automated system, judging whether a refusal reason is specific and audit-meaningful is semantic. Rules can catch blanks or obvious weak text, but not reliably assess narrative sufficiency across contexts. |
| Summary sheet semantic matching | OPTIONAL | Fallback reviewer / noise handler | Deterministic fuzzy sheet matching already handles many cases. LLM helps when sheet names are weak but previews suggest a possible match. |
| Lead adjustment review | NECESSARY | Reviewer / noise handler | Adjustment summaries can use different layouts, sign conventions, cross-account explanations, and narrative references. Automated interpretation benefits from LLM when structured extraction is incomplete. |
| Lead expectation/fluctuation semantic review | NECESSARY | Reviewer | Sufficiency of expectation and fluctuation explanation is primarily narrative and context-based. Numeric thresholds remain rule-owned. |
| K.02 Addition semantic review | OPTIONAL | Reviewer / explainer | Core addition decisions are rule-owned: fields, rollforward tie-out, sample matching, TE/CRA, and amounts. LLM mainly checks whether workpaper text explains the rule findings. |
| K.02 Disposal semantic review | OPTIONAL | Reviewer / explainer | Core disposal decisions are rule-owned. LLM adds value for evidence description, waiver explanation, and exception follow-up narrative quality. |
| Ingest semantic review | NECESSARY | Fallback reviewer / noise handler | When deterministic ingest is low-confidence or a core sheet may be missed, LLM can review previews and recognition metadata without mutating ingest results. |
| K.01 Rollforward notes review | NECESSARY | Reviewer | The rule can detect material differences and notes presence; whether the notes adequately explain the specific difference is semantic. |
| Final report enrichment | OPTIONAL | Explainer / aggregator | It improves readability and review focus but does not alter findings, counts, or severity. |
| CSV report enrichment | OPTIONAL | Explainer / aggregator | It summarizes already-determined FA list findings. It is not part of rule decision-making. |

Current REDUNDANT target:

| Area | Classification | Reason |
| --- | --- | --- |
| Numeric recalculation, thresholds, reconciliation, sample matching, required-field checks | REDUNDANT | These are already deterministic rule responsibilities. LLM should not participate in the decision outcome. |

## Replaceability Matrix

| Usage Area | Deterministic Replacement | Information Lost If LLM Removed | Actual LLM Role |
| --- | --- | --- | --- |
| Summary PSP waiver review | Keyword/length rules, required reason templates, threshold-token checks, contradiction checks against K.01/K.02 data | Nuanced reading of whether the reason is audit-specific, supported, and not merely boilerplate | Reviewer |
| Summary sheet semantic matching | Fuzzy sheet-name matching, workbook structure classifier, sheet title aliases, preview keyword scoring | Ability to compare weak sheet names with short content previews in ambiguous cases | Fallback decision maker for `NEED_REVIEW`, not final PASS authority |
| Lead adjustment review | More layout parsers, debit/credit column detection, sign convention rules, direct PPE account mapping tables | Judgment over irregular adjustment summaries, cross-account explanation quality, and unclear sign conventions | Reviewer / noise handler |
| Lead expectation/fluctuation semantic review | Required-text templates, movement direction consistency checks, note-presence rules, simple contradiction detection | Narrative sufficiency: whether explanation gives a business reason and responds to the observed movement | Reviewer |
| K.02 Addition semantic review | Check waiver fields, require sample basis text, require exception conclusion text, compare deterministic issue references to note fields | Quality of cross-sheet explanation and whether text meaningfully responds to rule findings | Reviewer / explainer |
| K.02 Disposal semantic review | Check waiver fields, require evidence description fields, require exception follow-up text, enforce execution-path completeness | Quality of disposal evidence narrative and other-reduction treatment explanation | Reviewer / explainer |
| Ingest semantic review | Better sheet classifier, stronger anchors, explicit low-confidence checks, missing-object rules | Human-like inspection of previews when labels, sections, or field mappings are noisy | Fallback reviewer / noise handler |
| K.01 Rollforward notes review | Topic-specific required note fields and keywords for cause/process/conclusion/further procedure | Whether the note actually addresses the material difference rather than merely existing | Reviewer |
| Final report enrichment | Static report templates, deterministic grouping, severity-based summary text | More readable executive summary and consolidated review focus | Explainer / aggregator |
| CSV report enrichment | Static summary template by rule/severity | Better narrative summary of already-known findings | Explainer / aggregator |

Replaceability conclusion:

- LLM is most justified where the input is narrative, semi-structured, or ambiguous.
- LLM is least justified where the input is numeric, tabular, threshold-based, or exact-match.
- If LLM is removed, the system still runs deterministic QC, but loses semantic sufficiency review and some ingest ambiguity surfacing.

## LLM Decision Boundary Model

### LLM Is Not Allowed To

| Prohibited Action | Boundary |
| --- | --- |
| Override `FAIL -> PASS` | A deterministic `FAIL` remains `FAIL` unless the underlying rule or data changes. |
| Perform numeric recalculation | LLM cannot be the authority for totals, differences, depreciation, sample amounts, TE/CRA/SAD comparisons, or tolerances. |
| Replace the rule engine | LLM cannot decide whether deterministic rules should run, be skipped, or be reordered. |
| Mutate `WorkbookQcContext` | Ingest review may flag a suspected missed sheet or wrong mapping, but it does not rewrite parsed datasets during `run_workbook_qc`. |
| Treat external evidence as verified | LLM can review descriptions of evidence but cannot authenticate invoices, contracts, approvals, or external systems. |
| Invent missing data | If input evidence is insufficient, LLM must return ambiguity or review focus rather than filling facts. |

### LLM Is Allowed To

| Allowed Action | Boundary |
| --- | --- |
| Explain findings | Add rationale, suggested action, or executive summary to already-produced findings. |
| Enrich context | Use compact workbook context and prior issues to make semantic comments more useful. |
| Flag ambiguity | Produce WARN or NEED_REVIEW when narrative sufficiency, sheet matching, or ingest stability is unclear. |
| Assist NEED_REVIEW cases | Help the reviewer understand why a manual check is needed and where to look. |
| Add semantic `QcIssue` | Only for review topics where the problem is narrative sufficiency, ambiguity, or explanation quality. |
| Add ingest review prompts | Surface possible missed or unstable ingest results in `ingest_review_section` without changing business findings. |

Authority model:

`Rules decide facts. LLM explains and challenges ambiguity. Humans resolve audit judgment.`

## Minimal LLM Architecture Proposal

This is a boundary proposal only. It does not require immediate code changes.

### Keep LLM

| Area | Recommended Boundary |
| --- | --- |
| Summary PSP waiver review | Keep as semantic sufficiency review for refusal reasons. Rules should still own blank/required-status checks. |
| Lead expectation/fluctuation review | Keep for narrative sufficiency and contradiction explanation. Rules should own threshold and movement calculations. |
| Lead adjustment review | Keep for irregular layout, sign convention ambiguity, and cross-account narrative review. Deterministic checks should own direct amount comparisons when layout is reliable. |
| K.01 Rollforward notes review | Keep for notes sufficiency only when deterministic rules already detect material differences and notes exist. |
| Ingest semantic review | Keep as reading-layer fallback for low-confidence or missing-object situations. It should remain separate from business findings. |

### Downgrade To Explanation / Logging Only

| Area | Recommended Boundary |
| --- | --- |
| Final report enrichment | Keep optional, but treat as report narrative only. It should not add or remove findings. |
| CSV report enrichment | Keep optional and narrative-only. |
| Summary sheet semantic matching | Prefer deterministic sheet matching first; LLM should only produce `NEED_REVIEW` style prompts for ambiguous cases. |

### Candidate For Rule Expansion Before LLM Reliance

| Area | Recommended Boundary |
| --- | --- |
| K.02 Addition semantic review | Use deterministic rules for required explanation fields, sampling package completeness, amount tie-out, and sample matching. Keep LLM for cross-sheet explanation quality only. |
| K.02 Disposal semantic review | Use deterministic rules for list/test/sample completeness and reconciliation. Keep LLM for evidence description and exception follow-up quality only. |

### Remove From Decision Surface

| Area | Recommended Boundary |
| --- | --- |
| Any numeric comparison | Must stay deterministic. LLM may quote deterministic findings but should not create the numeric conclusion. |
| Any PASS recovery from semantic review | LLM may say a narrative appears sufficient, but that should not erase existing deterministic findings. |

## Conflict Resolution Policy

### Rule Priority

| Conflict | System Winner | Handling |
| --- | --- | --- |
| Rule says `FAIL`, LLM says sufficient | Rule wins | Keep `FAIL`. LLM output may be ignored or recorded only as context if useful. |
| Rule says `WARN`, LLM says sufficient | Rule wins for severity | Keep `WARN` unless the deterministic rule itself is changed. |
| Rule says `NEED_REVIEW`, LLM says sufficient | Human/reviewer wins after review | LLM can reduce reviewer effort by explaining why it appears sufficient, but cannot automatically mark PASS. |
| Rule has no issue, LLM says insufficient | LLM may add semantic `WARN` or `NEED_REVIEW` only within an allowed semantic topic | This is additive, not an override. |
| LLM flags ingest suspicious but rules ran | Ingest review stays separate | The finding belongs in `ingest_review_section`; it should not retroactively change rule outcomes. |
| LLM fails or returns invalid JSON | Rules continue | Deterministic report remains valid without LLM output. |

### Severity Boundary

| LLM Output Type | Allowed Severity Effect |
| --- | --- |
| Semantic insufficiency | May add `WARN` or `NEED_REVIEW` where the LLM helper already maps it into `QcIssue`. |
| Semantic uncertainty | May add `NEED_REVIEW`. |
| Semantic sufficiency | Does not create PASS and does not remove existing issues. |
| Report enrichment | No severity effect. |
| Ingest review | No direct business severity effect; separate reading-layer review prompt. |

### Practical Rule

If a conclusion depends on a number, threshold, reconciliation, sample match, or
required structured field, the rule engine is authoritative.

If a conclusion depends on whether a written explanation is meaningful,
specific, and responsive to the audit issue, LLM can assist but the result is
still review-oriented rather than final audit judgment.

## LLM Failure Mode Model

This section defines how LLM can fail in this QC system and how those failures
are controlled.

### Over-Interpretation Failure

Definition:

LLM incorrectly upgrades weak or ambiguous evidence into a PASS-level
conclusion.

Examples:

- Weak narrative treated as sufficient explanation.
- Missing justification inferred as acceptable reasoning.
- A generic phrase such as "not material" treated as enough without workbook
  support.

Control:

- LLM outputs are non-authoritative for PASS/FAIL.
- Deterministic rule outcomes always override LLM interpretation.
- Semantic sufficiency from LLM does not create a PASS issue and does not remove
  existing findings.

### Judgment Drift Failure

Definition:

LLM deviates from deterministic rule severity.

Examples:

- A deterministic FAIL is described as WARN-like or PASS-like.
- NEED_REVIEW is softened into a conclusion that implies no further work is
  needed.
- A material reconciliation issue is reframed as only a documentation issue.

Control:

- Severity for deterministic facts is rule-owned only.
- LLM cannot modify existing deterministic `QcIssue.severity`.
- LLM-assisted `QcIssue` severity is additive and must remain review-oriented.
- Any narrative generated by LLM must preserve the existing deterministic
  severity context.

### Hallucinated Justification Failure

Definition:

LLM generates plausible but unsupported reasoning.

Examples:

- "This is typically acceptable."
- "Industry standard suggests..."
- Assuming an invoice, contract, approval, or external system check exists when
  it was not provided in the workbook context.

Control:

- LLM must only reference provided workbook context, prior findings, previews,
  and structured excerpts.
- No external assumptions are allowed in decision impact.
- Unsupported reasoning must be treated as ambiguity or manual review focus, not
  as evidence.

### Missing Data Completion Failure

Definition:

LLM fills missing data gaps with inferred values.

Examples:

- Missing ingest field assumed to be correctly mapped.
- Missing reconciliation assumed to be consistent.
- Missing SAD/TE/CRA value inferred from nearby text or generic audit practice.

Control:

- LLM must return uncertainty or review focus when data is insufficient.
- No data fabrication is allowed.
- Missing deterministic inputs remain missing until ingest or the underlying
  workbook data changes.
- Rules continue to own missing-field and unreadable-data consequences.

### Boundary Enforcement Principle

- Rules are the authoritative truth source.
- LLM is an interpretation assistant only.
- Any contradiction between rules and LLM is resolved in favor of rules.
- LLM can add context, but cannot erase, downgrade, or reverse deterministic
  findings.

## LLM Impact Propagation Model

This section defines how LLM outputs propagate into system artifacts after they
are produced. Impact level describes system propagation, not decision authority.
Higher impact does not mean higher audit authority.

### Impact Levels

| Level | Meaning | Decision Authority |
| --- | --- | --- |
| LEVEL 0 | No structural impact. LLM output is attached as enrichment or logging only. | No authority over rule outcomes. |
| LEVEL 1 | Additive impact. LLM output can add `QcIssue` or annotation, but cannot change existing deterministic issues. | Additive review signal only. |
| LEVEL 2 | Attention routing impact. LLM output changes what reviewers are asked to inspect, especially ingest risk areas. | Review prioritization only, not business decision authority. |

### LLM Output -> System Impact Mapping

| Usage Area | LLM Output Type | Downstream Consumption | Impact Level | System Impact |
| --- | --- | --- | --- | --- |
| Summary PSP waiver review | `WaiverSemanticReview` with adequacy, rationale, and suggested action | Passed into `check_psp_completion`; PSP rule decides whether to create a finding | LEVEL 1 | Can contribute to PSP `QcIssue` creation when waiver reason is insufficient or unclear. Does not override deterministic PSP checks. |
| Summary sheet semantic matching | LLM-assisted sheet match assessment | Converted directly into `QcIssue` by `build_sheet_semantic_issues` | LEVEL 1 | Adds `NEED_REVIEW` for ambiguous sheet reference support. Routes reviewer to candidate sheet evidence. |
| Lead adjustment review | Layout assessment, extracted rows, semantic assessment, optional LLM issues | LLM issues join Lead issues; layout result can gate strict deterministic adjustment total check | LEVEL 1 | Adds Lead review findings and can prevent overconfident strict comparison when layout is unreliable. It does not create numeric authority. |
| Lead expectation/fluctuation semantic review | Semantic sufficiency assessment | Converted into LLM-assisted `QcIssue` | LEVEL 1 | Adds WARN/NEED_REVIEW for weak expectation or fluctuation explanations. |
| K.02 Addition semantic review | Topic-level sufficiency assessment | Converted into `addition_semantic_review` issues | LEVEL 1 | Adds semantic findings to main issue list and addition section. Prior deterministic issues remain unchanged. |
| K.02 Disposal semantic review | Topic-level sufficiency assessment | Converted into `disposal_semantic_review` issues | LEVEL 1 | Adds semantic findings to main issue list. Prior deterministic issues remain unchanged. |
| K.01 Rollforward notes review | Topic-level notes sufficiency assessment | Converted into `rollforward_notes_semantic` issues | LEVEL 1 | Adds WARN/NEED_REVIEW when notes do not sufficiently explain material differences already detected by rules. |
| Ingest semantic review | `IngestReviewResult` with risk area, candidate sheet, rows, rationale, manual focus | Stored in `ingest_review_section`; annotated workbook can surface an LLM ingest review sheet | LEVEL 2 | Routes reviewer attention to suspected missing/unstable ingest areas. Does not change parsed datasets or business findings. |
| Final report enrichment | `LlmEnrichment` summary, notes, lead focus | Attached to `report.llm_enrichment` | LEVEL 0 | Improves report narrative and focus notes only. No `QcIssue` creation or severity effect. |
| CSV report enrichment | `LlmEnrichment` summary and notes | Attached to CSV-origin report | LEVEL 0 | Narrative-only enrichment of already-created FA list findings. |

### Strict Non-Impact Rules

LLM outputs must not:

- Change deterministic rule results.
- Override deterministic `FAIL`, `WARN`, or `NEED_REVIEW`.
- Modify numeric, threshold, reconciliation, sample matching, or required-field
  outcomes.
- Mutate `WorkbookQcContext`, parsed datasets, source workbook data, or rule
  execution order.
- Remove existing `QcIssue` objects from the report.
- Recalculate severity counts except through additive LLM-assisted issues that
  are explicitly created as review findings.

### Propagation Flow Model

The current propagation flow is:

`LLM Output -> Interpretation Layer -> QcIssue / Annotation Layer -> Report Layer -> Reviewer Attention Layer`

| Layer | Meaning |
| --- | --- |
| LLM Output | Raw JSON-like review result, enrichment, or ingest review response returned by an LLM helper. |
| Interpretation Layer | Helper functions validate the output, discard invalid responses, and map allowed assessments to review-oriented findings or sections. |
| `QcIssue` / Annotation Layer | Business semantic findings become additive `QcIssue` objects; ingest review becomes a separate review section; final enrichment stays attached to the report only. |
| Report Layer | `build_report` aggregates deterministic and additive issue objects. Separate sections such as `ingest_review_section` and `llm_enrichment` preserve non-decision outputs. |
| Reviewer Attention Layer | Reports and annotated workbooks direct reviewers to weak narratives, ambiguous mappings, missing evidence, or suspected ingest risks. |

### Separation Principle

| Layer | Owner | Responsibility |
| --- | --- | --- |
| Decision layer | Rules | Numeric truth, thresholds, reconciliations, sample matching, required fields, and deterministic severity. |
| Cognitive layer | LLM | Semantic sufficiency, ambiguity identification, explanation, weak narrative detection, and ingest risk surfacing. |
| Presentation layer | Report | Aggregation, issue display, annotated workbook comments, ingest review sheets, and final narrative enrichment. |

The LLM can affect presentation and reviewer attention. It can add bounded
semantic review findings where the code explicitly converts LLM output into
`QcIssue`. It cannot alter deterministic audit decisions.

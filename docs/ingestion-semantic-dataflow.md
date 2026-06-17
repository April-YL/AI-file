# Ingestion Semantic Dataflow

结论：本系统的 ingest 不是单纯“读取 Excel/CSV”，而是把底稿转换为可供规则和 LLM 使用的审计语义模型。它本身不直接产出 `PASS/WARN/FAIL/NEED_REVIEW`，但会决定哪些规则能执行、哪些规则应跳过、哪些事项只能进入 `NEED_REVIEW`。

## Scope

本文只还原当前代码中的 ingest 语义数据流，不提出新架构，不修改 pipeline，不新增组件。

核心对象：

- `WorkbookIngestContext`: ingest 层的整本底稿结构化结果。
- `WorkbookQcContext`: rules 和 LLM 共同消费的质检上下文。
- `QcReport`: report 层构建的最终内存报告对象。

主数据流：

```text
Workbook / CSV
-> workbook_reader / records loader
-> sheet_classifier / workbook_structure
-> per-sheet parser
-> semantic entity extraction
-> WorkbookIngestContext
-> WorkbookQcContext
-> run_workbook_qc()
-> QcIssue + report sections
-> build_report()
-> QcReport
```

CSV 分支：

```text
CSV
-> load_fa_list_csv()
-> FaListDataset
-> run_fa_list_qc()
-> QcReport
```

## Sheet-Level Semantic Mapping

Summary sheet -> Input source + validation context -> Parsed as `SummarySheetDataset`. It represents program execution status, sheet references, PSP flags, waiver reasons, and notes. It feeds PSP completion checks, K.02 package completeness, addition/disposal execution path inference, LLM waiver review, and report summary sections.

K.00 Lead sheet -> Input source + validation context + decision-support context -> Parsed as `LeadSheetDataset`. It carries TE/SAD/PM, CRA/TT, expectation rows, movement rows, volatility thresholds, Check with A3, fluctuation notes, and adjustment rows. It is reused by Lead rules, K.01 SAD checks, K.02 sampling parameter checks, K.03 TOD checks, LLM semantic review, and manual review sections.

K.01 Rollforward sheet -> Input source + derived computation + validation context -> Parsed as `RollforwardSheetDataset`. It contains amount column bindings, opening/ending totals, movement transactions, K.01 six-section recognition, table3/table4 checks, TB differences, and Notes. It feeds K.01 rules, addition/disposal reconciliation, K.03 TOD comparison, Summary/Lead LLM context, and report rollforward section.

FA list sheet -> Input source -> Parsed as `FaListDataset` with `AssetRecord` rows. It represents the main asset population. It feeds FA list field rules, K.01 reconciliation fallback, K.03 policy/TOD context, and workbook-level reconciliations.

K.02.1 Addition list -> Input source -> Parsed as a `FaListDataset` with addition semantics. It represents the addition population. It feeds required-field rules, population homogeneity, addition vs K.01 purchase reconciliation, LLM addition review, and addition execution path.

K.02.1 Addition test sheet -> Input source + validation context -> Parsed as `AdditionTestSheetDataset`. It represents detailed test execution, waiver note text, tested samples, module assessments, and amount anchors. It feeds sample match, replacement reason checks, semantic LLM review, and package completeness.

K.02.1a Addition sample output sheet -> Input source + validation context -> Parsed as `AdditionSampleOutputDataset`. It represents selected samples, sampling parameters, amount anchors, and module assessments. It feeds sample match, sample pool amount checks, TE/CRA/assertion scope checks, and LLM addition review.

K.02.2 Disposal list -> Input source + derived computation -> Parsed as `FaListDataset`, then summarized as `DisposalListSummary`. It represents disposal population and sale/scrap/other/unknown buckets. It feeds disposal list rules, disposal reconciliation, K.02.2 matrix checks, and LLM disposal review.

K.02.2 Disposal test sheet -> Input source + validation context -> Parsed as `DisposalTestSheetDataset`. It represents detailed disposal testing, waiver notes, reconciliation matrix, tested samples, amount anchors, and module assessments. It feeds disposal reconciliation rules, detailed test rules, sample match, and LLM disposal review.

K.02.2a Disposal sample output sheet -> Input source + validation context -> Parsed as `DisposalSampleOutputDataset`. It represents selected disposal samples, parameters, amounts, and module assessments. It feeds disposal sampling rules, sample match, and LLM disposal review.

K.03 depreciation TOD / SAP / policy sheets -> Input source + validation context -> Parsed as `K03SheetDataset`. It represents depreciation test branch, execution path, detail table, by-item rows, policy rows, template type, unsupported/later-phase flags, and LLM candidate context. It feeds K.03 TOD-by-item rules, K.03 policy review, and report issue localization.

Report artifacts -> Reporting artifact only -> JSON, HTML, and annotated workbook are generated after `QcReport`. They are not ingest sources and do not feed QC decisions.

## Row-Level Semantic Mapping

`AssetRecord` -> Asset entity -> Used for FA list, addition list, disposal list, and rollforward detail-like records. A row represents one asset or one asset-like population item with asset id/name/category/date/useful-life/value fields.

`PspProgramRow` -> Program execution entity -> A Summary row represents one audit program line, with procedure name, sheet reference, execution status, waiver reason, notes, and PSP flag.

`LeadBasicInfoField` / `MaterialityCapture` -> Threshold/context entity -> A row captures project-level values such as client name, period end, PM, TE, SAD, GAAP, and currency.

`CraAssertionRow` -> Assertion risk entity -> A row represents one assertion-level CRA/TT relationship, reused for Lead rules and sampling parameter checks.

`ExpectationRow` -> Expected movement analysis entity -> A row represents management/auditor expectation for an account change.

`LeadMovementRow` -> Account movement entity -> A row represents one account line such as original value, accumulated depreciation, impairment, or net value, including sheet ref and movement values.

`LeadCheckWithA3` / `CheckWithA3AccountLine` -> Cross-check entity -> Represents Lead check/diff/notes alignment with A3-like external reference values.

`AdjustmentSummaryRow` -> Adjustment entity -> A row represents a potential audit adjustment or adjustment-summary text, later filtered and reviewed by rules/LLM.

`MovementTransactionAmount` -> Rollforward transaction entity -> A row represents a transaction amount in K.01, such as purchase, disposal, or depreciation by measure.

`K01SectionRegion` -> Workpaper section entity -> A region represents one of the K.01 standard blocks, with anchor/start/end rows and evidence.

`AdditionSampleRow` / `AdditionTestedSampleRow` -> Addition sample entity -> Rows represent selected samples and tested samples, used for matching and testing coverage.

`DisposalSampleRow` / `DisposalTestedSampleRow` -> Disposal sample entity -> Rows represent selected and tested disposal samples, including sale/disposal amounts and supporting evidence fields.

`DisposalReconciliationRow` / `DisposalReconciliationCell` -> Disposal reconciliation entity -> Rows and cells represent K.02.2 matrix amounts, formulas, measure columns, and investigation flags.

`K03DetailRow` -> Depreciation test item entity -> A row represents an asset-level depreciation test line with raw values, normalized values, and cell references.

`K03PolicyRow` -> Depreciation policy entity -> A row represents category-level depreciation policy comparison, including current/prior method, useful life, salvage rate, annual rate, markers, and explanations.

`ReconciliationCheck` -> Cross-sheet reconciliation entity -> Represents computed relationships between populations and K.01 amounts, used as decision support by rollforward and report logic.

## Field-Level Influence Mapping

### Fields influencing K.03 checks

`asset_id`, `asset_name` -> CRITICAL -> Identify and match K.03 by-item rows against asset-level evidence and report localization.

`original_value`, `accumulated_depreciation`, `impairment_provision`, `net_value` -> CRITICAL -> Drive amount comparisons and abnormal difference checks in K.03 and cross-sheet context.

`start_date`, `depreciation_start_date`, `disposal_date` -> SECONDARY -> Support date-related depreciation context and possible later-phase checks.

`useful_life_months`, `salvage_rate`, depreciation method/policy fields -> CRITICAL -> Drive K.03 TOD and policy review logic.

`depreciation_difference`, `current_depreciation`, `management_depreciation`, `audit_recalculated_depreciation` -> CRITICAL -> Drive K.03 recalculation/difference checks.

Lead `sad`, `te`, CRA/TT -> SECONDARY -> K.03 uses Lead as threshold/context, especially for materiality-related review and semantic framing.

K.03 `template_type`, `execution_path`, `ingest_depth`, `rule_status`, `unsupported_or_later_phase` -> CRITICAL -> Determine whether the K.03 sheet is rule-ready, later-phase only, or policy/TOD branch.

Unmapped decorative text, instruction-only areas, blank rows -> IGNORED -> Preserved for context only if captured, but not core rule inputs.

### Fields influencing rollforward logic

`amount_column_bindings` -> CRITICAL -> Define amount measure and period role. Column binding errors directly affect opening/movement/ending logic.

`opening_totals`, `ending_totals`, `table1_check_values` -> CRITICAL -> Feed K.01 completeness and amount consistency checks.

`movement_transactions` with `transaction_key`, `measure`, `amount`, `source_row` -> CRITICAL -> Feed addition purchase reconciliation, disposal reconciliation, and movement-specific checks.

`section_presence`, `section_regions`, `section_conflicts`, `recognition_confidence` -> CRITICAL -> Determine whether K.01 blocks exist and whether rules should run or become `NEED_REVIEW`.

`table3_check_values`, `table3_notes_text_present`, `table3_notes_text` -> CRITICAL -> Drive FA list vs rollforward check and over-SAD Notes logic.

`tb_reconciliation_detected`, `tb_difference_values`, `tb_difference_details`, `tb_notes_text_present`, `tb_notes_text` -> CRITICAL -> Drive GL/TB difference over SAD checks and LLM notes review.

`table4_pl_amounts`, `table4_difference`, `table4_notes_text_present`, `table4_notes_text` -> CRITICAL -> Drive depreciation expense vs P/L/TB reconciliation.

Lead `sad` -> CRITICAL -> Used repeatedly to decide whether differences exceed SAD in K.01 and K.02 reconciliation logic.

Rollforward `notes` and section evidence -> SECONDARY -> Used for diagnostics, report sections, and LLM context.

### Fields influencing LLM evaluation

Summary `waiver_reason`, `execution_status`, `procedure_name`, `sheet_ref`, `notes` -> CRITICAL -> Feed PSP waiver semantic review and sheet semantic matching.

Lead `materiality`, `cra_rows`, `expectations`, `movement_rows`, `fluctuation_notes`, `adjustment_rows`, `notes` -> CRITICAL -> Feed Lead semantic review, adjustment review, and workbook context.

Rollforward `tb_difference_values`, `table3_check_values`, `table4_difference`, notes text, section conflicts -> CRITICAL -> Feed K.01 Notes semantic review and ingest review.

Addition/disposal execution path fields -> CRITICAL -> Tell LLM whether a test was performed, waived in Summary, or waived on the test sheet.

Addition/disposal sample/test rows and module assessments -> SECONDARY -> Feed semantic sufficiency review and cross-sheet explanation checks.

Workbook sheet titles and candidate previews -> SECONDARY -> Feed LLM ingest review and sheet semantic matching.

Full FA/addition/disposal list records beyond configured sample limits -> IGNORED by LLM -> Rules may use full records, but LLM payload uses excerpts and truncation.

### Fields influencing delivery validation

Prior `QcIssue` list -> CRITICAL -> Delivery checks use existing findings to judge first/final delivery completeness.

`WorkbookQcContext` and workbook sheet titles -> SECONDARY -> Provide supporting context for delivery completeness checks.

`delivery_context.stage` -> CRITICAL -> Selects first-delivery or final-delivery validation behavior.

Runtime timings, UI cache version, output file names -> IGNORED -> Useful for operation or display, not delivery quality decisions.

## Ingestion Role Clarification

Ingestion is not pure preprocessing.

Current role -> Semantic enrichment layer + QC decision-support layer.

Why it is more than preprocessing:

- It classifies sheets into audit procedure semantics.
- It selects candidate sheets and suppresses non-selected candidates from the main context.
- It maps raw headers into standard fields such as `asset_id`, `original_value`, `net_value`, `te`, `sad`, `cra`, and `tt`.
- It filters non-asset rows, blank rows, subtotal/total rows, and non-detail lines.
- It extracts procedure execution paths for K.02 addition/disposal.
- It identifies K.01 sections, notes regions, check rows, differences, and movement transactions.
- It summarizes disposal list methods into sale/scrap/other/unknown buckets.
- It builds workbook-level reconciliations.
- It sets confidence, `usable_for_rules`, `recognition_confidence`, `missing_components`, and warnings that directly influence rule behavior.

Why it is not the final QC decision layer:

- It generally does not create `QcIssue`.
- It does not assign final `PASS/WARN/FAIL/NEED_REVIEW` conclusions.
- It feeds `rules` and LLM review, where final findings are produced.

Practical interpretation:

```text
ingest = semantic model builder
rules = deterministic QC decision layer
LLM = semantic review assistant
report = finding aggregation and delivery layer
```

## Dataflow Graph Construction

### Excel workbook path

```text
Workbook
-> read_worksheet_rows()
-> classify_sheet()
-> analyze_workbook_structure()
-> choose candidate sheets by SheetKind
-> per-sheet parsers:
   - load_summary_from_workbook()
   - load_lead_from_workbook()
   - load_rollforward_from_workbook()
   - load_fa_list_from_workbook()
   - load_asset_sheet_from_workbook(addition/disposal)
   - load_addition_test_from_workbook()
   - load_addition_sample_output_from_workbook()
   - load_disposal_test_from_workbook()
   - load_disposal_sample_output_from_workbook()
   - load_k03_sheets_from_workbook()
-> derived semantic objects:
   - DisposalListSummary
   - ReconciliationCheck list
   - AdditionExecutionPathDataset
   - DisposalExecutionPathDataset
-> WorkbookIngestContext
-> WorkbookQcContext
-> run_workbook_qc()
-> QcIssue list + summary/lead/rollforward/addition/ingest-review sections
-> build_report()
-> QcReport
```

### CSV path

```text
CSV
-> load_fa_list_csv()
-> parse_fa_list_rows()
-> FaListDataset
-> run_fa_list_qc()
-> FA list rules
-> build_report()
-> QcReport
```

### Semantic dependency graph

```text
Summary
-> PSP checks
-> addition/disposal execution path
-> package completeness
-> LLM waiver review

Lead
-> Lead rules
-> K.01 SAD/Notes checks
-> K.02 TE/CRA/assertion checks
-> K.03 threshold/context checks
-> LLM semantic context
-> manual review sections

K.01 Rollforward
-> K.01 rules
-> addition purchase reconciliation
-> disposal reconciliation
-> K.03 context
-> LLM rollforward notes review

FA list
-> FA list rules
-> K.01 fallback reconciliation
-> K.03 policy/TOD context
-> workbook reconciliations

K.02 Addition objects
-> addition rules
-> sample match
-> sampling checks
-> addition semantic LLM review

K.02 Disposal objects
-> disposal rules
-> reconciliation matrix checks
-> sample match
-> disposal semantic LLM review

K.03 objects
-> K.03 TOD rules
-> K.03 policy review
-> report issue localization
```

## Boundary Notes

- Full population tables (`fa_list`, `addition_list`, `disposal_list`, K.03 sheets) may be loaded without truncation for rule use.
- LLM payloads use excerpts, previews, and truncation; LLM does not receive every row of large populations by default.
- Report sections are summaries of semantic objects and findings; they are not a replacement for the original workbook.
- Ingest failures and low confidence do not always stop execution; they often create skipped checks, fallback behavior, or `NEED_REVIEW` findings downstream.

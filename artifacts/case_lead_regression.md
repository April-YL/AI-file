# 案例库 Lead 质检回归表

- 生成时间（UTC）：2026-07-11T18:11:04Z
- 案例库：`E:\AI file\固定资产质检agent\案例库`
- 跳过策略：>20.0MB 或文件名含 A公司/A有限公司

## 汇总

| 标签 | 文件 | 状态 | Lead 表 | layout | CRA | Mov | Exp | 整体 | issues | FAIL 规则 | 耗时(s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- | ---: |
| B | K1 SWP 固定资产 20251231 B医疗公司.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **FAIL** | 7 | lead_check_with_a3_row, lead_fluctuation_notes_refs, lead_rollforward_tb_reconciliation | 4.76 |
| G | K1 SWP 固定资产 20251231 G科技.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **FAIL** | 4 | lead_fluctuation_notes_refs | 8.41 |
| K1 固定资产 2025 | K1 固定资产 20251231 H调温器有限公司.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **FAIL** | 3 | lead_analysis_date_after_period_end | 12.09 |
| K1 固定资产 2025 | K1 固定资产 20251231 J有限公司 - 副本.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **NEED_REVIEW** | 2 | — | 17.26 |
| K1 固定资产 2025 | K1 固定资产 20251231 J有限公司.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **FAIL** | 5 | lead_movement_notes_required, lead_fluctuation_notes_refs | 16.06 |

## 跳过

- `~$K1 固定资产 20251231 J有限公司.xlsx` (0.0 MB) — excel_lock_file

## 规则维度（overall_severity）

| 标签 | lead_required_fields | lead_analysis_date_after_period_end | materiality_consistency | risk_threshold_consistency | lead_tt_overall_min | lead_tt_gam_range | lead_expectation_analysis | lead_expectation_basis_present | lead_expectation_vs_movement_review | lead_volatility_threshold_link | lead_movement_rows_complete | lead_movement_consistency | lead_movement_notes_required | lead_check_with_a3_row | unexpected_movement_investigation | lead_fluctuation_notes_refs | lead_adjustment_internal_consistency | lead_rollforward_tb_reconciliation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B | PASS | PASS | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | NEED_REVIEW | PASS | PASS | PASS | PASS | PASS | FAIL | PASS | FAIL | PASS | FAIL |
| G | PASS | PASS | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | PASS | PASS |
| K1 固定资产 2025 | PASS | FAIL | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| K1 固定资产 2025 | PASS | PASS | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| K1 固定资产 2025 | PASS | PASS | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | NEED_REVIEW | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | FAIL | PASS | PASS |

## Ingest 基线（手工回归参考）

| 案例 | cra | mov | exp | layout 备注 |
| --- | ---: | ---: | ---: | --- |
| B–G（标准 SWP） | 5 | 4 | 7 | `layout_variant=None` |
| A（跳过） | 0 | — | — | `no_cra_te_volatility`（大文件未跑） |

复跑：`python scripts/run_case_lead_regression.py`

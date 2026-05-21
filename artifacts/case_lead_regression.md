# 案例库 Lead 质检回归表

- 生成时间（UTC）：2026-05-21T11:32:14Z
- 案例库：`D:\AI file\固定资产质检agent\案例库`
- 跳过策略：>20.0MB 或文件名含 A公司/A有限公司

## 汇总

| 标签 | 文件 | 状态 | Lead 表 | layout | CRA | Mov | Exp | 整体 | issues | FAIL 规则 | 耗时(s) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- | ---: |
| B | K1 SWP 固定资产 20251231 B医疗公司.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **FAIL** | 18 | lead_required_fields, lead_analysis_date_after_period_end, lead_check_with_a3_row | 17.6 |
| C | K1 SWP 固定资产 20251231 C新材料有限公司.xlsx | ok | K.00 Lead Sheet-24 | — | 5 | 4 | 7 | **FAIL** | 8 | lead_required_fields | 31.96 |
| D | K1 SWP 固定资产 20251231 D锂电科技有限公司.xlsx | ok | K.00 Lead Sheet-24 | — | 5 | 4 | 7 | **FAIL** | 10 | lead_required_fields, lead_rollforward_tb_reconciliation | 31.48 |
| E | K1 SWP 固定资产 20251231 E锂原.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **FAIL** | 8 | lead_required_fields | 25.54 |
| F | K1 SWP 固定资产 20251231 F有限公司.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **FAIL** | 15 | lead_required_fields, lead_check_with_a3_row | 39.97 |
| G | K1 SWP 固定资产 20251231 G科技.xlsx | ok | K.00 Lead Sheet | — | 5 | 4 | 7 | **FAIL** | 9 | lead_required_fields, lead_analysis_date_after_period_end | 23.54 |

## 跳过

- `K1 SWP 固定资产 20251231 A有限公司.xlsx` (40.87 MB) — name_contains:A有限公司

## 规则维度（overall_severity）

| 标签 | lead_required_fields | lead_analysis_date_after_period_end | materiality_consistency | risk_threshold_consistency | lead_tt_overall_min | lead_tt_gam_range | lead_expectation_analysis | lead_volatility_threshold_link | lead_movement_rows_complete | lead_movement_consistency | lead_movement_notes_required | lead_check_with_a3_row | unexpected_movement_investigation | lead_rollforward_tb_reconciliation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B | FAIL | FAIL | NEED_REVIEW | NEED_REVIEW | PASS | WARN | PASS | PASS | WARN | PASS | PASS | FAIL | PASS | PASS |
| C | FAIL | PASS | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | PASS | WARN | PASS | PASS | PASS | PASS | PASS |
| D | FAIL | PASS | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | PASS | WARN | PASS | PASS | PASS | PASS | FAIL |
| E | FAIL | PASS | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | PASS | WARN | PASS | PASS | PASS | PASS | PASS |
| F | FAIL | PASS | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | PASS | WARN | PASS | PASS | FAIL | WARN | PASS |
| G | FAIL | FAIL | NEED_REVIEW | NEED_REVIEW | PASS | PASS | PASS | PASS | WARN | PASS | PASS | PASS | PASS | PASS |

## Ingest 基线（手工回归参考）

| 案例 | cra | mov | exp | layout 备注 |
| --- | ---: | ---: | ---: | --- |
| B–G（标准 SWP） | 5 | 4 | 7 | `layout_variant=None` |
| A（跳过） | 0 | — | — | `no_cra_te_volatility`（大文件未跑） |

复跑：`python scripts/run_case_lead_regression.py`

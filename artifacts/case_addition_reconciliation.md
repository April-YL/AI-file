# 案例库 addition_rollforward_reconciliation 回归

- 案例库：`E:\AI file\固定资产质检agent\案例库`
- 生成时间：2026-06-04 06:37 UTC

| 案例 | 新增清单 | 清单购置合计 | K.01 购置 | 勾稽结论 | 耗时(s) |
| --- | --- | --- | --- | --- | --- |
| A | 跳过 | — | — | name_contains:A有限公司 | — |
| B | 无 (0行) | — | 25746.67 | PASS（一致或未触发） | 32.79 |
| C | 新增清单 (1行) | 10336.28 | 10336.28 | PASS（一致或未触发） | 50.9 |
| D | 新增清单 (50行) | 1146059.23 | 542691.72 | WARN：新增清单购置原值合计=1146059.23（11 行），K.01 后推购置金额=542691.72，差异=603367.51。 差异超过 SAD… | 50.57 |
| E | 无 (0行) | — | 7916311.98 | PASS（一致或未触发） | 44.71 |
| E | 无 (0行) | — | 7916311.98 | PASS（一致或未触发） | 43.54 |
| E | 无 (0行) | — | 7916311.98 | PASS（一致或未触发） | 43.49 |
| E | 无 (0行) | — | 7916311.98 | PASS（一致或未触发） | 44.94 |
| F | 新增清单 (191行) | 0 | 2791225.65 | WARN：新增清单购置原值合计=0（0 行），K.01 后推购置金额=2791225.65，差异=2791225.65。 差异超过 SAD（290030.… | 58.08 |
| G | K.02.1b 新增清单 (41行) | 41598444.50999999992 | 31019.47 | WARN：新增清单购置原值合计=41598444.50999999992（35 行），K.01 后推购置金额=31019.47，差异=41567425.0… | 41.86 |

## 明细

### A — 跳过 (name_contains:A有限公司)

### B — K1 SWP 固定资产 20251231 B医疗公司.xlsx
- 整体结论：FAIL；findings 总数：72
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：无 issue

### C — K1 SWP 固定资产 20251231 C新材料有限公司.xlsx
- 整体结论：FAIL；findings 总数：24
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：无 issue

### D — K1 SWP 固定资产 20251231 D锂电科技有限公司.xlsx
- 整体结论：FAIL；findings 总数：437
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：新增清单购置原值合计=1146059.23（11 行），K.01 后推购置金额=542691.72，差异=603367.51。 差异超过 SAD（194000），需调查。

### E — K1 SWP 固定资产 20251231 E锂原 - 测试0603.xlsx
- 整体结论：FAIL；findings 总数：15
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：无 issue

### E — K1 SWP 固定资产 20251231 E锂原 - 测试0604.xlsx
- 整体结论：FAIL；findings 总数：18
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：无 issue

### E — K1 SWP 固定资产 20251231 E锂原 -测试0602.xlsx
- 整体结论：FAIL；findings 总数：11
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：无 issue

### E — K1 SWP 固定资产 20251231 E锂原.xlsx
- 整体结论：FAIL；findings 总数：11
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：无 issue

### F — K1 SWP 固定资产 20251231 F有限公司.xlsx
- 整体结论：FAIL；findings 总数：243
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：新增清单购置原值合计=0（0 行），K.01 后推购置金额=2791225.65，差异=2791225.65。 差异超过 SAD（290030.351925），需调查。

### G — K1 SWP 固定资产 20251231 G科技.xlsx
- 整体结论：FAIL；findings 总数：112
- movement 交易行：['在建工程转入', '处置或报废', '计提', '购置']（共 7 条）
- **addition_rollforward_reconciliation**：新增清单购置原值合计=41598444.50999999992（35 行），K.01 后推购置金额=31019.47，差异=41567425.03999999992。 差异超过 SAD（165000），需调查。

复跑：`python scripts/run_case_addition_reconciliation.py`
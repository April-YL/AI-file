# 案例库 K.01 识别回归表

- 生成时间（UTC）：2026-05-28T15:31:31Z
- 案例库：`D:\AI file\固定资产质检agent\案例库`
- 跳过策略：>20.0MB 或文件名含 A公司/A有限公司
- 扫描行数上限：`max_rows=150`

## 汇总

| 标签 | 文件 | 状态 | K.01 表 | profile | 区块 | 置信度 | 冲突 | 耗时(s) |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: |
| B | K1 SWP 固定资产 20251231 B医疗公司.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 5 | 9.57 |
| C | K1 SWP 固定资产 20251231 C新材料有限公司.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 5 | 16.7 |
| D | K1 SWP 固定资产 20251231 D锂电科技有限公司.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 6 | 16.15 |
| E | K1 SWP 固定资产 20251231 E锂原.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 6 | 13.36 |
| F | K1 SWP 固定资产 20251231 F有限公司.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 6 | 20.18 |
| G | K1 SWP 固定资产 20251231 G科技.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 5 | 12.06 |

## 跳过

- `K1 SWP 固定资产 20251231 A有限公司.xlsx` (40.87 MB) — name_contains:A有限公司

## 基线期望（B–G）

- `layout_profile` = `hybrid`
- `sections_detected` = 6
- 六区块命中后允许存在 `duplicate_anchor` 等冲突（见 `section_conflicts`）

复跑：`python scripts/run_case_rollforward_regression.py`

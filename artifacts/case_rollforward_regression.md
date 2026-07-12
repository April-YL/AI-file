# 案例库 K.01 识别回归表

- 生成时间（UTC）：2026-07-11T18:10:35Z
- 案例库：`E:\AI file\固定资产质检agent\案例库`
- 跳过策略：>20.0MB 或文件名含 A公司/A有限公司
- 扫描行数上限：`max_rows=150`

## 汇总

| 标签 | 文件 | 状态 | K.01 表 | profile | 区块 | 置信度 | 冲突 | 耗时(s) |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: |
| B | K1 SWP 固定资产 20251231 B医疗公司.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 10 | 2.26 |
| G | K1 SWP 固定资产 20251231 G科技.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 10 | 4.62 |
| K1 固定资产 2025 | K1 固定资产 20251231 H调温器有限公司.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 10 | 6.06 |
| K1 固定资产 2025 | K1 固定资产 20251231 J有限公司 - 副本.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 10 | 8.57 |
| K1 固定资产 2025 | K1 固定资产 20251231 J有限公司.xlsx | ok | K.01 Agree SL to GL | hybrid | 6/6 | 0.4 | 10 | 8.0 |

## 跳过

- `~$K1 固定资产 20251231 J有限公司.xlsx` (0.0 MB) — excel_lock_file

## 基线期望（B–G）

- `layout_profile` = `hybrid`
- `sections_detected` = 6
- 六区块命中后允许存在 `duplicate_anchor` 等冲突（见 `section_conflicts`）

复跑：`python scripts/run_case_rollforward_regression.py`

# 四张完整底稿结构化摘要

- 生成日期：2026-06-24
- 案例库：`E:\AI file\固定资产质检agent\案例库`
- 用途：作为后续修复 bug 时选择最小回归样本的参考。
- 安全口径：本文只记录工作簿结构、sheet 识别、模块计数、勾稽状态和测试用途，不记录资产明细、人员、合同、发票等敏感信息。

## 使用建议

| 修改范围 | 建议优先案例 | 目的 |
| --- | --- | --- |
| 汇总页 / PSP | B、G、H、J | 覆盖标准 SWP、非 SWP、完整大底稿的汇总页结构。 |
| K.00 Lead | B、G、H、J | 四张均有 Lead，可观察 CRA、变动表、基础字段读取是否稳定。 |
| K.01 后推 | B、G、H、J | 四张均有 K.01，且包含匹配、不匹配、候选 sheet 干扰等情况。 |
| K.02 新增 | B、G、H、J | 覆盖标准新增、差异较大、新增豁免、完整执行。 |
| K.02 处置 | G、H、J | G 有处置清单但无处置测试，H 有处置豁免，J 有完整处置测试和选样输出。 |
| K.03 折旧 | B、G、H、J | 覆盖单表、多表、明细大表和折旧政策复核。 |
| report / 标注 / UI | B、J | B 适合快速小样本，J 适合完整大样本和性能冒烟。 |
| sheet 路由边界 | G、H、J | 存在 K.03 误入 rollforward 候选、FA list 误选、候选排序等风险点。 |

## 案例总览

| 案例 | 文件 | 大小 | sheet 数 | 主要价值 |
| --- | --- | ---: | ---: | --- |
| B | `K1 SWP 固定资产 20251231 B医疗公司.xlsx` | 0.83 MB | 19 | 标准 SWP 小型完整底稿，适合快速整链路回归。 |
| G | `K1 SWP 固定资产 20251231 G科技.xlsx` | 1.36 MB | 15 | 新增勾稽差异明显，无处置测试 sheet，适合边界场景。 |
| H | `K1 固定资产 20251231 H调温器有限公司.xlsx` | 1.11 MB | 13 | 非 SWP 命名，新增含在建工程转入，当前存在 FA list 选择风险。 |
| J | `K1 固定资产 20251231 J有限公司.xlsx` | 3.92 MB | 19 | 较大完整底稿，新增/处置/选样/K.03 多模块齐全。 |

## B — B医疗公司

### 当前选择的关键 sheet

| 模块 | sheet |
| --- | --- |
| 汇总页 | `汇总 ` |
| Lead | `K.00 Lead Sheet` |
| K.01 后推 | `K.01 Agree SL to GL` |
| FA list | `K.01.1a FA list` |
| 新增清单 | `新增清单` |
| 新增测试 | `K.02.1 新增测试 ` |
| 新增选样输出 | `K.02.1a 新增选样输出` |
| 处置清单 | `处置清单` |
| 处置测试 | `K.02.2 处置测试` |
| K.03 | `K1_400折旧测试`、`K.03.1 SAP`、`K.03.2 折旧测试TOD`、`K.03.3 折旧政策复核` |

### 关键计数

| 项目 | 数量 |
| --- | ---: |
| 汇总页程序 | 12 |
| Lead CRA 行 | 5 |
| Lead 变动行 | 4 |
| FA list 记录 | 314 |
| 新增清单记录 | 20 |
| 处置清单记录 | 3 |
| K.03 sheet | 4 |
| 勾稽检查 | 5 |

### 勾稽基线

| link_id | 当前状态 |
| --- | --- |
| `fa_list_rollforward_net` | mismatch |
| `fa_list_rollforward_original` | mismatch |
| `fa_list_rollforward_accum_dep` | mismatch |
| `addition_list_rollforward` | match |
| `disposal_list_rollforward` | need_review |

### 适合测试

- 标准 SWP 的汇总页、Lead、K.01、K.02、K.03 是否能完整识别。
- FA list 与 K.01 后推不一致时，勾稽 finding 是否稳定。
- 处置测试已识别但当前不适合确定性规则时，是否正确进入人工复核或跳过说明。
- 小型报告、标注、UI 展示是否正常。

### 风险点

- `K1_400折旧测试` 列数很大，可能影响 K.03 识别或性能。
- 处置测试 note 含 `disposal_test_not_usable_for_deterministic_rules`，适合防止执行台账解释不清。

## G — G科技

### 当前选择的关键 sheet

| 模块 | sheet |
| --- | --- |
| 汇总页 | `汇总 ` |
| Lead | `K.00 Lead Sheet` |
| K.01 后推 | `K.01 Agree SL to GL` |
| FA list | `K.01.1a FA list` |
| 新增清单 | `K.02.1b 新增清单` |
| 新增测试 | `K.02.1 新增测试 ` |
| 新增选样输出 | `K.02.1a新增选样输出` |
| 处置清单 | `处置清单` |
| 处置测试 | 未识别 |
| K.03 | `K.03.3 折旧政策复核`、`K.03.2 折旧测试TOD-by item测试` |

### 关键计数

| 项目 | 数量 |
| --- | ---: |
| 汇总页程序 | 12 |
| Lead CRA 行 | 5 |
| Lead 变动行 | 4 |
| FA list 记录 | 2104 |
| 新增清单记录 | 40 |
| 处置清单记录 | 10 |
| K.03 sheet | 2 |
| 勾稽检查 | 5 |

### 勾稽基线

| link_id | 当前状态 |
| --- | --- |
| `fa_list_rollforward_net` | match |
| `fa_list_rollforward_original` | mismatch |
| `fa_list_rollforward_accum_dep` | mismatch |
| `addition_list_rollforward` | mismatch |
| `disposal_list_rollforward` | need_review |

### 适合测试

- 新增清单与 K.01 后推差异较大时，新增勾稽规则是否稳定。
- 有处置清单但无处置测试 sheet 时，是否正确展示“不适用/数据不足/需人工复核”。
- K.03 明细较多时，K.03 识别和报告性能是否稳定。
- UI 是否能解释有清单但缺测试 sheet 的情况。

### 风险点

- `K.03.2 折旧测试TOD-by item测试` 当前也进入 rollforward 候选，适合防止 sheet 分类漂移。
- 新增勾稽差异非常大，适合测试高风险 finding 不被 report/UI 隐藏。

## H — H调温器

### 当前选择的关键 sheet

| 模块 | sheet |
| --- | --- |
| 汇总页 | `汇总 ` |
| Lead | `K.00 Lead Sheet` |
| K.01 后推 | `K.01 Agree SL to GL` |
| FA list | `处置清单`（当前选择结果，存在风险） |
| 新增清单 | `新增清单` |
| 新增测试 | `K.02.1 新增测试 ` |
| 新增选样输出 | 未识别 |
| 处置清单 | 未选中 |
| 处置测试 | `K.02.2 处置测试` |
| K.03 | `K.03.2 折旧测试`、`K.03.3 折旧政策复核` |

### 关键计数

| 项目 | 数量 |
| --- | ---: |
| 汇总页程序 | 12 |
| Lead CRA 行 | 5 |
| Lead 变动行 | 4 |
| FA list 记录 | 157 |
| 新增清单记录 | 47 |
| 处置清单记录 | 0 |
| K.03 sheet | 2 |
| 勾稽检查 | 5 |

### 勾稽基线

| link_id | 当前状态 |
| --- | --- |
| `fa_list_rollforward_net` | missing_left |
| `fa_list_rollforward_original` | mismatch |
| `fa_list_rollforward_accum_dep` | mismatch |
| `addition_list_rollforward` | match |
| `disposal_list_rollforward` | not_applicable |

### 适合测试

- 非 SWP 命名底稿的 sheet 路由。
- 新增测试存在豁免说明时，规则和报告是否正确处理。
- 新增清单含在建工程转入等非纯购置场景时，金额口径是否稳定。
- FA list 被误选为 `处置清单` 的读取层问题，适合作为 sheet 选择优先级回归样本。

### 风险点

- 当前 `selected.fa_list = 处置清单`，实际存在 `FA list` sheet，这是典型读取层风险，不应通过规则层放宽掩盖。
- `FA list` 同时进入 addition_list 候选，适合防止台账误当新增清单。
- 处置测试存在豁免说明，但 disposal_list 未选中，适合测试豁免/不适用展示。

## J — J有限公司

### 当前选择的关键 sheet

| 模块 | sheet |
| --- | --- |
| 汇总页 | `汇总` |
| Lead | `K.00 Lead Sheet` |
| K.01 后推 | `K.01 Agree SL to GL` |
| FA list | `FA list` |
| 新增清单 | `新增清单` |
| 新增测试 | `K.02.1 新增测试` |
| 新增选样输出 | `K.02.1a 新增选样输出` |
| 处置清单 | `处置清单` |
| 处置测试 | `K.02.2 处置测试 ` |
| 处置选样输出 | `K.02.2a 处置选样输出` |
| K.03 | `K.03.1 SAP-中精确度`、`K.03.1 SAP-高精确度`、`K.03.2 折旧测试TOD-by item测试`、`K.03.3 折旧政策复核`、`K.03.2 折旧测试TOD-抽样`、`K.03.2a 折旧选样输出` |

### 关键计数

| 项目 | 数量 |
| --- | ---: |
| 汇总页程序 | 16 |
| Lead CRA 行 | 5 |
| Lead 变动行 | 4 |
| FA list 记录 | 11394 |
| 新增清单记录 | 1006 |
| 处置清单记录 | 42 |
| K.03 sheet | 6 |
| 勾稽检查 | 5 |

### 勾稽基线

| link_id | 当前状态 |
| --- | --- |
| `fa_list_rollforward_net` | match |
| `fa_list_rollforward_original` | match |
| `fa_list_rollforward_accum_dep` | match |
| `addition_list_rollforward` | match |
| `disposal_list_rollforward` | need_review |

### 适合测试

- 新增测试、处置测试、选样输出完整场景。
- 较大 FA list 和 K.03 明细表下的性能冒烟测试。
- report、标注副本、UI 下载产物的大样本稳定性。
- 多 K.03 / SAP / 抽样 sheet 的分类和展示。

### 风险点

- `For Disclosure`、`K.03.2 折旧测试TOD-by item测试`、`本期计提` 当前也进入 rollforward 候选，适合测试候选排序与最终选择稳定性。
- 记录量较大，适合发现 report 重复展示、Comments 行数膨胀、UI 卡顿等问题。
- 处置清单与后推减少净值当前仍为 `need_review`，适合验证人工复核提示是否清楚。

## 后续可演进为 snapshot 的字段

第一阶段建议只比对以下轻量字段，避免测试过重：

- `selected_sheets`
- `key_counts`
- `reconciliation_baseline`
- `recognized_sheets_by_kind` 中关键模块是否存在
- `module_notes` 中测试 sheet 是否识别、样本数是否稳定

暂不建议比对：

- 完整 JSON 报告
- 完整 HTML
- 完整标注副本
- 逐行资产 finding 明细
- LLM 原始输出


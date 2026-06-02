# K.01 Agree SL to GL — 六区块质检覆盖矩阵

> **用途**：按工作表**物理六区块**对照 SOP 风险点，明确检查方式与 Agent 实现状态。  
> **关联**：[k01-qc-rules.md](./k01-qc-rules.md)（SOP【01】–【03】模块）、[k01-workpaper-layouts.md](./k01-workpaper-layouts.md)、[program-qc-coverage-index.md](./program-qc-coverage-index.md)  
> **ingest 键名**：`section_presence` / `section_regions` / `section_conflicts` / `recognition_confidence`

## 六区块与 SOP 模块

| 区块 ID | 工作表区块 | SOP 模块 |
| --- | --- | --- |
| `b1_bkd_main_table` | 表1 BKD 主矩阵 | 【01】填列 BKD |
| `b2_movement_tb_reconciliation` | 变动 / TB / 差异 | 【02】期末 vs TB |
| `b3_table2_fa_summary` | 表2 清单分类汇总 | 【02】FA list 汇总 |
| `b4_table3_check_with_table1` | 表3 表2↔表1 | 【02】清单与后推核对 |
| `b5_table4_depreciation_pl` | 表4 折旧 vs 利润表 | 【02】折旧费用核对 |
| `b6_notes_investigation_routing` | Notes / TE / 程序路由 | 【02】>SAD；【03】>TE |

---

## 区块 1：表1 BKD 主矩阵

**风险**：后推不存在、列不全、金额关系错误、分类/符号/调整错误。

| 风险点 | 应如何检查 | 实现状态 | 规则 / 方式 |
| --- | --- | --- | --- |
| 后推表不存在 | K.01 sheet + 可解析主表 | ✅ | `rollforward_exists`（GL-006） |
| 未定位 b1 主矩阵 | 六区块 `b1` + 表1/固定资产类别锚点 | ✅ | `rollforward_exists`（增强） |
| 四口径×期初/变动/期末不全 | L1 列绑定 + opening/ending/movement | ✅ | `rollforward_columns_complete`（GL-007） |
| 累折>原值、负净值、转出异常 | 合计 + 明细金额关系 | ✅ | `rollforward_abnormal_amounts`（GL-005） |
| 购置/处置分类错、减少符号 | 交易行标签 + 符号 | ⏳ | `rollforward_sign_convention` |
| 调整列与 Lead 一致 | 调整列 vs K.00 | ⏳ | `rollforward_adjustment_link_lead` |
| 期初滚调三种情形 | 上年 TB/JE | ❌ 人工 | `NEED_REVIEW` |

**验收**：`b1` presence；GL-006/007/005 对案例库 B–G 无 FAIL（或 FAIL 带 `source_row`）。

---

## 区块 2：变动 / TB 勾稽区

**风险**：与试算表/明细账不一致；超 SAD 未调查。

| 风险点 | 应如何检查 | 实现状态 | 规则 / 方式 |
| --- | --- | --- | --- |
| TB 勾稽区可靠识别 | 同时出现 TB/试算表口径 + 差异 | ✅ 读取层 | `tb_reconciliation_detected` / `tb_reconciliation_confidence` |
| 差异金额摘录 | 从差异行/列读取金额 | ✅ 读取层 | `tb_difference_values` / `tb_difference_row` |
| 期末账面 vs TB | K.01 vs 外部 TB | ⏳ 摘录 | `rollforward_ending_reconciliation` → `NEED_REVIEW` |
| 差异 >SAD | 差异 vs Lead SAD + Notes | ✅ | `rollforward_difference_over_sad`（GL-008） |
| 差异说明不充分 | Notes 四要素 | ⏳ 人工/LLM | 有 Notes → `NEED_REVIEW` |

---

## 区块 3：表2（FA list 分类汇总）

| 风险点 | 应如何检查 | 实现状态 | 规则 / 方式 |
| --- | --- | --- | --- |
| 表2 缺失 | 识别 `b3` | ✅ 识别 | hybrid 缺表2 → WARN（规划） |
| 表2 vs FA list 合计 | 识别表2，确认有 SUMIF 汇总金额 | ✅ 辅助 | `rollforward_fa_list_reconciliation`（GL-002；表2作辅助，不作为主结论） |
| 分类口径不一致 | 类别映射 + 说明 | ❌ | `NEED_REVIEW` |

---

## 区块 4：表3（表2 check with 表1）

| 风险点 | 应如何检查 | 实现状态 | 规则 / 方式 |
| --- | --- | --- | --- |
| 表3 / check-with 缺失 | 识别 `b4` | ✅ 识别 | 缺失 → WARN（规划） |
| 表2 与表1 不一致 | 表3 差异 / check 结果 | ✅ | `rollforward_fa_list_reconciliation`（GL-002 主检查） |
| 与 b2、Notes 矛盾 | 报告层交叉 | ❌ | 冲突清单（规划） |

---

## 区块 5：表4（折旧 vs 利润表）

| 风险点 | 应如何检查 | 实现状态 | 规则 / 方式 |
| --- | --- | --- | --- |
| 表4 缺失 | 识别 `b5` | ✅ 识别 | 缺失 → WARN（规划） |
| 表1 折旧 vs 表4 vs PL | 三边金额 | ❌ 无 PL | `rollforward_depreciation_pl_reconciliation` |
| 差异 >SAD | 同区块2 | ❌ | 同 SAD 规则 |
| 分摊/首年计提等 | 职业判断 | ❌ | LLM / 人工 |

---

## 区块 6：Notes / 差异调查 / TE 路由

| 风险点 | 应如何检查 | 实现状态 | 规则 / 方式 |
| --- | --- | --- | --- |
| Notes 空白 | 识别 `b6` + 文本 | ✅ 识别（弱） | 有 material 差异无 Notes → FAIL（规划） |
| >SAD 无调查结论 | Notes 四要素 | ❌ | 摘录 + LLM |
| >TE 未执行 K.02/K.03 | BKD vs TE + 汇总索引 | ⏳ | `rollforward_te_program_routing` |
| 错误拒绝 PSP | 汇总 G/H 列 | ✅ | AE-003（汇总程序） |
| 特殊交易另册 | 合并/持有待售等 | ❌ | `NEED_REVIEW` |

---

## 六区块 × 实现层级（一览）

| 区块 | 表内 P0 | 跨表 M2b | 说明 / 程序 |
| --- | --- | --- | --- |
| 1 表1 | ✅ GL-006/007/005 | ⏳ Lead 调整 | 滚调人工 |
| 2 变动/TB | ✅ 识别 + TB check 摘录 | ✅ SAD + Notes | GL-008 |
| 3 表2 | ✅ 识别 | ✅ SUMIF 汇总辅助 | 分类说明 |
| 4 表3 | ✅ 识别 | ✅ 表2↔表1 check | GL-002 主检查 |
| 5 表4 | ✅ 识别 | ❌ PL/TB | 分摊 LLM |
| 6 Notes | ✅ 识别 | — | TE、AE-003、LLM |

---

## 当前实现摘要（2026-06-02）

- **识别层**：`RollforwardSheetDataset.section_*`；案例库 B–G：`hybrid`，六区块 **6/6**（`scripts/run_case_rollforward_regression.py`）。  
- **P0 规则**：`run_rollforward_rules` → exists + columns_complete + abnormal_amounts。  
- **M2b 首版**：`rollforward_fa_list_reconciliation`（GL-002）主读 K.01 表3 check 结果；表3非零差异为 `WARN`，表3不可读时结合表2识别和 Agent 自算合计给 `NEED_REVIEW` 兜底提示。  
- **TB check 读取层**：已新增 `tb_reconciliation_detected`、`tb_reconciliation_confidence`、`tb_difference_values`、`tb_notes_text` 等字段；只有 TB/试算表口径和“差异”同时出现，才视为可靠 TB check，单纯“变动金额”不直接当作 TB 核对结论。
- **GL-008**：`rollforward_difference_over_sad` 已接入 K.01 runner；TB check 差异未超过 SAD 不报，超过 SAD 且无 Notes 输出 `FAIL`，超过 SAD 且已有 Notes 输出 `NEED_REVIEW`。
- **报告**：`rollforward_sheet_section`；CLI `fa-qc-run` 打印 K.01 QC 一行。  
- **交叉**：`lead_rollforward_tb_reconciliation`（LEAD-010）在 Lead 规则中执行，非 K.01 表内。

**下一步建议（M2b）**：GL-002 表3模板变体增强 → `rollforward_te_program_routing` → 表4/PL 勾稽。

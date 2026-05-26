# K.01 后推明细表质检规则规划

> **来源**：`FY26_SOP K1 SWP 固定资产.xlsx` → `K.01 Agree SL to GL`（K1.01-【01】～【03】）、案例库 B–G 实测、`docs/qc-checklist.md` §三。  
> **版式**：见 [k01-workpaper-layouts.md](./k01-workpaper-layouts.md)。  
> **实现前必读**：`docs/qc-checklist.md`、`docs/workpaper-fields.md` § K.01、`docs/audit-workflow.md` § K.01。

## 背景

| 项 | 状态 |
| --- | --- |
| Ingest | `rollforward_sheet.py` → `RollforwardSheetDataset`（bindings、opening/ending totals、合计行） |
| 已有规则 | `lead_rollforward_tb_reconciliation`（Lead 期末 vs K.01 `ending_totals`，procedure **K.00**） |
| 规划 P0 | `rollforward_exists`、`rollforward_columns_complete`（**L1**，见 layouts 文档） |
| 案例库 | B–G 多为 `hybrid`；ingest 期初/期末列语义待增强 |
| 外部 | TB 全文、A3、Canvas、Notes 调查充分性 **未接入** |

**自动化分层**（与 [lead-qc-rules.md](./lead-qc-rules.md) 一致）

| 层级 | 含义 | Agent 结论 |
| --- | --- | --- |
| **M2a 确定性** | 表存在、列矩阵 L1、明显异常金额 | `FAIL` / `WARN` |
| **M2b 勾稽** | 两侧金额可比（Lead、FA list、清单合计） | `FAIL` / `WARN` |
| **M2 摘录** | 无 TB/PL/滚调输入 | `NEED_REVIEW` + 人工核对 HTML |
| **M3 / LLM** | 差异调查是否充分、分类是否合理 | 不改 severity |

---

## SOP 三段与模块划分

| SOP 块 | 主题 | 本文模块 |
| --- | --- | --- |
| K1.01-【01】 | 填列后推明细表（BKD / 表1） | **模块 A** |
| K1.01-【02】 | 核对（Lead、TB、FA list、折旧费用） | **模块 B** |
| K1.01-【03】 | 实质性程序执行判断（>TE → K.02/K.03） | **模块 C** |

指引全文摘录：`artifacts/_k01_sop_guidance.txt`（本地资料库生成，不入 Git 亦可）。

---

## 模块 A：填列 BKD（SOP【01】）

**Ingest**：`RollforwardSheetDataset`；profile 见 layouts。

### 业务检查点

| # | 检查点 | SOP 要点 |
| --- | --- | --- |
| A.1 | 后推明细表存在 | 获取上期末至本期末（或中期）后推表 |
| A.2 | 按类别与交易填列 | 表1：类别 × 交易行 × 账面/调整/审定 |
| A.3 | 填列口径 | 原值/累折/减值为正；本期减少用 **负数**；调整 **link K.00 Lead** |
| A.4 | 易错：分类与转出 | 购置/处置分类错误；处置转出累折+减值 > 原值 |
| A.5 | 期初滚调 | 上年调整跟调三种情形（进阶） |

### 规则映射

| 规则 ID | 检查内容 | Layout | M2 | 默认 severity | 状态 |
| --- | --- | --- | --- | --- | --- |
| `rollforward_exists` | A.1：识别 K.01 sheet 且可解析主表（header 或表1 锚点） | all | M2a | `FAIL` | **planned** |
| `rollforward_columns_complete` | A.2：**L1** 四口径×期初/变动/期末（layouts 定义） | dual, hybrid | M2a | `FAIL` | **planned** |
| `rollforward_columns_complete` | A.2：**L2** 矩阵+三子列 | sop_bkd | P1 | `FAIL`/`WARN` | planned |
| `rollforward_sign_convention` | A.3：减少类为负（抽样/合计行） | sop, hybrid | P1 | `WARN` | planned |
| `rollforward_adjustment_link_lead` | A.3：调整列与 Lead 一致 | sop_bkd | P1 | `FAIL`/`WARN` | planned |
| `rollforward_abnormal_amounts` | A.4：累折>原值、负净值；处置转出勾稽 | all | M2a | `FAIL`/`WARN` | planned |
| — | A.5 期初滚调 | all | 摘录 | `NEED_REVIEW` | manual |

**字典编码（规划）**：`GL-006` exists、`GL-007` columns_complete；`GL-005` abnormal（procedure 应为 **K.01**，见 rule-dictionary 修正说明）。

---

## 模块 B：核对（SOP【02】）

### 业务检查点（SOP 步骤）

| # | 检查点 | SOP 步骤 |
| --- | --- | --- |
| B.1 | 期初审定 ↔ Lead ↔ 上年 | ① 表1 AL 列 check；Lead 期初 vs A3 |
| B.2 | 期末账面 ↔ 试算表 | ② 表1 下方 check / TB 行 |
| B.3 | 期末 ↔ FA list | ③ 表2 汇总、表3 与表1 核对 |
| B.4 | 期末审定 ↔ Lead ↔ A3 | ④ 同 B.1 期末侧 |
| B.5 | 折旧计提 ↔ 利润表/TB | ⑤ 表4 与表1 折旧合计 |
| B.6 | >SAD 差异调查 | ⑤ + Notes 记录 |

### 规则映射

| 规则 ID | 检查内容 | 依赖 | M2 | 状态 |
| --- | --- | --- | --- | --- |
| `lead_rollforward_tb_reconciliation` | B.2/B.4 部分：Lead 引导表期末 vs K.01 合计 | Lead + K.01 ending | M2b | **implemented** |
| `rollforward_opening_lead_reconciliation` | B.1 期初 vs Lead | Lead opening | M2b | planned |
| `rollforward_fa_list_reconciliation` | B.3 表2/3 vs FA list | FA list + K.01 | M2b | planned（GL-002） |
| `rollforward_ending_reconciliation` | B.2 期末 vs TB（无 TB 输入） | 外部 TB | 摘录 | planned（checklist REVIEW） |
| `rollforward_depreciation_pl_reconciliation` | B.5 表4 | PL/TB | P1 | planned |
| `rollforward_difference_over_sad` | B.6 差异>SAD 须调查 | Lead SAD + diff 行 | M2b | planned |
| `rollforward_notes_on_material_diff` | B.6 Notes 是否填写 | Notes 区文本 | P1 | planned |
| GL-001 `lead_tb_reconciliation` | Lead vs 外部 TB | TB | 摘录 | manual_only |

**易错点（SOP）→ 规则**：期初/期末与 Lead 不一致（B.1/B.4）、与 FA list 差异未调查（B.3）、折旧差异>SAD 未调查（B.5）— 由上表覆盖或 `NEED_REVIEW`。

---

## 模块 C：实质性程序执行判断（SOP【03】）

### 业务检查点

| # | 检查点 | SOP 要点 |
| --- | --- | --- |
| C.1 | BKD 购置/处置/折旧 > **TE** | D 列索引 K.02/K.03 |
| C.2 | 其他交易类型 > TE | 转入、合并、持有待售、减值等 → 另册 |
| C.3 | 汇总页一致 | 判断结论反映在 **汇总** PSP |
| C.4 | 易错 | 错误拒绝 PSP；拒绝无具体理由 |

### 规则映射

| 规则 ID | 检查内容 | M2 | 状态 |
| --- | --- | --- | --- |
| AE-003 `psp_completion` | C.3/C.4 部分：汇总「已执行」与 sheet 索引 | M2b | **implemented**（汇总） |
| `rollforward_te_program_routing` | C.1：BKD 金额 vs TE → 是否应执行 K.02/K.03 | P1 | planned |
| `rollforward_special_transaction_review` | C.2：非三类交易 > TE | 摘录 | planned |
| — | C.2 另册索引 | — | manual |

**边界**：AE-003 看 **汇总页 G 列与程序页**；`rollforward_te_program_routing` 看 **BKD 发生额与 TE**（二者互补，不互相替代）。

---

## 规则映射总表（checklist ↔ SOP ↔ 实现）

| checklist §三 | rule_id | SOP | dict_code（规划） | Profile | 状态 |
| --- | --- | --- | --- | --- | --- |
| 后推明细表存在 | `rollforward_exists` | 【01】 | GL-006 | all | planned |
| 金额口径完整 | `rollforward_columns_complete` | 【01】L1/L2 | GL-007 | dual/hybrid；sop L2 | planned |
| 期末核对 | `rollforward_ending_reconciliation` | 【02】② | — | all | planned / REVIEW |
| 差异调查 | `rollforward_difference_over_sad` | 【02】⑤ | — | all | planned |
| 异常金额 | `rollforward_abnormal_amounts` | 【01】易错 | GL-005 | all | planned |
| （交叉） | `lead_rollforward_tb_reconciliation` | 【02】④ | LEAD-010 | hybrid+ | **implemented** |
| （交叉） | `rollforward_fa_list_reconciliation` | 【02】③ | GL-002 | dual/hybrid | planned |

---

## M2a 实现顺序（建议）

| 阶段 | 交付 | 验收 |
| --- | --- | --- |
| **P0-1** | docs（本文 + layouts） | 团队对齐 L1/L2 |
| **P0-2** | ingest：审2/审3、变动 token、选 sheet | B–G bindings 有 opening/ending |
| **P0-3** | `rollforward_exists` + `rollforward_columns_complete`（L1）+ runner + registry | pytest + `fa-qc-run` 案例 B |
| **P0-4** | `rollforward_abnormal_amounts` | 负净值、处置转出 |
| **P1** | `rollforward_fa_list_reconciliation`、opening Lead、表4、TE 路由、L2 矩阵 ingest | 案例+SOP 模板 |

---

## 与 FA list 规则边界

| 主题 | K.01 | FA list |
| --- | --- | --- |
| 卡片级异常（寿命、资本化改原值等） | — | `fa_list_*` / SOP FA list 易错 |
| 后推表分类/转出/矩阵 | `rollforward_*` | — |
| 期末与清单合计 | `rollforward_fa_list_reconciliation` | 输入来自 ingest |

`rollforward_abnormal_amounts` 字典项 **procedure_code 应为 `K.01`**（非 `FA_LIST`）。

---

## SOP 遗漏与人工复核清单

| 主题 | 处理 |
| --- | --- |
| 期初滚调三种情形 | `NEED_REVIEW` + handoff 摘录 |
| 折旧分摊商业合理性 | P1 摘录或 `--llm-rules` |
| 持有待售/合并/减值另册 | 提示索引，不 FAIL 标准 K.01 |
| A3 / Canvas TE 最终版 | Lead AE-001/002 摘录 |
| 表4 完整勾稽 | P1 |

---

## 相关文件

- [k01-workpaper-layouts.md](./k01-workpaper-layouts.md)
- `src/ingest/rollforward_sheet.py`、`src/rules/lead_rollforward_tb_reconciliation.py`
- `docs/qc-checklist.md` §三、`docs/rule-dictionary-mapping.md`
- `docs/handoff/latest.md`

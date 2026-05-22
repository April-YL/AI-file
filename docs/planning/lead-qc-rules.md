# K.00 Lead Sheet 质检规则规划

> **来源**：业务说明 `FA_lead规则说明.txt`（2026-05-20）、EY GAM 测试阈值指引、`FY26_SOP K1 SWP 固定资产.xlsx` → `K.00 Lead Sheet`（K1.00-【01】～【05】指引，2026-05-21 对照）、项目 ingest/规则现状。  
> **实现前必读**：`docs/qc-checklist.md`、`docs/workpaper-fields.md` § K.00。

## 背景

| 项 | 状态 |
| --- | --- |
| Ingest | `lead_sheet_blocks.py` 锚点 **6 块**（不依赖固定行号）→ `LeadSheetDataset` |
| 已有规则 | AE-001 `materiality_consistency`、AE-002 `risk_threshold_consistency`（摘录 + `NEED_REVIEW`） |
| 版式变体 | `layout_variant=no_cra_te_volatility`（案例 A）：无 CRA/TT 区，波动幅度金额 link **TE**（已人工确认） |
| 外部底稿 | A3、Canvas、项目组 CRA 表、A3A5 **尚未接入**；M2 以摘录 + Lead 内勾稽为主 |

**自动化分层约定**

| 层级 | 含义 | Agent 结论 |
| --- | --- | --- |
| **M2 确定性** | 结构、日期逻辑、数值勾稽、GAM 区间、超门槛未调查 | `FAIL` / `WARN` |
| **M2 摘录** | 需与 A3/Canvas/CRA 表比对但无输入 | `NEED_REVIEW` + `manual_review_sections` |
| **M3 / LLM（层 2，`--llm-rules`，规划）** | 预期是否合理、波动说明是否充分、调整是否恰当 | 规则先标 `NEED_REVIEW`；LLM 挂 `llm_rationale`（**不**改 severity） |
| **M2 确定性（P0，优先）** | 必填、超门槛、GAM、Lead↔K.01、Notes 一致性等 | `FAIL`/`WARN` 由 `rules` 判定 |

---

## 模块 1：基准信息块

**Ingest**：`basic_info_fields`、`materiality`（PM/TE/SAD）。

### 业务检查点（`FA_lead规则说明`）

| # | 检查点 | 说明 |
| --- | --- | --- |
| 1.1 | 客户名称 | 准确且已更新 |
| 1.2 | 期末 | 与资产负债表日一致；底稿内日期一致 |
| 1.3 | 分析日期 | **不得早于** 资产负债表日（允许与期末同日） |
| 1.4 | TE、SAD | 与 A3、Canvas 最终版一致 |
| 1.5 | 适用会计准则（GAAP） | 与 Canvas 一致 |
| 1.6 | 记账本位币 | 与 A3 或 Canvas 一致 |

**现阶段**：除 **1.3** 外，1.1/1.2/1.4–1.6 无法对接外部系统，**先摘录**；接入 A3/Canvas 后再做一致性 FAIL。

### 规则映射

| 规则 ID | 检查内容 | M2 |
| --- | --- | --- |
| `lead_required_fields` | 1.1–1.6 字段存在且非空 | 缺项 → `FAIL` |
| `lead_analysis_date_after_period_end` | 1.3 分析日期 ≥ 期末 | 早于期末 → `FAIL`；无法解析日期 → `WARN` |
| AE-001 `materiality_consistency` | 1.4 TE/SAD（及 PM 摘录） | 有值 → `NEED_REVIEW`（Canvas）；不与 `lead_required_fields` 重复 WARN 缺 TE/SAD |
| （未来）`lead_period_end_consistency` | 1.2 底稿内期末一致 | 需跨 sheet 上下文 |

**必填字段**（`lead_required_fields`）：`client_name`, `period_end`, `analysis_date`, `te`, `sad`, `gaap`, `currency`。PM 仍由 AE-001 摘录，不纳入 AUTO_FAIL（除非业务变更）。

---

## 模块 2：CRA / TT 块

**Ingest**：`cra_rows`（认定、CRA、TT）、`tt_overall`（「所有相关认定」/整体 Threshold）。

**简版** `no_cra_te_volatility`：**跳过**本模块 GAM/CRA 检查；波动金额改走 TE（见模块 3）。

### 业务检查点

| # | 检查点 | 说明 |
| --- | --- | --- |
| 2.1 | 认定 CRA | 5 项认定 CRA 选择正确（与项目组 CRA 表一致） |
| 2.2 | 认定 TT | 各认定 TT 由 CRA 表确定，且符合 **EY GAM** 区间；与 CRA 表数值一致 |
| 2.3 | 整体 TT | 整体 Threshold = 各认定 TT 的 **最小值**，**排除 0**；TT 通常不为 0 |

**现阶段**：CRA 表未接入 → **GAM 区间** + **2.3 Lead 内勾稽** 可 AUTO；与 CRA 表一致性 → 摘录 + `NEED_REVIEW`。

### EY GAM：综合风险评估与测试阈值（资产/收入账户）

固定资产 Lead 按 **资产/收入账户** 理解 TT 占 TE 的比例区间（负债/费用账户区间更低，本程序一般不适用）。

**CRA 四档**（控制风险 × 固有风险）：

| 控制风险 | 固有风险 | 综合风险评估（CRA） |
| --- | --- | --- |
| 依赖控制 | 较低 | **最低 (Lowest)** |
| 依赖控制 | 较高 | **低 (Low)** |
| 不依赖控制 | 较低 | **中等 (Moderate)** |
| 不依赖控制 | 较高 | **高 (High)** |

**示例测试阈值（占 TE 的 %）— 资产/收入账户**：

| CRA | TT 占 TE 建议区间 |
| --- | --- |
| 最低 | 75% – 100% |
| 低 | 50% – 75% |
| 中等 | 25% – 50% |
| 高 | 10% – 25% |

**GAM 脚注（规则设计时注意）**

1. 阈值为职业判断 **起点**，非机械唯一值。  
2. 选关键项需职业判断；无关键项时应考虑代表性样本（M3/人工）。  
3. 负债/费用账户侧重完整性，阈值常更低（固定资产 Lead 可忽略此行）。  
4. 采用自动化技术测试时，证据质量更高，测试窗口可放宽（底稿未结构化标注前暂不规则化）。

**程序性质 / 测试期间**（表中「主要实质性程序」「示例期间」）：M2 **摘录 + NEED_REVIEW**，提示质检员对照 GAM，不自动 FAIL。

### 规则映射

| 规则 ID | 检查内容 | M2 |
| --- | --- | --- |
| AE-002 `risk_threshold_consistency` | 2.1–2.2 摘录认定 CRA/TT | 标准版：`NEED_REVIEW`；简版：**跳过** CRA 缺失 WARN |
| `lead_tt_overall_min`（待建） | 2.3 整体 TT = min(认定 TT，排除 0) | 不一致 → `FAIL`/`WARN`；整体 TT=0 → `WARN` |
| `lead_tt_gam_range`（待建） | 2.2 各认定 TT/TE 是否在 GAM 区间 | 超出区间 → `WARN`（可配置是否 `FAIL`）；缺 TE 或 CRA 枚举无法映射 → `NEED_REVIEW` |
| （未来）`lead_cra_table_consistency` | 与项目组 CRA 表一致 | 需 CRA 表 ingest |

**CRA 枚举映射**：底稿 CRA（如 Minimal/Low/Moderate/High）与 GAM 四档的对应关系在 `domain-glossary.md` 维护后再实现 `lead_tt_gam_range`。

---

## 模块 3：预期分析 + 波动门槛（ARP）

**Ingest**：`expectations`（约 7 类账户变更预期）、`volatility`（波动幅度金额、%）。

### 业务检查点

| # | 检查点 | 说明 |
| --- | --- | --- |
| 3.1 | 预期分析 | 约 7 项，**非逐项必填**；重点：预期与 **实际变动是否一致** |
| 3.2 | 波动门槛 | 波动幅度金额：标准版默认 **= TT**；比例默认 **10%**，可自定义 |
| 3.3 | 超门槛 | 超过金额或比例门槛的变动须添加 **Note**，并在 **模块 5 波动说明** 中分析 |

| 版式 | 波动金额默认 | Agent |
| --- | --- | --- |
| 标准 | link **TT**（符合 GAM/模板） | `volatility.amount_source=tt` |
| 简版 A | link **TE**（无 CRA 区） | `no_cra_te_volatility`；不跑 GAM TT 区间 |

### 规则映射

| 规则 ID | 检查内容 | M2 / M3 |
| --- | --- | --- |
| `lead_expectation_analysis` | 预期块存在；门槛金额/% 存在 | 块缺失 → `WARN`/`FAIL`；**不要求 7 行均有文字** |
| `lead_volatility_threshold_link`（待建） | 3.2 标准版波动金额 ≈ 整体 TT | 明显不等 → `WARN`；简版：波动金额 ≈ TE |
| AE-004（部分） | 3.3 超门槛 → Note + 波动说明 | 见模块 4、5 |
| （M3）预期 vs 实际变动 | 3.1 语义 | `NEED_REVIEW` + LLM |

---

## 模块 4：两期引导主表

**Ingest**：`movement_bindings`、`movement_rows`（原值/累计折旧/减值准备/净值 + 各列角色）。

### 业务检查点

| # | 检查点 | 说明 |
| --- | --- | --- |
| 4.1 | 四行完整 | 原值、累计折旧、减值准备、净值 |
| 4.2 | 列完整性 | 科目编码、科目名称、索引号、期末/期初、变动金额及比例、波动/定性调查列等 **均应有值**；**账表调整、审计调整** 仅在有调整时填列 |
| 4.3 | Notes 与调查列 | 波动或定性调查任一为「是」→ 须有 Notes 编号，且与 **模块 5** 一致（编号形式不限） |
| 4.4 | Check with A3 | **仅净值行**；\|Diff\|&lt;1 视为尾差 leave；\|Diff\|≥1 须有 Notes。**M2**：Lead 内 Check with A3 / Diff 行 vs 净值审定数列 |
| 4.5 | 变动额自洽 | 审定期末 − 上期审定 ≈ 变动金额（容差 0.01） |
| 4.6 | 与 K.01 后推 | 账面原值/累计折旧/减值准备取自后推 **TB-原值、TB-累计折旧、TB-减值准备**（公式链路）；须与后推一致 |

### 规则映射

| 规则 ID | 检查内容 | M2 |
| --- | --- | --- |
| `lead_movement_rows_complete`（待建） | 4.1、4.2 核心列 | 缺行/缺核心列 → `FAIL`/`WARN`；调整列条件必填 |
| `lead_movement_consistency`（待建） | 4.5 | 不自洽 → `FAIL`/`WARN` |
| `lead_movement_notes_required`（待建） | 4.3 | 调查=是但无 Notes → `FAIL`/`WARN` |
| `lead_check_with_a3_row` | 4.4 净值 | \|diff\|≥1 → `FAIL`；缺 Notes → `FAIL`；引导表 vs A3 不一致 → `WARN` |
| `lead_rollforward_tb_reconciliation`（待建） | 4.6 | 有 K.01 时比对 TB 列 → `FAIL`/`WARN` |
| GL-001 / GL-003 | 与外部 TB、上年审定 | 无 TB → 摘录 + `NEED_REVIEW` |
| （交叉）AE-003 | `sheet_ref` 索引号 ↔ 工作簿 sheet | 无匹配 → 沿用 PSP matcher |

---

## 模块 5：波动说明

**Ingest**：`fluctuation_notes`（自由文本区）。

### 业务检查点

| # | 检查点 | 说明 |
| --- | --- | --- |
| 5.1 | Notes 编号 | 与模块 4 主表 Notes **一致** |
| 5.2 | 变动说明 | 整体变动金额描述与 Lead 主表一致；展开分析可能需结合 K.01、FA list、新增/处置清单 |

### 规则映射

| 规则 ID | 检查内容 | M2 / M3 |
| --- | --- | --- |
| AE-004 `unexpected_movement_investigation` | 超门槛或调查=是时，说明非空；不得仅「无异常波动」 | M2：`FAIL`/`WARN` |
| `lead_fluctuation_notes_refs`（待建） | 5.1 编号在主表与说明区双向存在 | M2：弱检查（正则/集合包含） |
| （M3）说明充分性、跨表一致 | 5.2 | `NEED_REVIEW` + LLM |

checklist 的 `lead_exception_investigation` 与 AE-004 **合并为一个 rule_id**：`unexpected_movement_investigation`。

---

## 模块 6：调整汇总表

**Ingest**：`adjustment_rows`。

### 业务检查点

| # | 检查点 | 说明 |
| --- | --- | --- |
| 6.1 | 有调整时 | 与引导表、K.01 后推、程序索引一致；调整事项已执行程序或索引至其他底稿；与 A3A5 一致（**A3A5 未接入**） |
| 6.2 | 无调整时 | 可删除本表或注明无调整；**非必须程序** |

### 规则映射

| 规则 ID | 检查内容 | M2 / M3 |
| --- | --- | --- |
| MT-003 `adjustment_testing` | 6.1 恰当性 | M2：有调整行时摘录；M3/人工 |
| `lead_adjustment_presence`（待建） | 6.2 | 无调整且无说明 → `INFO`/`PASS`，不 FAIL |

---

## 规则 ID 总览

| 模块 | rule_id | dict_code | 状态 |
| --- | --- | --- | --- |
| 1 | `lead_required_fields` | — | 待实现 |
| 1 | `lead_analysis_date_after_period_end` | — | 待实现 |
| 1 | AE-001 `materiality_consistency` | AE-001 | 已实现 |
| 2 | AE-002 `risk_threshold_consistency` | AE-002 | 已实现（待增强简版跳过） |
| 2 | `lead_tt_overall_min` | — | 待实现 |
| 2 | `lead_tt_gam_range` | — | 待实现 |
| 3 | `lead_expectation_analysis` | — | 待实现 |
| 3 | `lead_volatility_threshold_link` | — | 待实现 |
| 4 | `lead_movement_*`、`lead_rollforward_tb_reconciliation`、`lead_check_with_a3_row` | GL-001/003 相关 | 已实现（GL-001 外部 TB 仍 manual） |
| 5 | AE-004 `unexpected_movement_investigation` | AE-004 | 待实现（部分逻辑） |
| 5 | `lead_fluctuation_notes_amount_consistency` | — | 待实现（SOP 易错） |
| 5 | `lead_arp_three_triggers` | — | 待实现（SOP【05】） |
| 6 | MT-003 `adjustment_testing` | MT-003 | 摘录为主 |
| 6 | `lead_adjustment_ref_classification` | — | 待实现（SOP【04】） |
| 1 | `lead_te_sad_finalization_note` | — | 待实现（SOP【01】） |
| 2 | `lead_tt_below_gam_lower` | — | 待实现（SOP 易错） |
| 3 | `lead_expectation_basis_present` | — | 待实现（SOP 易错） |
| 3 | `lead_disposal_expectation_vs_rollforward` | — | 待实现（SOP 进阶） |
| — | `lead_k03_cra_consistency`（交叉） | checklist `sap_cra_consistency` | 待实现 |

---

## FY26 SOP `K.00 Lead Sheet` 对照（K1.00-【01】～【05】）

对照资料：`固定资产质检agent/资料库/FY26_SOP K1 SWP 固定资产.xlsx`，指引列（约 C21/C23/C25）：基础操作指引、进阶实操提示、易错点。

| SOP 块 | 主题 | 与 `FA_lead规则说明` | 规划覆盖度 |
| --- | --- | --- | --- |
| 【01】 | 填列基本信息 | 一致 | 主干已覆盖；见下方遗漏 |
| 【02】 | CRA 与 TT（GAM） | 一致 | 主干已覆盖；见下方遗漏 |
| 【03】 | 设定预期 | 一致 | 结构 + M3；易错点部分遗漏 |
| 【04】 | 编制引导表 | 一致 | 主干已覆盖；调整分类遗漏 |
| 【05】 | ARP / 波动调查 | 一致 | 部分覆盖；三类触发与 Notes 金额遗漏 |

**已与 SOP 对齐较好的项**：六块 ingest、GAM TT 区间、TT=min(排除 0)、波动默认 TT/10%、超门槛 + Notes、Lead↔K.01 TB 列、Check with A3 行、调整列条件必填、无调整可删调整表。

### 【01】基准信息 — SOP 补充与遗漏

| SOP / 易错点 | 规划状态 | 建议 |
| --- | --- | --- |
| 审定 TE/SAD 与执行阶段比较并文字记录（四种情形） | **遗漏** | `lead_te_sad_finalization_note`：检测 NB/复核叙述；`manual_review` 附模板句 |
| TE/SAD 用错或未更新 | 无 Canvas 时摘录 | AE-001 + 上述叙述检查 |
| 客户名称、期末、币种未更新 | `lead_required_fields` | 已规划 |
| 分析日期「据实」vs 业务说明「须晚于期末」 | 见「待业务确认」 | **以业务说明为准**（> 期末），或中期底稿例外 |

### 【02】CRA / TT — SOP 补充与遗漏

| SOP / 易错点 | 规划状态 | 建议 |
| --- | --- | --- |
| TT 系数默认 GAM 区间**上限**；非上限须手改公式 | `lead_tt_gam_range` | 已规划（以上限为默认预期） |
| TT 可 **大于 TE**（GAM 2.2.2 例外） | **遗漏** | `NEED_REVIEW` 清单项，不自动 FAIL |
| TT 低于 GAM **下限**未按评估改底稿 | **遗漏** | `lead_tt_below_gam_lower` → `WARN` |
| Threshold 行：与未审数、审定数一致；与 **A5** 一致 | 部分（GL-001 摘录） | `lead_threshold_a3_*`、`lead_cra_a5_reconciliation`（待 A3/A5） |
| 整体 TT 用途：(a) 选总账账户测试起点 (b) 波动幅度起点 | 模块 3 波动 link TT | 已规划 |

### 【03】预期 — SOP 补充与遗漏

| SOP / 易错点 | 规划状态 | 建议 |
| --- | --- | --- |
| 未建立账户波动预期 | 空块 WARN | 可加强为 `FAIL`/`WARN` |
| 仅描述结果、无判断依据 | **遗漏** | `lead_expectation_basis_present`（弱规则）+ M3 |
| 处置预期与后推发生额不符（完整性风险） | **遗漏** | `lead_disposal_expectation_vs_rollforward`（有后推时） |

### 【04】引导主表 — SOP 补充与遗漏

| SOP / 易错点 | 规划状态 | 建议 |
| --- | --- | --- |
| 期末账面数 **公式 link K.01** | `lead_rollforward_tb_reconciliation` | 已规划 |
| 期初审定 = 上年底稿期末审定 | GL-003 摘录 | 待上年 Lead 输入 |
| 调整 AA#/RA#/CLA#/OA# 分类 | **遗漏** | `lead_adjustment_ref_classification` |
| 调整 Refer A5、与定稿 **A3A5 编号一致** | **遗漏** | 待 A3A5 ingest |
| 贴死数、调整无来源 | 难 AUTO | M3 / 人工 |

### 【05】ARP — SOP 补充与遗漏

| SOP / 易错点 | 规划状态 | 建议 |
| --- | --- | --- |
| 三类须调查：(1) 超门槛 (2) 定性异常 (3) **与预期矛盾** | 部分（仅 1） | `lead_arp_three_triggers` |
| BS：本期末 vs 上年末；PL：本期 vs 上期可比 | 固定资产以 BS 四行为主 | 写入 AE-004 规则说明 |
| Notes 金额与引导表不一致 | **遗漏** | `lead_fluctuation_notes_amount_consistency` |
| 达门槛未分析、Note 编号错误、性质异常未跟进 | AE-004 部分 | 合并进 AE-004 + 上项 |
| ARP 首句/无调查/有调查 **记录模板** | **遗漏** | `manual_review` 检查清单 |

### 跨 Lead 全局（SOP 总述 / 其他 sheet）

| 要求 | 规划状态 | 建议 |
| --- | --- | --- |
| SWP 与 **Canvas form** 程序一致 | 未写 Lead 专节 | 全局 AE / `workpaper_index` 类 NEED_REVIEW |
| 本指引仅适用固定资产 **重大账户** | 无法 AUTO | 报告备注 |
| **K.03 SAP CRA** 与 Lead 计价/计量认定 CRA 一致 | **遗漏** | `lead_k03_cra_consistency` / `sap_cra_consistency` |
| 汇总页拒绝程序须结合 Lead **预期**（如处置完整性） | **遗漏** | AE-003 × Lead 预期交叉 |
| K.03 **实体类型** link Lead 基础信息 | Lead 无 `entity_type` 字段 | 扩展 ingest 或交叉 K.03 |

### SOP 对照后的实施优先级（补充）

在「建议实施顺序」之前插入的 P1/P2 项：

| 优先级 | 待建 rule / 能力 |
| --- | --- |
| P1 | `lead_arp_three_triggers`、`lead_fluctuation_notes_amount_consistency`、`lead_adjustment_ref_classification` |
| P1 | `lead_te_sad_finalization_note` |
| P2 | `lead_tt_below_gam_lower`、`lead_expectation_basis_present`、`lead_disposal_expectation_vs_rollforward` |
| P2 | `lead_k03_cra_consistency`、TT>TE 例外 NEED_REVIEW |
| P3 | A5/A3A5 闭环、ARP 模板句、Canvas form 一致 |

---

## 外部输入依赖

| 外部数据 | 影响模块 | M2 策略 |
| --- | --- | --- |
| Canvas / A3 最终 TE/SAD/GAAP/币种 | 1 | 摘录 + NEED_REVIEW |
| 项目组 CRA 表 | 2 | GAM 区间 + NEED_REVIEW |
| 试算表 TB | 4、GL-001 | NEED_REVIEW |
| 上年 Lead / 审定 | 4、GL-003 | NEED_REVIEW |
| K.01 后推 | 4、6 | 数值勾稽 AUTO |
| A3A5 | 6 | 待接入 |
| FA list / 新增 / 处置 | 5 | M3 LLM |

---

## 报告交付

- **`lead_sheet_section`**：块边界、`layout_variant`、`volatility_amount_source`、各模块摘录、Lead findings 汇总（对称 `summary_sheet_section`）。
- **`manual_review_sections`**：扩展 AE-001/002、GL-001/003、CRA/TT 待核表、AE-004 待核项。
- **底稿标注**（终态）：finding 回写至对应块锚点单元格（未开始）。

---

## 建议实施顺序

1. **模块 1**：`lead_required_fields`、`lead_analysis_date_after_period_end`；理顺 AE-001  
2. **报告**：`lead_sheet_section` + `pipeline` 注册  
3. **模块 2**：AE-002 简版跳过；`lead_tt_overall_min`、`lead_tt_gam_range`（需 CRA↔GAM 映射表）  
4. **模块 3–4**：`lead_expectation_analysis`、`lead_volatility_threshold_link`；`lead_movement_*`、`lead_rollforward_tb_reconciliation`  
5. **模块 5**：AE-004 确定性子集 + Notes 弱检查  
6. **模块 6**：调整摘录 + 有/无调整分支  
7. **M3**：预期一致性、波动说明充分性、调整恰当性  

---

## 待业务确认

| 项 | 选项 |
| --- | --- |
| 无 Lead 表 | `FAIL`（程序缺失）vs `NEED_REVIEW`（sheet 未识别） |
| 超门槛未调查 / 调查=是无说明 | `FAIL` vs `WARN` |
| GAM 区间偏离 | 仅 `WARN` vs `FAIL` |
| PM 是否纳入 `lead_required_fields` FAIL | 当前：否，走 AE-001 |
| 分析日期口径 | SOP「据实」vs 业务说明「> 期末」：**默认采用业务说明**；中期底稿是否例外待确认 |

---

## 相关文件

- SOP 底稿：`固定资产质检agent/资料库/FY26_SOP K1 SWP 固定资产.xlsx` → sheet `K.00 Lead Sheet`（资料库路径，非 git 跟踪）
- 业务原文：`固定资产质检agent/FA_lead规则说明.txt`（桌面资料库，非 git 跟踪）
- 阅读笔记摘录：`docs/source-materials-reading-notes.md` § K.00 Lead Sheet
- `docs/workpaper-fields.md` § K.00、`docs/qc-checklist.md` §二  
- `src/ingest/lead_sheet_blocks.py`、`src/ingest/lead_sheet.py`  
- `src/rules/materiality_consistency.py`、`risk_threshold_consistency.py`  
- `tests/ingest/test_lead_sheet.py`

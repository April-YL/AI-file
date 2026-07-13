# 质检规则字典映射

本文将桌面《固定资产质检规则字典》与 Agent 开发框架对齐。脱敏副本见：

- `tests/fixtures/rule_dictionary_sanitized.csv` — 35 条规则主表
- `tests/fixtures/rule_dictionary_priority_sanitized.csv` — 人工实施优先级

代码注册表：`src/rules/registry.py`（`RuleSpec` + `get_by_rule_id` / `get_by_dict_code`）。

## 两套优先级

| 轨道 | 来源 | 用途 |
| --- | --- | --- |
| **人工质检** | 字典 sheet「实施优先级」 | 交付复核员检查顺序 |
| **Agent 开发** | 下表 `agent_priority` | `src/rules` 实现与单测排期 |

### Agent 开发阶段（当前 P1 = M2a）

| 阶段 | 目标 | 规则/模块优先 |
| --- | --- | --- |
| **M2a（P1，进行中）** | 整底稿流水线 + 报告 + 标注副本 | **AE-003**（汇总 PSP）、**K.01**（`rollforward_*`）、`fa-qc-run`、多 sheet ingest |
| M2b（P2） | K.02 新增/处置、折旧逻辑、跨表一致性 | SP/AT/DT、DP 系列 |
| M3+（P3/P4） | Canvas/TB、证据充分性等 | AE-001/002、AT-002 等 → `NEED_REVIEW` 为主 |

**不以** FA list 规则条数扩张为 P1 主线。`FA-RC-*`（`fa_list_*`）在 M1 已实现，供客户台账或清单与 K.01 核对时**复用**。

**不以** 字典人工实施优先级 sheet（AE-001、GL-001 等）作为 Agent 代码排期依据。

## 严重程度映射

| 字典「严重程度」 | Agent `severity`（能实现时） |
| --- | --- |
| 重大缺陷 | `FAIL` 或 `NEED_REVIEW` |
| 一般缺陷 | `WARN` 或 `NEED_REVIEW` |
| 建议优化 | `WARN` 或报告备注 |

| 字典「QC Checkpoint」 | `automation` |
| --- | --- |
| Y-影响程序范围、证据程度 / Y-审计基础程序 / Y-错报风险 等 | 视具体规则：`AUTO_*` 或 `REVIEW` |
| No-考虑到影响不重要 / No-非PSP程序要求 | 通常 `MANUAL_ONLY` |

## 完整映射表

`FA-RC-*` 为 `docs/qc-checklist.md` 补充项（字典主表待增行）。

| dict_code | rule_id | 规则名称 | procedure | agent_priority | automation | implementation |
| --- | --- | --- | --- | --- | --- | --- |
| AE-001 | materiality_consistency | PM/TE/SAD一致性 | K.00 | P4 | REVIEW | manual_only |
| AE-002 | risk_threshold_consistency | 各认定CRA正确性 | K.00 | P4 | REVIEW | manual_only |
| AE-003 | psp_completion | PSP程序执行完整性 | SUMMARY | P3 | REVIEW | **implemented** |
| AE-004 | unexpected_movement_investigation | 异常波动调查充分性 | K.00 | P4 | REVIEW | manual_only |
| AE-005 | workpaper_cleanliness | 底稿清洁度 | GLOBAL | MANUAL | MANUAL_ONLY | manual_only |
| AE-006 | workpaper_index_accuracy | 底稿索引准确性 | GLOBAL | MANUAL | MANUAL_ONLY | manual_only |
| MT-001 | fixed_asset_definition | 固定资产定义符合性 | FA_LIST | P4 | REVIEW | manual_only |
| MT-002 | special_movement_identification | 特殊性质变动识别 | K.02 | P4 | REVIEW | manual_only |
| MT-003 | adjustment_testing | 调整事项测试恰当性 | K.00 | MANUAL | MANUAL_ONLY | manual_only |
| GL-001 | lead_tb_reconciliation | 期末账面数与TB核对 | K.00 | P4 | REVIEW | manual_only |
| GL-002 | rollforward_fa_list_reconciliation | 期末账面数与FA list核对 | K.01 | **P1** | REVIEW | **implemented（主检查：K.01 表3 check；差异=0或≤SAD通过，>SAD 无 Notes → FAIL；表2 SUMIF 辅助；自算合计仅兜底）** |
| GL-003 | lead_prior_year_reconciliation | 期初期末审定数与Lead核对 | K.00 | P4 | REVIEW | manual_only |
| GL-004 | rollforward_depreciation_pl_reconciliation | 折旧费用与利润表/TB核对 | K.01 | **P1** | REVIEW | **implemented**（主检查：K.01 表4差异；差异=0或≤SAD通过，>SAD 无 Notes → FAIL；表4读不到差异或SAD读不到 → NEED_REVIEW） |
| GL-005 | rollforward_abnormal_amounts | 后推表异常金额（累折>原值、负净值、处置转出） | **K.01** | **P1** | AUTO_FAIL/WARN | **implemented**（procedure 以 K.01 为准，见 [planning/k01-qc-rules.md](planning/k01-qc-rules.md)） |
| GL-006 | rollforward_exists | 后推明细表存在 | K.01 | **P1** | AUTO_FAIL | **implemented**（qc-checklist §三；字典主表待增行） |
| GL-007 | rollforward_columns_complete | 后推金额列完整（M2a=L1） | K.01 | **P1** | AUTO_FAIL | **implemented**（L2 矩阵见 [planning/k01-workpaper-layouts.md](planning/k01-workpaper-layouts.md)） |
| GL-008 | rollforward_difference_over_sad | K.01 TB差异超过SAD调查 | K.01 | **P1** | AUTO_WARN/REVIEW | **implemented**（TB check 差异>SAD 且无 Notes → FAIL；有 Notes → NEED_REVIEW） |
| FA-RC-001 | fa_list_required_fields | FA list 必需字段完整 | FA_LIST | **P1** | AUTO_FAIL | **implemented** |
| FA-RC-002 | unique_asset_id | 资产编号唯一 | FA_LIST | **P1** | AUTO_FAIL | **implemented** |
| FA-RC-003 | asset_value_consistency | 金额勾稽一致 | FA_LIST | **P1** | AUTO_FAIL | **implemented** |
| FA-RC-004 | asset_amount_non_negative | 金额非负 | FA_LIST | **P1** | AUTO_FAIL | planned |
| FA-RC-005 | useful_life_positive | 使用寿命为正 | FA_LIST | **P1** | AUTO_FAIL | planned |
| FA-RC-006 | salvage_rate_range | 残值率区间合理 | FA_LIST | **P1** | AUTO_FAIL | planned |
| FA-RC-007 | asset_start_date_reasonable | 入账日期合理 | FA_LIST | P2 | AUTO_WARN | planned |
| SP-001 | addition_population_homogeneity | 交易类别区分 | K.02.1 | P3 | REVIEW | planned |
| SP-002 | addition_rollforward_reconciliation | 样本池与BKD一致性 | K.02.1 | P3 | AUTO_WARN | planned |
| SP-003 | sampling_parameters | 抽样工具参数设置 | K.02.1 | MANUAL | MANUAL_ONLY | manual_only |
| SP-004 | key_item_selection | 关键项选取恰当性 | K.02.1 | P3 | REVIEW | planned |
| AT-001 | addition_sample_match | 测试样本与抽样输出一致 | K.02.1 | P3 | REVIEW | planned |
| AT-002 | addition_supporting_documentation | 支持性文件充分性 | K.02.1 | P4 | REVIEW | manual_only |
| AT-003 | addition_special_nature_testing | 特殊性质新增测试 | K.02.1 | P4 | REVIEW | manual_only |
| AT-004 | addition_exception_followup | 例外情况跟进记录 | K.02.1 | P3 | REVIEW | planned |
| DT-001 | disposal_sample_match | 测试样本与抽样输出一致 | K.02.2 | P3 | REVIEW | planned |
| DT-002 | disposal_supporting_documentation | 支持性文件充分性 | K.02.2 | P4 | REVIEW | manual_only |
| DT-003 | disposal_special_nature_testing | 特殊性质减少测试 | K.02.2 | P4 | REVIEW | manual_only |
| DT-004 | disposal_exception_followup | 例外情况跟进记录 | K.02.2 | P3 | REVIEW | planned |
| DP-001 | depreciation_policy_change | 折旧政策变化识别 | K.03.3 | P4 | REVIEW | manual_only |
| DP-CTRL-001 | k03_program_execution_consistency | K.03 汇总勾选与实际执行一致性 | K.03 | P1 | REVIEW | **implemented**（逐项比较 K.03.1/K.03.2/K.03.3；政策独立，不以 SAP/TOD 替代） |
| DP-CTRL-002 | k03_depreciation_path_identified | K.03 折旧测试执行路径已识别 | K.03 | P1 | REVIEW | **implemented**（汇总选择执行时，只认状态为 `EXECUTED` 的 SAP/TOD 主程序组件） |
| DP-CTRL-003 | k03_path_combination_consistency | K.03 折旧测试路径组合一致性 | K.03 | P1 | REVIEW | **implemented**（允许一条 SAP + 一条 TOD；双 SAP、双 TOD、同角色重复执行转人工复核） |
| DP-002 | depreciation_policy_list_consistency | 折旧政策与清单一致性 | K.03.3 | P3 | REVIEW | planned |
| DP-003 | sap_precision_selection | 折旧测试策略恰当性 | K.03.1 | P3 | REVIEW | **implemented**（部分覆盖：CRA/TE/中高精度路径/TOD补充识别；证据充分性仍需人工判断） |
| DP-SAP-001 | sap_te_consistency | SAP 可容忍误差与 Lead 一致性 | K.03.1 | P3 | AUTO_FAIL | **implemented**（DP-003 的 Agent 可执行子规则；SAP TE 与 Lead TE 明确不一致时 FAIL） |
| DP-SAP-002 | sap_high_cra_consistency | 高精度 SAP CRA 与 Lead V/M 一致性 | K.03.1 | P3 | AUTO_FAIL | **implemented**（DP-003 的 Agent 可执行子规则；仅适用于高精度 SAP，明确不一致时 FAIL） |
| DP-004 | sap_depreciation_difference | SAP折旧测试差异处理（基础） | K.03.1 | P3 | REVIEW | **implemented**（识别预期构建说明和偏差测试区域；逐类别偏差说明见 DP-SAP-003/004） |
| DP-SAP-003 | sap_medium_category_deviation_explanation | 中精度 SAP 类别及合计偏差说明 | K.03.1 | P3 | REVIEW | **implemented**（逐类别及合计比较偏差阈值；超阈值时检查同列 Notes 索引和正文，充分性人工复核） |
| DP-SAP-004 | sap_high_category_deviation_explanation | 高精度 SAP 类别偏差说明 | K.03.1 | P3 | REVIEW | **implemented**（逐类别比较差异和已分配偏差阈值；超阈值时检查对应 Notes 正文，充分性人工复核） |
| DP-005 | depreciation_by_item_sad | By Item折旧测试差异 | K.03.2 | P3 | AUTO_WARN | planned |
| DP-006 | depreciation_tod_sampling | TOD抽样折旧测试抽样过程 | K.03.2 | P3 | REVIEW | **implemented**（部分覆盖：总体、关键项目、K.03.2a选样输出参数；抽样设计充分性仍需人工判断） |
| DP-007 | depreciation_tod_difference | TOD抽样折旧测试差异 | K.03.2 | P3 | REVIEW | **implemented**（部分覆盖：样本明细和结论是否存在；差异调查质量仍需人工判断） |
| DP-TOD-PRE-001 | k03_tod_sampling_output_required | TOD抽样选样输出配套 | K.03.2 | P3 | REVIEW | **implemented**（DP-006 子规则） |
| DP-TOD-001 | k03_tod_sampling_currency | TOD抽样货币单元 | K.03.2 | P3 | AUTO_FAIL | **implemented**（DP-006 子规则） |
| DP-TOD-002 | k03_tod_sampling_te_consistency | TOD选样TE与Lead一致性 | K.03.2 | P3 | AUTO_FAIL | **implemented**（DP-006 子规则） |
| DP-TOD-003 | k03_tod_sampling_population_reconciliation | TOD总体与K.01勾稽 | K.03.2 | P3 | AUTO_FAIL/REVIEW | **implemented**（DP-006 子规则；SAD缺失不执行阈值结论） |
| DP-TOD-004 | k03_tod_sampling_count_consistency | TOD选样数量一致性 | K.03.2 | P3 | AUTO_FAIL | **implemented**（DP-006 子规则） |
| DP-TOD-005 | k03_tod_sampling_identity_consistency | TOD样本编号一致性 | K.03.2 | P3 | AUTO_FAIL/REVIEW | **implemented**（DP-006 子规则；替换样本单独复核） |
| DP-TOD-006 | k03_tod_sampling_attributes | TOD样本测试属性完整性 | K.03.2 | P3 | REVIEW | **implemented**（DP-007 子规则） |
| DP-TOD-007 | k03_tod_sampling_difference_followup | TOD样本差异跟进 | K.03.2 | P3 | AUTO_FAIL/REVIEW | **implemented**（DP-007 子规则） |
| DP-TOD-008 | k03_tod_sampling_documentation | TOD关键项目依据与结论 | K.03.2 | P3 | REVIEW | **implemented**（DP-007 子规则） |
| DL-001 | first_delivery_standard | 首次交付标准 | GLOBAL | MANUAL | MANUAL_ONLY | manual_only |
| DL-002 | final_delivery_standard | 整体交付标准 | GLOBAL | MANUAL | MANUAL_ONLY | manual_only |

## QcIssue 扩展字段

`src/rules/models.py` 中 `QcIssue` 在原有字段基础上增加（由 `registry.attach_rule_metadata` 填充）：

| 字段 | 含义 |
| --- | --- |
| `dict_rule_code` | 字典编号，如 `AE-001`、`FA-RC-001` |
| `rule_name` | 字典规则名称 |
| `problem_category` | 问题分类（底稿范围、基础程序、错报、交付风险） |
| `reviewer_role` | `preparer` / `reviewer` |
| `qc_checkpoint` | 字典 QC Checkpoint 原文 |
| `automation_level` | `AUTO_FAIL` / `AUTO_WARN` / `REVIEW` / `MANUAL_ONLY` |
| `k1_checklist_ref` | K1 来源行 |

JSON 报告 `to_dict()` 仅输出非空扩展字段。

## 字典修订建议（维护桌面 xlsx 时）

1. **增行**：`FA-RC-001`～`007` 与上表一致，避免 Agent 规则无字典编号。
2. **AT-002 / DT-002**：判定条件与 K1（12/5）同步——合同/控制权转移单据**不强制编号**。
3. **K.03 映射维护**：`DP-CTRL-001`～`DP-CTRL-003` 负责执行路径与程序总控，只读取汇总页与 `K03ExecutionProfile`，不得重新扫描工作表或把模板页视为已执行。`DP-003`、`DP-004`、`DP-006`、`DP-007` 已纳入主 runner，但仍应标注“部分覆盖 + 人工复核边界”，不得写成审计判断全自动通过。`DP-SAP-001`～`DP-SAP-004` 是从 `DP-003/DP-004` 拆出的 Agent 可执行子规则，不作为原始 35 条来源字典的新行写入脱敏 CSV。
4. **检查字段/单元格**：改为语义字段（`te`、`sad`），避免写死 `B5:B6`。

## 开发用法

```python
from rules.registry import get_by_rule_id, attach_rule_metadata
from rules.runner import run_fa_list_rules

spec = get_by_rule_id("fa_list_required_fields")
# spec.dict_code -> "FA-RC-001"

issues = run_fa_list_rules(records, ctx)  # 已自动 attach_rule_metadata
assert issues[0].dict_rule_code == "FA-RC-001"
```

## 相关文档

- [qc-checklist.md](qc-checklist.md) — Agent 可自动化检查点
- [architecture.md](architecture.md) — 模块与 finding 结构
- [workpaper-fields.md](workpaper-fields.md) — 标准字段与 sheet 口径

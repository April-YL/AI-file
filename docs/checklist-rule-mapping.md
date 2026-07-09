# K1 Checklist 与 Agent Rule 映射表

## 文件位置

正式映射工作簿：`固定资产质检agent/资料库/K1 check list_rule_mapping.xlsx`

当前最新工作表：`规则映射v0.5_K03更新`

历史与对照工作表：

- `规则映射v0.2`：初版映射与复核意见来源。
- `规则映射v0.3修正版`：按业务复核意见修正后的版本。
- `规则映射v0.4编号补全版`：编号补全后的历史版本。
- `规则映射v0.5_K03更新`：同步 K.03 SAP 与 TOD 抽样第一阶段规则状态。
- `当前规则能力目录_v2`：同步 K.03 SAP 与 TOD 抽样第一阶段规则状态后的当前能力目录。
- `映射口径说明`：生成和分类口径说明。
- `Checklist FY26-K`：原始 K1 checklist 对照。

## 映射口径

该工作簿用于把质检人员熟悉的 K1 checklist 检查点，对应到当前 Agent 实际 runner、pipeline 和 registry 中的规则。

一条 checklist 检查描述可以对应多条实际 rules。映射表按“一条实际 rule 一行”展开，便于筛选、统计和后续维护。

`规则编号` 是面向业务和报告展示的正式编号，例如 `AE-003`、`GL-002`、`DP-BI-001`。

`内部rule_key` 是系统内部定位键，例如 `psp_completion`、`rollforward_fa_list_reconciliation`。开发排查代码时用内部 key，质检沟通时优先看规则编号。

映射必须基于当前实际情况，不得把规划项、人工复核项或未来目标写成当前已覆盖。

## 主要列说明

| 列名 | 说明 |
| --- | --- |
| `规则来源类型` | 区分当前主 runner 规则、LLM 条件产生规则、注册表存在但当前 runner 未纳入、模块总述行等。 |
| `Agent覆盖结论` | 当前实际能力边界，如已覆盖、部分覆盖、需人工复核、暂未覆盖。 |
| `自动化程度（基于当前实际rules）` | 只描述当前规则实际能做到什么，不描述未来预期形态。 |
| `是否纳入当前runner` | 标识当前主流程是否会执行，或是否依赖 LLM、delivery_context 等条件触发。 |
| `当前缺口说明` | 说明当前尚未覆盖、只部分覆盖或需要人工判断的原因。 |

## 当前状态

`规则映射v0.4编号补全版` 已补齐此前映射表中的 `未登记字典编号`，并在 2026-06-24 复核后从 102 行更新为 110 行。

`规则映射v0.5_K03更新` 已同步 2026-07-09 K.03 第一阶段开发结果：`DP-003`、`DP-004`、`DP-006`、`DP-007` 已由“注册表存在但当前 runner 未纳入”更新为“当前主 runner 规则”。本轮只更新映射口径和能力目录，不改变规则代码、severity 或 finding 判断逻辑。

当前已在 `src/rules/registry.py` 中补充登记：

- `AT-LLM-001`：新增测试语义复核。
- `DP-BI-PRE-001` 至 `DP-BI-PRE-004`：K.03 by-item 折旧测试前置读取、字段、差异列和 SAD 参数规则。
- `DP-BI-001` 至 `DP-BI-004`：K.03 by-item 折旧测试相关规则。
- `DP-POL-PRE-001` 至 `DP-POL-PRE-002`：K.03 折旧政策复核前置读取规则。
- `DP-POL-001` 至 `DP-POL-007`：K.03 折旧政策复核相关规则。
- `DP-003`、`DP-004`：K.03.1 SAP 折旧测试策略与差异处理规则。
- `DP-006`、`DP-007`：K.03.2 TOD 抽样过程与差异/结论规则。

这些登记只补规则元数据和正式编号，不改变 runner、pipeline、severity 或 finding 判断逻辑。

本轮同步修复了映射表复核意见中的疑问口径：

- `MT-002 / special_movement_identification`：明确当前主 runner 未纳入，减少侧仅由处置相关规则部分覆盖，尚未形成完整特殊减少识别规则。
- `GL-003 / lead_prior_year_reconciliation`：明确该点与 LEAD-010/LEAD-011 及 K.01/A3 勾稽存在重叠，当前不作为独立 runner 规则执行。

后续补规则时，优先关注映射表中：

- `注册表存在但当前runner未纳入`
- `暂未覆盖`
- `需人工复核`
- `当前缺口说明` 中标注 rules 不完整的事项

## 维护规则

新增或调整 rule 时，应同步维护：

1. `src/rules/registry.py` 中的 `RuleSpec`。
2. `tests/rules/test_registry.py` 或对应规则测试。
3. `K1 check list_rule_mapping.xlsx` 中最新映射工作表。

不要把 `PLANNED`、`MANUAL_ONLY` 或仅存在于注册表但未进入当前 runner 的规则写成当前已覆盖。

LLM 条件产生规则必须单独标识为 `LLM条件产生规则` 或 `LLM辅助提示`，不得写成确定性自动判断。

K.03 by-item 折旧测试与 TOD-抽样折旧测试必须区分。by-item 规则不得误挂到 TOD-抽样 checklist 行。

K.03 SAP 与 TOD 抽样第一阶段规则均属于“部分覆盖”：系统可检查路径、参数、差异结果、说明/结论是否存在或明显异常；但审计证据是否充分恰当、差异说明是否足够支持结论，仍需质检人员人工复核。

如果更新映射表，建议保留历史 sheet，或在新 sheet 名称中标注版本和变更目的。

## 验收方式

注册表编号校验：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\rules\test_registry.py -q
```

映射表人工检查建议：

1. 打开 `K1 check list_rule_mapping.xlsx`。
2. 查看 `规则映射v0.5_K03更新`。
3. 筛选 `规则来源类型`，确认主 runner、LLM 条件、注册表未纳入项是否合理。
4. 筛选 `Agent覆盖结论`，重点检查 `暂未覆盖`、`需人工复核`、`部分覆盖`。
5. 筛选 `是否纳入当前runner`，确认条件触发规则没有被误解为无条件执行。

## 后续建议

开发新 rule 前，先查看该映射表，确认对应 checklist 行、现有规则、当前缺口和自动化边界。

当某个 checklist 点从人工复核或部分覆盖推进为规则覆盖时，应同步更新映射表中的覆盖结论、自动化程度、执行条件和缺口说明。

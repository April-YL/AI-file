# K.01 后推底稿版式（Layout Profile）

> **用途**：约定 ingest 与规则所识别的 K.01 物理版式；避免将「案例库简表」与「SOP 标准 BKD 矩阵」混为同一套列完整标准。  
> **关联**：[k01-qc-rules.md](./k01-qc-rules.md)、[workpaper-fields.md](../workpaper-fields.md) § K.01、[domain-glossary.md](../domain-glossary.md)。

## 背景

固定资产 K.01（Agree SL to GL / 后推明细表）在资料库与案例库中存在 **多种合法版式**：

| 来源 | 典型特征 |
| --- | --- |
| `FY26_SOP K1 SWP 固定资产.xlsx` → `K.01 Agree SL to GL` | **表1** 按资产类别列展开；原值/累折/减值/净值各含多行交易（年初余额、购置、处置…）；每格常为 **账面数 \| 账表调整/审计调整 \| 审定数**；另有 **表2/表3/表4** |
| 案例库 B–G（20251231） | 上部 **变动/TB 勾稽区** + 下部 **类别两期对比**（审2/审3 或表2/表3）；表头常无「期初/期末」字样 |

Agent **M2a** 以 `category_dual_period` / `hybrid` 为主验收；`sop_bkd_matrix` 为 **P1+** 扩展目标。

---

## Layout Profile 枚举

| Profile ID | 名称 | 识别特征（任一组合即可倾向） | 案例库 |
| --- | --- | --- | --- |
| `sop_bkd_matrix` | SOP 标准 BKD（表1 矩阵） | 含「表1」；行标签含购置/计提/处置或报废/年初余额/年末余额；列组为 **账面数、账表调整/审计调整、审定数** | SOP 模板 |
| `category_dual_period` | 类别两期对比 | 「固定资产类别」+ 并列两组原值/累折/减值/净值；上一行含 **审2/审3** 或 **表2/表3**、check with | B–G 下部主表 |
| `hybrid` | 混合 | 同时存在变动金额行（原值变动金额…）、TB-原值/差异行 **与** 类别两期表 | **B–G 常见** |
| `unrecognized` | 未识别 | 无上述锚点或仅有说明文字 | 需 `NEED_REVIEW` |

**判定优先级（ingest 规划）**：`sop_bkd_matrix` > `hybrid` > `category_dual_period` > `unrecognized`（实现时写入 `RollforwardSheetDataset.layout_profile`）。

---

## 表段与锚点（各 Profile）

### `sop_bkd_matrix` — 表1–4

| 表段 | 锚点/行标签 | Agent 用途 |
| --- | --- | --- |
| 表1 BKD | `表1`、`固定资产类别`、原值/累计折旧/减值准备/净值 (NBV) | 列完整性 L2、交易行、调整列 |
| 变动摘要 | `变动`、`原值变动金额` | movement 信号、同比 |
| TB 勾稽 | `TB-原值`、`TB-累计折旧`、`差异` | 与 Lead / 试算表核对（M2b） |
| 表2/表3 | `表2`、`表3`、`表2 check with 表1` | FA list 汇总核对 |
| 表4 | `折旧费用与利润表科目核对` | 折旧 ↔ PL（P1，多为摘录） |
| Notes | `Notes`、`请在此记录…差异` | >SAD 调查记录（P1） |

**填列口径（SOP）**：原值/累折/减值为 **正数列示**；本期减少以 **负数** 填列；账表调整、审计调整 **公式链接 K.00 Lead**。

### `category_dual_period` / `hybrid` — 案例库简表

| 表段 | 锚点 | Agent 用途 |
| --- | --- | --- |
| 变动区（hybrid） | `变动`、`原值变动金额`、`TB-` | movement + TB 勾稽 |
| 类别表 | `固定资产类别`、合计行 | `ending_totals` / `opening_totals` |
| 时期标签 | 上一行：`审2`/`审3`、`表2`/`表3` | 列 `period_role` → opening/ending |

---

## 列完整性：L1 与 L2

对外 checklist 规则 ID 均为 `rollforward_columns_complete`；实现与验收按 **级别** 区分。

### L1 — M2a 最小（`category_dual_period` / `hybrid`）

| 项 | 要求 |
| --- | --- |
| 四口径 | `original_value`、`accumulated_depreciation`、`impairment_provision`、`net_value` 均在 `amount_column_bindings` 或合计行 `ending_totals` 中出现 |
| 期初 | 至少一种：`opening` 列绑定，或 `opening_totals` 有值，或时期标签映射为期初列块（审2/表2/年初余额） |
| 期末 | 至少一种：`ending` 列绑定，或 `ending_totals` 有值，或审3/表3/年末余额 |
| 变动 | 至少一种：`movement` 列绑定，或表内存在变动金额/购置/计提/处置类 **行标签**（不要求矩阵全部交易行） |
| 减值 | 列须 **存在**；金额可为 0 |

**不满足** → `FAIL`（`AUTO_FAIL`）。

### L2 — SOP 完整（`sop_bkd_matrix`，P1+）

| 项 | 要求 |
| --- | --- |
| 四口径 × 交易行 | 每口径具备 SOP 预设交易行集合（年初/年末余额及主要增减类；`[…]` 可空） |
| 三子列 | 每活跃交易格具备 **账面数、账表调整/审计调整、审定数** 列角色（或等价公式列） |
| 调整列 | 有调整时须与 Lead 过账一致（另规则 `rollforward_adjustment_link_lead`，P1） |
| 符号 | 减少类交易以负数列示（另规则扩展 `rollforward_sign_convention`） |

**M2a 不实现 L2 全量**；检测到 `sop_bkd_matrix` 且仅满足 L1 时，可 `WARN`「矩阵版式待增强 ingest」或 `NEED_REVIEW`。

---

## Ingest 契约（`RollforwardSheetDataset`）

| 字段 | 含义 | 各 Profile 填充预期 |
| --- | --- | --- |
| `layout_profile` | 上表枚举 | 必填（实现后） |
| `amount_column_bindings` | 口径 × 时期 × 列号 | hybrid：≥8 列常见；须逐步消除全 `unknown` |
| `opening_totals` / `ending_totals` | 合计行四口径 | 至少 `ending` 有值（案例库已满足） |
| `header_row` / `total_row` | 主表定位 | 案例库 header≈54、total≈61–63 |
| `notes` | 解析路径 | 如 `totals_from_period_bindings`、`ending_from_total_row` |

**ingest 增强（M2a P0，见 handoff）**：

1. 多行表头：header 上一行 `审2/审3` → 列块 `opening`/`ending`。  
2. 变动 token：`变动金额`、`变动比例`、行标签购置/计提/处置。  
3. 多 sheet：多候选 K.01 时优先 **无 `-24` 后缀** 的当年表。  
4. （P1）扫描表1 矩阵区，填充 L2 绑定。

---

## 不宜 M2a 全自动（标 `manual_only` / `NEED_REVIEW`）

| 主题 | SOP 出处 | 原因 |
| --- | --- | --- |
| 期初滚调三种情形 | 【01】进阶 | 需上年 TB/JE 与职业判断 |
| 表4 折旧 ↔ PL 分摊合理性 | 【02】进阶 | 首年/资本化/多受益对象 |
| 特殊交易另册（合并、持有待售、减值 SWP） | 【03】进阶 | 程序不在标准 K.01 PSP 内 |
| 与 A3/Canvas 最终 TE/SAD 一致 | 交叉 Lead | 外部系统未接入 |
| FA list 分类差异仅披露影响 | 【02】进阶 | EIC/PIC 判断 |

---

## 案例库实测摘要（B–G，2026-05）

| 项 | 结果 |
| --- | --- |
| Sheet | `K.01 Agree SL to GL`（C/D 另有 `-24`） |
| Profile（规划） | `hybrid` |
| bindings | 8 列、四口径；`period_role` 曾为全 `unknown`（待 ingest 修复） |
| ending_totals | 有；opening 待修复后应有 |

回归建议：`tests/ingest/test_case_rollforward_regression.py` 或扩展现有 case 测试，锁定 profile + bindings 数量。

---

## 相关文件

- `src/ingest/rollforward_sheet.py`
- `docs/planning/k01-qc-rules.md`
- `artifacts/_k01_sop_guidance.txt`（SOP 指引摘录，可选本地生成）

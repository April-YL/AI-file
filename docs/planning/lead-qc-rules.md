# K.00 Lead Sheet 质检规则规划

> 2026-05-20 与产品/业务对齐的讨论纪要。实现前以本文 + `docs/qc-checklist.md` + `docs/workpaper-fields.md` 为准。

## 背景

- **Ingest 已就绪**：`lead_sheet_blocks.py` 锚点分块（6 块，不依赖固定行号）→ `LeadSheetDataset`。
- **已有规则**：AE-001 `materiality_consistency`、AE-002 `risk_threshold_consistency`（摘录 + `NEED_REVIEW`）。
- **版式变体**：`layout_variant=no_cra_te_volatility`（案例 A）：无 CRA/TT 区，波动幅度金额 link **TE**（已人工确认）。

## Lead 逻辑模块与规则映射

| 模块 | Ingest 字段 | 规则 ID | 自动化 | M2 实现策略 |
| --- | --- | --- | --- | --- |
| 基础信息 | `basic_info_fields`, `materiality` | `lead_required_fields` | AUTO_FAIL | 缺必填 → FAIL；与 AE-001 分工（AE-001 仅 Canvas 核对） |
| 基础信息 | 同上 | AE-001 | REVIEW | 有 TE/SAD/PM 后摘录 → NEED_REVIEW |
| CRA/TT | `cra_rows` | AE-002 | REVIEW | 标准版摘录；简版 **跳过** CRA WARN |
| 预期 + 波动门槛 | `expectations`, `volatility` | `lead_expectation_analysis` | REVIEW | 结构：空行/缺门槛 WARN；语义 NEED_REVIEW |
| 两期引导主表 | `movement_rows`, `movement_bindings` | GL-001, GL-003 | REVIEW | M2 摘录 + NEED_REVIEW（无 TB 输入） |
| 两期引导主表 | 同上 | 内部勾稽（待建） | AUTO | 变动额自洽、Lead↔K.01 期末（有后推时） |
| 两期引导主表 | `sheet_ref` | 交叉 AE-003 | AUTO | 索引号 ↔ 工作簿 sheet 名匹配 |
| 波动说明 | `fluctuation_notes` + 主表调查列 | AE-004 `unexpected_movement_investigation` | 部分 AUTO | 超门槛未调查 → FAIL/WARN；说明充分性 NEED_REVIEW |
| 调整汇总 | `adjustment_rows` | MT-003 | MANUAL | M2 仅摘录 |

checklist 中的 `lead_exception_investigation` 与 AE-004 业务重叠，**建议合并为一个 rule_id**（`unexpected_movement_investigation`）。

## 必填字段（`lead_required_fields`）

与 checklist §二一致：

- `client_name`, `period_end`, `analysis_date`, `te`, `sad`, `gaap`, `currency`
- **PM** 仍由 AE-001 处理，不纳入 AUTO_FAIL 清单（除非后续变更）。

## 报告交付

- 新增 `lead_sheet_section`（对称 `summary_sheet_section`）：块边界、版式、`layout_variant`、`volatility_amount_source`、摘录表、Lead 规则 findings 汇总。
- 扩展 `manual_review_sections`：GL-001/003、AE-004 待核表（实现后）。

## 建议实施顺序（明日起）

1. `lead_required_fields` + 理顺 AE-001/002（简版跳过 CRA）
2. `lead_sheet_section` + `pipeline` 注册
3. `lead_expectation_analysis`
4. AE-004 确定性子集（超门槛 + 调查列 + 波动说明）
5. GL-001/003 摘录；Lead↔K.01 数值勾稽
6. MT-003 摘录（可选）

## 待业务确认

- 无 Lead 表：FAIL（程序缺失） vs NEED_REVIEW（读表失败）
- 超门槛未调查：FAIL vs WARN
- PM 是否纳入必填 FAIL

## 相关代码

- `src/ingest/lead_sheet_blocks.py`, `src/ingest/lead_sheet.py`
- `src/rules/materiality_consistency.py`, `risk_threshold_consistency.py`
- `tests/ingest/test_lead_sheet.py`

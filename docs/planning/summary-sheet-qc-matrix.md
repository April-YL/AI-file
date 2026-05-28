# 汇总页（PSP）— 质检覆盖矩阵

> **工作表**：`汇总`（程序目录、执行状态、拒绝理由、程序页索引）  
> **关联**：[program-qc-coverage-index.md](./program-qc-coverage-index.md)、[qc-checklist.md](../qc-checklist.md) §一、[workpaper-fields.md](../workpaper-fields.md) § 汇总

## 区块划分（逻辑模块）

| 模块 | 内容 | ingest |
| --- | --- | --- |
| **A. 程序主表** | B/C 程序编号与说明、F 程序页、G 执行、H 不执行原因、I 注意事项 | `SummarySheetDataset.programs`、`column_bindings` |
| **B. PSP 执行勾稽** | G=已执行 → 工作簿内是否存在对应 sheet | AE-003 `psp_sheet_matcher` |
| **C. 与 Lead 交叉** | 拒绝执行是否违背 Lead 预期（如处置完整性） | ⏳ 摘录 / 规划 |

---

## 风险点 × 检查方式

| 风险点 | 应如何检查 | 状态 | 规则 / 方式 |
| --- | --- | --- | --- |
| 汇总页不存在 | sheet 分类 + 主表头 | ✅ | ingest；整本结构 `MISSING_CORE_SHEET` |
| 主表列绑定缺失 | G/H/F 列角色 | ✅ | `summary_sheet` ingest notes |
| 应执行 PSP 未执行 / 无 sheet | G 已执行 vs 程序页名称 | ✅ | `psp_completion`（AE-003） |
| 弱匹配程序页 | confidence 不足 | ✅ | AE-003 → `NEED_REVIEW` |
| 目标 sheet 过空 | 非空单元格过少 | ✅ | AE-003 → `WARN` |
| 拒绝执行无理由 / 理由空泛 | H 列 | ⏳ | AE-003 部分 + 人工 |
| PSP 与 K.01 >TE 路由不一致 | 汇总 vs BKD 发生额 | ⏳ | 交叉 K.01 区块6 |
| PM/TE/SAD 与 Canvas 一致 | 汇总或 Lead vs 外部 | ❌ | `materiality_consistency`（Lead AE-001 摘录） |

---

## 报告与验收

| 交付 | 路径 |
| --- | --- |
| JSON 块 | `QcReport.summary_sheet_section` |
| 规则 | `src/rules/psp_completion.py` |
| 单测 | `tests/ingest/test_summary_sheet.py`、`tests/rules/test_psp_completion.py` |
| UI | Streamlit「汇总页 (PSP)」页签 |

**验收命令**：`fa-qc-run tests/fixtures/workbook_psp_demo.xlsx` → 终端 AE-003 一行 + JSON `summary_sheet_section`。

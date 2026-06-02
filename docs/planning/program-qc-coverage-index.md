# 程序质检覆盖索引（开发进度一览）

> **用途**：按**程序 / 工作表**快速了解「应查什么、已实现什么、还缺什么」。详细矩阵见各子文档。  
> **更新**：规则或 ingest 状态变化时，同步改对应矩阵与本表「实现状态」列。  
> **关联**：[qc-checklist.md](../qc-checklist.md)、[rule-dictionary-mapping.md](../rule-dictionary-mapping.md)、[handoff/latest.md](../handoff/latest.md)

## 如何阅读

| 符号 / 列 | 含义 |
| --- | --- |
| **识别层** | ingest 能否读对 sheet、区块/字段/合计（不直接出 FAIL，供规则使用） |
| **P0 规则** | M2a 确定性：`AUTO_FAIL` / 关键 `AUTO_WARN` |
| **M2b** | 跨表勾稽（Lead、FA list、TB、PL 等） |
| **摘录 / LLM** | 无外部输入或需语义判断 → `NEED_REVIEW` / `--llm-rules` |
| ✅ / ⏳ / ❌ | 已实现 / 进行中或规划 / 未做 |

**自动化分层**（与 [lead-qc-rules.md](./lead-qc-rules.md)、[k01-qc-rules.md](./k01-qc-rules.md) 一致）：

| 层级 | Agent 结论 |
| --- | --- |
| M2a 确定性 | `FAIL` / `WARN` |
| M2b 勾稽 | `FAIL` / `WARN`（两侧可比时） |
| 摘录 | `NEED_REVIEW` + 人工核对 HTML |
| LLM（规划） | 附加 `llm_rationale`，**不改** rules severity |

---

## 程序总览

| 程序 | 工作表 / 输入 | 覆盖矩阵文档 | 规则规划 | 识别层 | P0 规则 | 报告块 |
| --- | --- | --- | --- | --- | --- | --- |
| **汇总** | `汇总` | [summary-sheet-qc-matrix.md](./summary-sheet-qc-matrix.md) | AE-003 等 | ✅ 主表 + 列绑定 | ✅ AE-003 | ✅ `summary_sheet_section` |
| **K.00 Lead** | `K.00 Lead Sheet` | [lead-qc-rules.md](./lead-qc-rules.md)（6 模块） | 模块 1–6 | ✅ 6 块锚点 | ✅ 13 条 Lead + AE-001/002/004 | ✅ `lead_sheet_section` |
| **K.01 后推** | `K.01 Agree SL to GL` | [k01-six-block-qc-matrix.md](./k01-six-block-qc-matrix.md) | [k01-qc-rules.md](./k01-qc-rules.md) | ✅ 六区块 + L1 + 表2/表3 + TB check 摘录 | ✅ GL-005/006/007 + GL-002 表3 check | ✅ `rollforward_sheet_section` |
| **FA list** | `FA list` 等 | （见 checklist §四） | `fa_list_*` | ✅ | ✅ M1 三条 + 扩展规划 | findings + 标注 |
| **K.02 新增/处置** | 新增清单、处置清单、测试表 | [k02-k03-qc-matrix.md](./k02-k03-qc-matrix.md) § K.02 | 待建 | ⏳ 清单 ingest | ❌ | ❌ |
| **K.03 折旧** | SAP、TOD、政策复核 | [k02-k03-qc-matrix.md](./k02-k03-qc-matrix.md) § K.03 | 待建 | ⏳ 部分 | ❌ | ❌ |

**交叉规则（多程序）**：

| 规则 ID | 说明 | 状态 |
| --- | --- | --- |
| `lead_rollforward_tb_reconciliation` | Lead 期末 ↔ K.01 合计（LEAD-010） | ✅ |
| `rollforward_fa_list_reconciliation` | K.01 表3 check（表2 SUMIF 辅助；自算合计兜底） | ✅ |
| `rollforward_difference_over_sad` | K.01 TB check 差异 > SAD 时检查 Notes | ⏳ 读取层已起步 |
| AE-003 × Lead 预期 | 汇总 PSP 与 Lead 波动/预期 | ⏳ 摘录为主 |

---

## 端到端验收链（M2a 目标）

```text
汇总（PSP 执行/拒绝理由）
    ↔ Lead（TE/SAD、预期、引导表）
    ↔ K.01（六区块 + 后推 P0）
    ↔ FA list（清单合计）
    → K.02 / K.03（>TE 路由后的详细程序）
```

当前 **已通链路**：汇总 AE-003 + Lead 规则集 + K.01 识别与 P0 + LEAD-010 + GL-002 表3 check + TB check 摘录；**未通**：K.01 >SAD 判断、TE 路由、K.02/K.03 规则、Notes/TE 闭环。

---

## 回归与案例库

| 类型 | 路径 / 命令 |
| --- | --- |
| Lead 案例库 | `python scripts/run_case_lead_regression.py` · `tests/ingest/test_case_lead_regression.py` |
| K.01 识别 | `python scripts/run_case_rollforward_regression.py` · `tests/ingest/test_case_rollforward_regression.py` |
| K.01 P0 规则 | 同上 pytest 内 `test_case_library_k01_p0_rules_pass` |
| 整本 CLI | `fa-qc-run <底稿.xlsx>` |

---

## 子文档维护约定

1. 新增规则：在对应矩阵中增行（风险点 / 规则 ID / 状态），并更新本索引「P0/M2b」列。  
2. 仅 ingest 增强：改矩阵「识别层」列，规则仍为 ⏳ 时可先标 `NEED_REVIEW` 摘录。  
3. K.02/K.03 开工：复制 [k01-six-block-qc-matrix.md](./k01-six-block-qc-matrix.md) 表结构，按工作表区块拆分新文档，并在本索引加一行。

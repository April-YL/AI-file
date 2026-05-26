# K.01 后推明细表 — 新会话启示语（可复制）

> 上一阶段（K.00 Lead）已落地：`ce3fbad`（LEAD-004/007 等）、`87c104d`（协作约定）。远程 `main` 已同步。  
> 本文件供 **新开 Cursor 会话** 时粘贴第一条消息使用。

---

## 粘贴区（复制以下全文）

```text
继续固定资产质检 Agent 开发。

请先阅读：AGENTS.md、docs/agent-collaboration.md、docs/handoff/latest.md、docs/planning/k01-qc-rules.md、docs/planning/k01-workpaper-layouts.md、docs/qc-checklist.md §三、docs/workpaper-fields.md § K.01、docs/domain-glossary.md、docs/rule-dictionary-mapping.md。

协作方式：先回答/给方案；改代码、git commit、git push 前都先列清单等我确认（见 agent-collaboration.md）。不提交 .env / 真实 API 密钥。

---

## 当前阶段

M2a P0：**K.01 后推明细表（Agree SL to GL / rollforward）** 规则 + ingest 稳定化。  
上一阶段 K.00 Lead 已完成主要 P0（含 LEAD-004 GAM 边界、LEAD-007 sheet_ref/py_audited 等，见 commit ce3fbad）。

终态验收（本里程碑仍须对齐）：**质检报告（findings）+ 底稿标注副本**（`*_qc_annotated.xlsx`）。

---

## 已有基础（勿重复造轮子）

**Ingest**
- `src/ingest/rollforward_sheet.py` → `RollforwardSheetDataset`（`amount_column_bindings`、`opening_totals` / `ending_totals`、合计行）
- `load_workbook_context` / `fa-qc-run` / `fa-qc-ui` 已可加载后推 sheet（`SheetKind.ROLLFORWARD`）

**规则（部分）**
- `lead_rollforward_tb_reconciliation`：Lead 引导表 ↔ K.01 **期末 TB 列**勾稽（已在 `lead_runner`）
- 注册表中有 `rollforward_*` / `rollforward_fa_list_reconciliation` 等 **planned**，多数尚未实现

**测试**
- `tests/rules/test_lead_rules_extended.py` 含 Lead↔后推 reconciliation 用例
- 需补充 `tests/ingest/`、`tests/rules/` 针对 K.01 的 fixture 与单测

---

## 本 Section 目标（建议 P0 顺序）

对照 `docs/qc-checklist.md` §三，优先 **确定性规则**（`FAIL`/`WARN`，有据 `NEED_REVIEW`）：

| 优先级 | rule_id（规划名） | 检查点 |
| --- | --- | --- |
| P0 | `rollforward_exists` | 工作簿识别到 K.01 / 后推表存在 |
| P0 | `rollforward_columns_complete` | 原值/累计折旧/减值/净值 × 期初/变动/期末列绑定完整 |
| P0 | `rollforward_abnormal_amounts` | 折旧>原值、净值为负等（注册表已有草案） |
| P1 | `rollforward_ending_reconciliation` | 期末与 TB/FA list（多需外部输入 → 摘录或 NEED_REVIEW） |
| P1 | `rollforward_difference_over_sad` | 差异超 SAD（依赖 TE/SAD 自 Lead 或汇总） |

**ingest 侧**：案例库（B–G）表头变体、期初/期末并列、合计行识别；与 `docs/workpaper-fields.md` 对齐后改 `rollforward_sheet.py`。

**报告/UI**：findings 挂 `procedure_code` K.01；`rollforward_sheet_section`（若尚无则建，对称 `lead_sheet_report.py`）；Streamlit 分程序展示（可选）。

---

## 建议不涉及（除非我明确要求）

- 扩展 `--llm` 报告叙述（P3）
- 新增大量 `fa_list_*` 规则
- 未确认前 `git commit` / `git push`
- 整本 `openpyxl.save` 破坏外链底稿（标注仍走 OXML 路径）

---

## 验收标准（请在第一轮方案里写明）

1. 案例库至少 1 份标准底稿（如 B 医疗）可 `fa-qc-run` / UI 跑出 K.01 相关 findings（或 PASS）。
2. 每条新规则有 `tests/rules/` 单测 + 脱敏 fixture。
3. `registry.py` / `docs/rule-dictionary-mapping.md` 与实现一致。
4. 若改 ingest/规则口径，更新 `docs/domain-glossary.md` 或 `docs/handoff/latest.md`。

---

## 请先回答（再改代码）

1. 阅读 `rollforward_sheet.py` 与案例库 K.01 sheet 样例，给出 **ingest 差距清单**。
2. 给出 **P0 规则实现顺序** 与拟新增文件列表。
3. 确认理解后，我再回复「可以按方案 A 实现」。

当前任务：<可在此补充，例如「先实现 rollforward_exists + rollforward_columns_complete」>。
```

---

## 本地快速验证命令

```powershell
cd "D:\AI file"
pip install -e ".[dev,ui]"
pytest tests/ingest/ -k rollforward -q
fa-qc-run "固定资产质检agent\案例库\<某案例>.xlsx"
```

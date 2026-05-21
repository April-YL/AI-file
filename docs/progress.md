# 项目进度

本文记录阶段性里程碑进展，适合给团队或管理者查看。更细的每日接续信息写入 `docs/handoff/latest.md`。

## 里程碑

| 里程碑 | 目标 | 状态 |
| --- | --- | --- |
| M0：项目骨架 | 建立文档、Cursor 上下文、源码和测试目录 | 已完成 |
| M0.5：业务资料沉淀 | 阅读资料库并沉淀 SOP、checklist、字段映射 | 已完成 |
| M1：技术切片 | ingest、规则字典映射、3 条 `fa_list_*`、JSON 报告 | 已完成 |
| M2a：Agent P1 | 整底稿流水线 + 报告/标注；规则优先汇总页与 K.01 | 进行中 |
| M2b：程序扩展 | K.02 新增/处置、折旧与一致性检查 | 待开始 |
| M3：LLM 挂质检点 + 规则语义 | `--llm-rules` / `--llm-checklist`（非报告摘要为主） | 待开始 |
| M4：材料比对 | 影像、合同、发票等非结构化材料 | 待规划 |

## 当前进展

- 已建立项目级 Agent 上下文。
- 已建立领域词典、架构说明、任务清单和交接模板。
- 已建立 Cursor rules、Skill 和子 Agent 定义。
- 已阅读资料库中的固定资产标准底稿、SOP、checklist 和程序执行资料。
- 已沉淀 `docs/audit-workflow.md`、`docs/qc-checklist.md`、`docs/workpaper-fields.md`。
- 已实现 `src/ingest/`、`src/rules/`（含 registry）、`src/report/`（JSON）及对应测试。
- **M2a 已落地**：`fa-qc-run` / UI、汇总页 ingest + AE-003、`summary_sheet_section`。
- **K.00 Lead ingest（2026-05-20）**：锚点 6 块、`LeadSheetDataset` 扩展、案例库版式回归；规则规划见 `docs/planning/lead-qc-rules.md`（含 FY26 SOP K1.00 对照与遗漏清单，2026-05-21）。

## 下一阶段目标

**P0 — 质检点准确（规则，无 LLM）**

1. Lead 确定性规则（见 `docs/planning/lead-qc-rules.md`）。
2. K.01 `rollforward_*`；Lead↔K.01 勾稽。
3. 底稿批注 v0、案例库端到端回归。

**P1 — LLM 服务质检全过程（非报告摘要）**

4. M3c：`--llm-rules`、`--llm-checklist`（见 `docs/llm-agent-roadmap.md`）。
5. 层 4 `--llm` 维持可选，不作为验收重点。

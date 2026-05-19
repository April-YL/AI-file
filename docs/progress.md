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
| M3：人工复核增强 | NEED_REVIEW 工作流、复核清单导出 | 待开始 |
| M4：材料比对 | 影像、合同、发票等非结构化材料 | 待规划 |

## 当前进展

- 已建立项目级 Agent 上下文。
- 已建立领域词典、架构说明、任务清单和交接模板。
- 已建立 Cursor rules、Skill 和子 Agent 定义。
- 已阅读资料库中的固定资产标准底稿、SOP、checklist 和程序执行资料。
- 已沉淀 `docs/audit-workflow.md`、`docs/qc-checklist.md`、`docs/workpaper-fields.md`。
- 已实现 `src/ingest/`、`src/rules/`（含 registry）、`src/report/`（JSON）及对应测试。

## 下一阶段目标（M2a）

1. 实现 `fa-qc-run`：整本固定资产底稿 → findings → 报告 + 标注副本。
2. ingest 支持汇总 sheet、K.01 后推表（及可选客户台账）结构化提取。
3. 优先实现 AE-003（PSP）、K.01 后推类规则；`fa_list_*` 用于台账↔后推一致性时复用。
4. 定型程序维度质检报告；底稿单元格批注 v0。
5. 案例库小型底稿端到端回归。

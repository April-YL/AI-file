---
name: fixed-asset-qc
description: 执行固定资产质检 Agent 开发工作流。用于固定资产、资产台账、质检规则、规则引擎、质检报告、脱敏样例和人工复核相关任务。
---

# 固定资产质检开发工作流

## 协作约定（默认）

遵循 [docs/agent-collaboration.md](../../docs/agent-collaboration.md)：**先回答问题、给出方案与影响范围；用户确认后再修改** `src/`、`tests/`、`docs/`。**`git commit` / `git push` 前须列拟提交清单并等用户确认**（即使用户说「保存并推送」）。用户写明「请勿直接修改」时仅分析不改动。

## 开始前

1. 阅读 `AGENTS.md` 与 `docs/agent-collaboration.md`。
2. 阅读 `docs/data-security.md`（**`.env` 与 API 密钥不得提交 Git**）。
3. 阅读 `docs/handoff/latest.md`。
4. 如涉及文件职责，阅读 `docs/PROJECT_STRUCTURE.md`。
5. 如涉及字段或规则口径，阅读 `docs/domain-glossary.md`。
6. 如涉及标准底稿、SOP 或程序选择，阅读 `docs/audit-workflow.md`。
7. 如涉及规则优先级或人工复核，阅读 `docs/qc-checklist.md`。
8. 如涉及 Excel 工作表和字段映射，阅读 `docs/workpaper-fields.md`。
9. 如涉及 LLM：先读 `docs/llm-agent-roadmap.md` § 产品优先级——**P0=rules 判对**，**P1=llm-rules/checklist**，`--llm` 报告叙述为 P3。

## 添加质检规则

1. 确认规则输入字段和业务口径，优先参考 `docs/qc-checklist.md`。
2. 在 `tests/fixtures/` 准备脱敏样例。
3. 在 `src/rules/` 实现规则。
4. 在 `tests/rules/` 添加通过、失败和边界测试。
5. 更新 `docs/domain-glossary.md`、`docs/architecture.md`、`docs/workpaper-fields.md` 中受影响内容。
6. 运行测试并修复问题。

## 修改数据接入

1. 确认输入来源是标准底稿 Excel、CSV、API 还是测试 fixture。
2. 在 `src/ingest/` 做字段映射和基础清洗。
3. 不在接入层写业务质检规则。
4. 字段映射优先遵循 `docs/workpaper-fields.md`。
5. 使用脱敏样例覆盖不同列名、工作表和空值情况。

## 修改报告输出

1. 使用统一质检问题结构。
2. 保留 `asset_id`、`rule_id`、`field`、`severity`、`message` 和 `suggestion`。
3. 汇总逻辑放在 `src/report/`。
4. 如输出格式变化，更新 `docs/architecture.md`。

## 收工交接

每次完成阶段性开发后，更新 `docs/handoff/latest.md`：

- 已完成。
- 进行中。
- 下一步。
- 已知问题。
- 相关文件。

## 参考

- 质检结果结构、错误码命名和样例数据约定见 `reference.md`。

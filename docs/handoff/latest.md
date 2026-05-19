# 最新交接

> 每次收工前更新本文。新成员接手先读 `docs/ONBOARDING.md`，再读 `AGENTS.md` 和本文。

## 当前状态

- Git 仓库已初始化并关联 GitHub 远程。
- 已创建固定资产质检 Agent 项目骨架。
- 已读取资料库中的固定资产标准底稿、SOP、checklist 和程序执行资料。
- 已对案例库中 6 份较小脱敏底稿完成读取诊断，暂跳过 42MB 的 A 公司底稿。
- 已实现 `src/ingest/` 轻量读取器（sheet 分类、字段映射、底稿诊断 CLI）。
- 当前处于 M1：在读取器基础上实现首批质检规则与报告结构。

## 已完成

- 项目长期上下文：`AGENTS.md`
- 项目结构说明：`docs/PROJECT_STRUCTURE.md`
- 领域词典：`docs/domain-glossary.md`
- 架构说明：`docs/architecture.md`
- 任务清单：`docs/tasks.md`
- 项目进度：`docs/progress.md`
- 资料库读取摘要：`docs/source-materials-reading-notes.md`
- 固定资产质检流程与 SOP：`docs/audit-workflow.md`
- 固定资产质检 checklist：`docs/qc-checklist.md`
- 固定资产底稿字段映射：`docs/workpaper-fields.md`
- 案例库底稿读取诊断：`docs/case-workpaper-diagnostic.md`
- MVP 范围 ADR：`docs/decisions/ADR-0001-mvp-scope.md`
- Cursor 规则、Skill 和子 Agent 初始配置
- 源码与测试目录说明
- 上手文档：`docs/ONBOARDING.md`
- Sheet 识别策略：`docs/sheet-classification.md`
- `pyproject.toml` 与 `src/ingest/`（含 `fa-qc-diagnose`）
- `tests/ingest/` 分类与映射单测

## 进行中

- 用案例库回归验证 ingest 在更多 sheet 变体下的识别准确率。
- 准备 `tests/fixtures/` 脱敏样例，供规则层使用。

## 下一步

1. 实现第一批规则：`fa_list_required_fields`、`unique_asset_id`、`asset_value_consistency` 等。
2. 在 `src/report/` 输出统一质检问题结构（JSON 优先）。
3. 用 6 份小型案例底稿跑通「读取 → 规则 → 报告」最小闭环。
4. 优化大文件（A 公司约 42MB）读取性能后再纳入诊断。

## 已知问题

- PDF `固定资产程序执行方法指引.pdf` 当前未抽取到正文文本，可能需要 OCR 或源文件。
- A 公司底稿约 42MB，首轮诊断已跳过，需要读取器具备性能优化后再处理。
- 部分字段不能简单模糊匹配，例如处置清单中的 `单据编号` 不应自动当成 `asset_id`。
- 尚未确定报告输出格式是 Excel、JSON 还是两者都要。

## 相关文件

- `docs/ONBOARDING.md`
- `AGENTS.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/domain-glossary.md`
- `docs/architecture.md`
- `docs/source-materials-reading-notes.md`
- `docs/audit-workflow.md`
- `docs/qc-checklist.md`
- `docs/workpaper-fields.md`
- `docs/case-workpaper-diagnostic.md`
- `docs/tasks.md`
- `docs/progress.md`
- `.cursor/skills/fixed-asset-qc/SKILL.md`

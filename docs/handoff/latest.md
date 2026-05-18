# 最新交接

> 每次收工前更新本文。新会话或新成员接手时，先读 `AGENTS.md`、`docs/PROJECT_STRUCTURE.md` 和本文。

## 当前状态

- Git 仓库已初始化并关联 GitHub 远程。
- 已创建固定资产质检 Agent 项目骨架。
- 当前处于 MVP 设计与基础文档阶段，尚未开始实现业务代码。

## 已完成

- 项目长期上下文：`AGENTS.md`
- 项目结构说明：`docs/PROJECT_STRUCTURE.md`
- 领域词典：`docs/domain-glossary.md`
- 架构说明：`docs/architecture.md`
- 任务清单：`docs/tasks.md`
- 项目进度：`docs/progress.md`
- MVP 范围 ADR：`docs/decisions/ADR-0001-mvp-scope.md`
- Cursor 规则、Skill 和子 Agent 初始配置
- 源码与测试目录说明

## 进行中

- 等待确认第一版输入数据格式：Excel、CSV、API 或手工 JSON fixture。
- 等待确认第一批字段名是否与实际台账一致。

## 下一步

1. 准备一份脱敏固定资产台账样例，放入 `tests/fixtures/`。
2. 确认 MVP 首批规则：必填字段、资产编码唯一、金额关系、金额非负、日期合理性。
3. 初始化 Python 工程配置，例如 `pyproject.toml`、依赖和测试命令。
4. 实现第一条规则：必填字段校验。

## 已知问题

- 尚无真实样例字段，当前字段字典为推荐口径。
- 尚未确定报告输出格式是 Excel、JSON 还是两者都要。

## 相关文件

- `AGENTS.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/domain-glossary.md`
- `docs/architecture.md`
- `docs/tasks.md`
- `docs/progress.md`
- `.cursor/skills/fixed-asset-qc/SKILL.md`

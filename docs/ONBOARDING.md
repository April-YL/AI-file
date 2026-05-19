# 新人上手：固定资产质检 Agent

本文帮助新成员、新终端（Cursor / Claude / Codex）在 **5–10 分钟** 内了解项目进度与已有成品。进度以 `docs/handoff/latest.md` 为准；若与本文不一致，以 Git 最新提交和 `handoff` 为准。

## 1. 获取代码

```powershell
git clone https://github.com/April-YL/AI-file.git
cd AI-file
git pull origin main
```

## 2. 必读文档（按顺序）

| 顺序 | 文件 | 用途 |
| --- | --- | --- |
| 1 | [AGENTS.md](../AGENTS.md) | 项目目标、模块边界、质检结论、数据安全 |
| 2 | [handoff/latest.md](handoff/latest.md) | **最新进度**、下一步、已知问题 |
| 3 | [progress.md](progress.md) | 里程碑 M0 / M0.5 / M1… |
| 4 | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | 每个目录/文件的作用 |

PowerShell 一次查看前四份：

```powershell
Get-Content AGENTS.md, docs\handoff\latest.md, docs\progress.md, docs\PROJECT_STRUCTURE.md
```

## 3. 快速看仓库状态

```powershell
git log --oneline -10
git status -sb
```

## 4. 当前阶段与成品

### 里程碑（摘要）

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M0 | 项目骨架、Cursor 规则/Skill、文档目录 | 已完成 |
| M0.5 | 资料库/SOP/checklist 沉淀、案例诊断 | 已完成 |
| M1 | 读取器 + 基础规则 + 报告结构 | 进行中 |
| M2+ | 规则扩展、人工复核、影像材料 | 待规划 |

### 已有成品（可查阅 / 可运行）

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 审计流程 | [audit-workflow.md](audit-workflow.md) | K.00–K.03 SOP 与 Agent 关注点 |
| 质检清单 | [qc-checklist.md](qc-checklist.md) | 可自动化 vs 人工复核 |
| 字段映射 | [workpaper-fields.md](workpaper-fields.md) | FA list 语义必需列、同义词 |
| Sheet 识别 | [sheet-classification.md](sheet-classification.md) | 名称 + 表头内容 |
| 案例诊断报告 | [case-workpaper-diagnostic.md](case-workpaper-diagnostic.md) | 6 份脱敏底稿首轮结论 |
| 读取器 | `src/ingest/` | 分类、映射、`diagnose_workbook` |
| 诊断 CLI | `src/ingest/cli.py` | 命令 `fa-qc-diagnose` |
| 单元测试 | `tests/ingest/` | 分类与映射测试 |

### 尚未完成

| 模块 | 路径 | 说明 |
| --- | --- | --- |
| 规则引擎 | `src/rules/` | 仅有 README，规则待实现 |
| 质检报告 | `src/report/` | 仅有 README |
| 规则单测 | `tests/rules/` | 待补充 fixture 与用例 |

## 5. 本地环境（可选）

```powershell
pip install -e ".[dev]"
$env:PYTHONPATH = "src"
pytest tests/ingest -q
```

对案例库底稿做读取诊断（需本地存在目录，见下节）：

```powershell
python -m ingest.cli
# 或
fa-qc-diagnose
fa-qc-diagnose "路径\到\底稿.xlsx" --json
```

默认跳过大于 20MB 的文件；JSON 输出便于脚本处理。

## 6. 本地资料（不在 Git 中）

以下目录在 `.gitignore` 中，**克隆后需向团队索取**：

| 目录 | 内容 |
| --- | --- |
| `固定资产质检agent/资料库/` | SOP、标准底稿模板、checklist |
| `固定资产质检agent/案例库/` | 脱敏行业案例 Excel |

## 7. 新 AI 会话推荐开场白

复制到 Cursor / Claude / Codex 第一条消息：

```text
继续固定资产质检 Agent 开发。
请先阅读 AGENTS.md、docs/handoff/latest.md、docs/ONBOARDING.md 和 docs/PROJECT_STRUCTURE.md。
当前任务是：<具体任务>
验收标准：<可验证的结果>
```

## 8. 按角色阅读

| 角色 | 优先阅读 |
| --- | --- |
| 审计/产品 | [audit-workflow.md](audit-workflow.md)、[qc-checklist.md](qc-checklist.md) |
| 规则开发 | [qc-checklist.md](qc-checklist.md)、[domain-glossary.md](domain-glossary.md)、`src/rules/README.md` |
| 接入开发 | [workpaper-fields.md](workpaper-fields.md)、[sheet-classification.md](sheet-classification.md)、`src/ingest/` |
| 项目管理 | [progress.md](progress.md)、[tasks.md](tasks.md)、[handoff/latest.md](handoff/latest.md) |

## 9. 收工约定

- 长期结论写入 `docs/` 或 `.cursor/rules/`，不要只留在聊天里。
- 每次收工更新 [handoff/latest.md](handoff/latest.md)。
- 修改 `src/rules/` 时同步更新 `tests/rules/`。
- 不提交真实资产编号、部门、人员、合同或密钥。

## 10. 远程仓库

- GitHub: https://github.com/April-YL/AI-file.git
- 默认分支: `main`

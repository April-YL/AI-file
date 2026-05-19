# 新人上手：固定资产质检 Agent

本文帮助新成员、新终端（Cursor / Claude / Codex）在 **5–10 分钟** 内了解项目进度与已有成品。进度以 `docs/handoff/latest.md` 为准；若与本文不一致，以 Git 最新提交和 `handoff` 为准。

## 项目终态（一句话）

输入**固定资产底稿**及必要辅助文件 → 按 [qc-checklist.md](qc-checklist.md) 检查是否存在 **findings** → 输出**质检报告**并在**底稿副本**上**标注**问题位置（模拟质检人员复核）。详见 [AGENTS.md](../AGENTS.md)。

### 必交付项

| 交付物 | 说明 | 当前状态 |
| --- | --- | --- |
| 质检报告 | findings 清单、严重级别、程序/资产汇总、复核建议 | 进行中（JSON 结构已通） |
| 底稿标注 | 在底稿副本上批注/高亮，与 findings 一一对应 | **未开始** |

## 1. 获取代码

```powershell
git clone https://github.com/April-YL/AI-file.git
cd AI-file
git pull origin main
```

## 2. 必读文档（按顺序）

| 顺序 | 文件 | 用途 |
| --- | --- | --- |
| 1 | [AGENTS.md](../AGENTS.md) | 终态目标、必交付项、模块边界、数据安全 |
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
| M1 | 读取器 + 首批规则 + 报告 JSON 骨架 | 进行中 |
| M2 | 定型质检报告 + **底稿标注回写** + 扩展 checklist 规则 | 待开发 |
| M3+ | 一键 CLI、案例库端到端、多文件/影像等 | 待规划 |

> **终态验收**以「质检报告 + 底稿标注」双交付为准；M1 仅为通向终态的技术切片。

### 已有成品（可查阅 / 可运行）

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 审计流程 | [audit-workflow.md](audit-workflow.md) | K.00–K.03 SOP 与 Agent 关注点 |
| 质检清单 | [qc-checklist.md](qc-checklist.md) | findings 检查来源；可自动化 vs 人工复核 |
| 字段映射 | [workpaper-fields.md](workpaper-fields.md) | FA list 语义必需列、同义词 |
| Sheet 识别 | [sheet-classification.md](sheet-classification.md) | 名称 + 表头内容 |
| 案例诊断报告 | [case-workpaper-diagnostic.md](case-workpaper-diagnostic.md) | 6 份脱敏底稿首轮结论 |
| 读取器 | `src/ingest/` | 分类、映射、`diagnose_workbook`、FA list CSV 解析 |
| 诊断 CLI | `src/ingest/cli.py` | 命令 `fa-qc-diagnose` |
| 规则引擎（首批） | `src/rules/` | FA list 三条规则 + `run_fa_list_rules` |
| 报告骨架 | `src/report/` | `run_fa_list_qc`、JSON 汇总（**无底稿标注**） |
| 单元测试 | `tests/ingest/`、`tests/rules/` | 分类、映射、规则与集成测试 |
| 脱敏 fixture | `tests/fixtures/fa_list_*.csv` | 规则与闭环测试用 |

### 尚未完成（相对终态）

| 能力 | 路径 / 说明 |
| --- | --- |
| **底稿标注（必交付）** | `src/report/` 待增加批注/高亮回写，输出 `*_qc_annotated.xlsx` |
| **正式质检报告（必交付）** | 面向业务的报告导出（Excel 等）；当前主要为 JSON 结构 |
| 全 checklist 规则 | `src/rules/` 仅覆盖 FA list 首批 3 条 |
| Excel 多 sheet 端到端 | FA list 行级解析需与 `workbook_reader` 合并 |
| 一键质检 CLI | `fa-qc-run`：底稿 → 报告 + 标注副本 |
| 案例库回归 | 6 份小型底稿全链路；42MB 大文件待性能优化 |

## 5. 本地环境（可选）

```powershell
pip install -e ".[dev]"
$env:PYTHONPATH = "src"
pytest tests/ingest tests/rules -q
```

对案例库底稿做**读取诊断**（需本地存在目录，见下节）：

```powershell
python -m ingest.cli
# 或
fa-qc-diagnose
fa-qc-diagnose "路径\到\底稿.xlsx" --json
```

默认跳过大于 20MB 的文件；JSON 输出便于脚本处理。

规则 + 报告最小闭环（脱敏 CSV fixture）：

```powershell
python -c "from pathlib import Path; from ingest.records import load_fa_list_csv; from report.export_json import run_fa_list_qc; r=run_fa_list_qc(load_fa_list_csv(Path('tests/fixtures/fa_list_mixed.csv'))); print(r.summary.overall_severity.value, len(r.issues))"
```

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
终态须包含：质检报告 + 底稿标注（若本次未做标注，请说明）。
```

## 8. 按角色阅读

| 角色 | 优先阅读 |
| --- | --- |
| 审计/产品 | [audit-workflow.md](audit-workflow.md)、[qc-checklist.md](qc-checklist.md) |
| 规则开发 | [qc-checklist.md](qc-checklist.md)、[domain-glossary.md](domain-glossary.md)、`src/rules/` |
| 接入 / 标注 | [workpaper-fields.md](workpaper-fields.md)、[sheet-classification.md](sheet-classification.md)、`src/ingest/`、`src/report/` |
| 项目管理 | [progress.md](progress.md)、[tasks.md](tasks.md)、[handoff/latest.md](handoff/latest.md) |

## 9. 收工约定

- 长期结论写入 `docs/` 或 `.cursor/rules/`，不要只留在聊天里。
- 每次收工更新 [handoff/latest.md](handoff/latest.md)。
- 修改 `src/rules/` 时同步更新 `tests/rules/`。
- 不提交真实资产编号、部门、人员、合同或密钥。

## 10. 远程仓库

- GitHub: https://github.com/April-YL/AI-file.git
- 默认分支: `main`

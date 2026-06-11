# 新人上手：固定资产质检 Agent

本文帮助新成员、新终端（Cursor / Claude / Codex）在 **5–10 分钟** 内了解项目进度与已有成品。进度以 `docs/handoff/latest.md` 为准；若与本文不一致，以 Git 最新提交和 `handoff` 为准。

## 项目终态（一句话）

设计并开发一个**固定资产质检 Agent**：输入固定资产底稿及必要辅助文件，按 [qc-checklist.md](qc-checklist.md) 和 SOP 执行基础 review 与可结构化检查，输出**质检报告**并在**底稿副本**上**标注**问题位置，让质检人员把更多时间用于高风险事项、重大审计判断和风险管理。详见 [AGENTS.md](../AGENTS.md)。

### 必交付项

| 交付物 | 说明 | 当前状态 |
| --- | --- | --- |
| 质检报告 | findings 清单、严重级别、程序/资产汇总、复核建议 | 进行中（JSON 结构已通） |
| 底稿标注 | `*_qc_annotated.xlsx`（双 Comments 表 + 批注） | **M2a 首版**（见 [workpaper-annotation.md](workpaper-annotation.md)） |

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
| 2 | [agent-collaboration.md](agent-collaboration.md) | **先答后改**：确认理解一致后再让 Agent 改代码 |
| 3 | [handoff/latest.md](handoff/latest.md) | **最新进度**、下一步、已知问题 |
| 4 | [progress.md](progress.md) | 里程碑 M0 / M0.5 / M1… |
| 5 | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | 每个目录/文件的作用 |

PowerShell 一次查看前四份：

```powershell
Get-Content AGENTS.md, docs\handoff\latest.md, docs\progress.md, docs\PROJECT_STRUCTURE.md
```

### 2.1 资料库固定入口

做固定资产底稿开发时，先按这个顺序读资料库，避免每次重新搜索：

1. `固定资产质检agent/资料库/K1 SWP 固定资产 202YMMDD XYZ公司.xlsx`：标准底稿模板
2. `固定资产质检agent/资料库/FY26_SOP K1 SWP 固定资产.xlsx`：标准包 + SOP 说明
3. `固定资产质检agent/资料库/固定资产程序执行方法指引.pdf`：程序执行方法
4. `固定资产质检agent/资料库/K1 check list.xlsx`：质检 checklist
5. `docs/audit-workflow.md`：把上述资料整理成可读的流程索引

K.02 新增/处置开发时，优先看 `docs/audit-workflow.md` 和 `docs/planning/k02-disposal-qc-matrix.md`。

### 2.2 通用 Excel 读取模板

遇到任何本地 Excel 文件，先按这套方式读，避免中文路径和命令行编码来回试错：

```powershell
$p = (Get-ChildItem -LiteralPath 'E:\AI file\固定资产质检agent\资料库' | Where-Object Name -eq 'K1 SWP 固定资产 202YMMDD XYZ公司.xlsx').FullName
& '.\.venv\Scripts\python.exe' .\scripts\inspect_workbook.py --path $p
```

原则很简单：

1. 先拿真实全路径，再传给脚本。
2. 中文文件名不要直接塞进很长的 `python -c` 字符串。
3. 先只读看 sheet 名、维度、合并单元格和关键锚点，再决定要不要继续深入。
4. 资料库、案例库、导出结果、测试 fixture 的 Excel 都按同一套方法读。

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
| M1 | ingest 诊断、规则字典映射、3 条 `fa_list_*`、JSON 报告骨架 | 已完成 |
| **M2a（Agent P1）** | **整底稿流水线** + 报告/标注雏形；规则优先 **汇总 + K.01** | **进行中** |
| M2b+ | K.02 新增/处置、折旧逻辑、38 checkpoint 扩展 | 待开发 |
| M3+ | 案例库全量回归、影像等 | 待规划 |

> **终态验收**以「质检报告 + 底稿标注」双交付为准。客户台账与 FA list 均为 ingest 输入路径，**不是**当前 P1 主线。

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
| 规则引擎 | `src/rules/` | 3 条 `fa_list_*`（M1）；registry 35+ 条映射；M2a 优先汇总/K.01 |
| 报告骨架 | `src/report/` | `run_fa_list_qc`、JSON 汇总（**无底稿标注**） |
| 单元测试 | `tests/ingest/`、`tests/rules/` | 分类、映射、规则与集成测试 |
| 脱敏 fixture | `tests/fixtures/fa_list_*.csv` | 规则与闭环测试用 |

### 尚未完成（相对终态）

| 能力 | 路径 / 说明 |
| --- | --- |
| **底稿标注（必交付）** | `export_annotated_workbook.py` → `*_qc_annotated.xlsx`（已实现首版） |
| **正式质检报告（必交付）** | 面向业务的报告导出（Excel 等）；当前主要为 JSON 结构 |
| **M2a 流水线** | `fa-qc-run`、整本 Excel 解析、汇总/K.01 规则、底稿标注 |
| 全 checklist 规则 | 大部分仍为 planned / manual_only |
| 客户台账路径 | 与 FA list 共用 `fa_list_*`，作 K.01 一致性核对输入 |
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

### 图形界面（推荐业务同事使用）

**推荐**（项目内虚拟环境；**不要用** `.\scripts\start-ui.ps1`，易被 PowerShell 策略拦截）：

```cmd
cd /d "d:\AI file"
scripts\start-ui.bat
```

或双击项目根目录 **`启动质检界面.bat`**，或 `scripts\start-ui.bat`。

若必须用 PowerShell 脚本：

```powershell
powershell -ExecutionPolicy Bypass -File "d:\AI file\scripts\start-ui.ps1"
```

首次会自动创建 `.venv` 并安装依赖。浏览器打开 http://localhost:8501 → 选底稿 →「开始质检」。

若坚持用全局 Python：

```powershell
pip install -e ".[ui]"
fa-qc-ui
```

安装若报 `WinError 32`：先关闭所有 `fa-qc-ui`/Streamlit 窗口和终端，再重试；或改用上面的 `start-ui.ps1`。

规则 + 报告最小闭环（命令行）：

```powershell
fa-qc-run tests/fixtures/fa_list_mixed.csv
```

### 大模型 API（M3，可选）

**请先读** [llm-agent-roadmap.md](llm-agent-roadmap.md) § 产品优先级：

- **最重要**：每个质检点由 **`rules` 判对**（Lead/K.01 等确定性规则，M2a P0）。
- **LLM 终态**：挂在 **ingest 映射、`--llm-rules` 语义质检点、`--llm-checklist` 逐条评估**——不是报告摘要。
- **`--llm`（层 4）**：规则跑完后的文字摘要，**已实现、优先级最低**；勾选它**不能**代替 Lead 等规则实现。

复制 `.env.example` 为 `.env`，填写 `FA_QC_LLM_API_KEY`（**勿提交 `.env`**，见 [data-security.md](data-security.md)）。

提交代码前请执行：`python scripts/check_staged_no_secrets.py`

```powershell
# 团队验收基线（推荐）：纯规则
fa-qc-run tests/fixtures/workbook_with_lead.xlsx

# 层 4 报告叙述（可选，低优先级；已实现）
# $env:FA_QC_LLM_API_KEY = "<your-api-key>"
# fa-qc-run tests/fixtures/workbook_with_lead.xlsx --llm

# M3c 规划（高优先级，尚未实现）
# fa-qc-run 底稿.xlsx --llm-rules
# fa-qc-run 底稿.xlsx --llm-checklist
```

`--llm-rules` / `--llm-checklist` 落地后，`severity` 仍仅由 `rules` 决定；LLM 在 issue 上附加 `llm_rationale` 或输出 `checklist_assessments[]`。

```powershell
pytest tests/ingest tests/rules tests/llm -q
```

## 6. 本地资料（不在 Git 中）

以下目录在 `.gitignore` 中，**克隆后需向团队索取**：

| 目录 | 内容 |
| --- | --- |
| `固定资产质检agent/资料库/` | SOP、标准底稿模板、checklist |
| `固定资产质检agent/案例库/` | 脱敏行业案例 Excel |

## 7. 新 AI 会话推荐开场白

在 **Claude** 中开发：先读 [CLAUDE_START.md](CLAUDE_START.md)（阅读顺序 + 可粘贴开场白）。

复制到 Cursor / Claude / Codex 第一条消息：

```text
继续固定资产质检 Agent 开发。
请先阅读 AGENTS.md、docs/agent-collaboration.md、docs/handoff/latest.md、docs/ONBOARDING.md 和 docs/PROJECT_STRUCTURE.md。
协作方式：先回答/给方案；改代码、git commit、git push 前都先列清单等我确认（见 agent-collaboration.md）。
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

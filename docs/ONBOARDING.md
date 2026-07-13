# 新人上手：固定资产质检 Agent

本文帮助阅读仓库的开发者快速理解项目定位、当前能力、运行方式和扩展边界。项目首页见 [`README.md`](../README.md)，最新接手事项见 [`handoff/latest.md`](handoff/latest.md)。

## 1. 项目定位

固定资产质检 Agent 读取固定资产审计底稿，执行可结构化的基础复核，输出质检报告，并在底稿副本上标注问题位置。

它是审计辅助工具，不替代审计人员对风险、会计估计、证据充分性和重大审计判断的责任。自动结论只使用 `PASS`、`WARN`、`FAIL`、`NEED_REVIEW`。

## 2. 获取代码

```powershell
git clone https://github.com/April-YL/AI-file.git
cd AI-file
```

建议阅读顺序：

1. [`README.md`](../README.md)：项目概览与快速启动。
2. [`AGENTS.md`](../AGENTS.md)：项目约束、数据安全和修改确认规则。
3. [`handoff/latest.md`](handoff/latest.md)：当前基线、风险和下一步。
4. [`architecture/fa_qc_governance_plan.md`](architecture/fa_qc_governance_plan.md)：规则真源和执行证据边界。
5. [`qc-checklist.md`](qc-checklist.md)：业务检查来源。
6. [`planning/program-qc-coverage-index.md`](planning/program-qc-coverage-index.md)：分程序覆盖索引。

## 3. 资料入口

以下标准资料已随 Git 仓库提供，不需要克隆后另行索取：

1. `固定资产质检agent/资料库/K1 SWP 固定资产 202YMMDD XYZ公司.xlsx`：标准底稿模板。
2. `固定资产质检agent/资料库/FY26_SOP K1 SWP 固定资产.xlsx`：标准包和 SOP 说明。
3. `固定资产质检agent/资料库/固定资产程序执行方法指引.pdf`：程序执行方法。
4. `固定资产质检agent/资料库/K1 check list.xlsx`：质检 checklist。
5. `docs/audit-workflow.md`：上述资料的可读流程索引。

这些文件用于理解标准程序和开发规则。真实项目底稿、客户资料、本地案例库和质检输出不在公开分享范围内，也不得提交。

读取 Excel 时使用仓库相对路径，不要绑定开发者本机盘符：

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_workbook.py --path ".\固定资产质检agent\资料库\K1 SWP 固定资产 202YMMDD XYZ公司.xlsx"
```

## 4. 当前能力

| 模块 | 当前状态 |
| --- | --- |
| 汇总页 / PSP | 已接入程序执行、拒绝理由和工作表引用等检查 |
| K.00 Lead | 已接入基础信息、CRA/TT、预期分析、变动说明和调整汇总等读取与规则 |
| K.01 后推 | 已接入六区块识别、列完整性和多项金额勾稽规则 |
| K.02 新增/处置 | 清单、总体勾稽、选样输出和详细测试规则已进入主流程 |
| K.03 折旧 | SAP/TOD/政策路径识别、runner 分派、关键参数和差异规则已进入主流程 |
| 报告 | JSON、HTML、UI、执行台账已可运行；正式 Excel 汇总报告仍待完善 |
| 底稿标注 | 已生成 `*_qc_annotated.xlsx`，包含 Comments 表和单元格批注 |
| LLM | OpenAI 兼容客户端和可选辅助能力已实现；默认关闭，不能替代规则 |

这不是“全 checklist 已自动完成”。具体规则以 `src/rules/registry.py` 为准；需要项目背景、证据充分性或重大判断的事项应保留为人工复核。

## 5. 安装与运行

要求 Python 3.10 或更高版本。

### Windows 推荐方式

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ui]"
```

启动界面：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-ui.ps1
```

也可以双击根目录 `启动质检界面.bat`。界面默认访问 `http://localhost:8501`。

### 命令行

```powershell
fa-qc-diagnose ".\路径\到底稿.xlsx" --json
fa-qc-run tests\fixtures\workbook_with_lead.xlsx
```

### 其他操作系统

核心代码是 Python 包，可按标准方式安装：

```bash
python -m venv .venv
python -m pip install -e ".[dev,ui]"
fa-qc-run tests/fixtures/workbook_with_lead.xlsx
```

当前启动脚本、中文路径、Excel 样式保真和标注导出主要在 Windows 验证。Linux/macOS 使用者应自行验证这些能力；仓库不宣称已经完成跨平台验收。

## 6. 可选 LLM 配置

复制 `.env.example` 为 `.env`，填写 OpenAI 兼容端点、模型和密钥。`.env` 已被 Git 忽略，严禁提交真实 API Key。

```powershell
Copy-Item .env.example .env
```

- `--llm` 是可选辅助能力，不影响规则 severity。
- `--llm-rules`、`--llm-checklist` 仍属于规划方向，不能在文档或 UI 中描述为正式完成。
- 使用真实底稿调用外部 API 前，必须确认数据安全和脱敏要求。

详见 [`data-security.md`](data-security.md) 和 [`llm-agent-roadmap.md`](llm-agent-roadmap.md)。

## 7. 修改和验证

修改规则前必须阅读领域词典、checklist、最新 handoff 和治理方案。修改 `src/rules/` 时同步更新 `tests/rules/`。

项目约定优先通过统一脚本运行测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

提交前至少检查：

```powershell
git status --short
python scripts\check_staged_no_secrets.py
```

代码、文档、`git add`、commit 和 push 的确认要求见 [`agent-collaboration.md`](agent-collaboration.md)。

## 8. 拓展其他科目

可以复用工作簿读取、规则注册、执行台账、observation、报告和标注框架，但不能直接复用固定资产的业务结论。

新增科目至少需要：

1. 独立的领域词典和标准底稿结构说明。
2. checklist/SOP 到 rule_id 的映射。
3. ingest 识别结果与可靠性边界。
4. registry 准入、runner 接线和执行台账。
5. 脱敏 fixture、规则测试和报告/标注验收。

UI 不得根据名称或关键词自行推断新科目结论；它只能展示规则和执行台账产出的结构化事实。

## 9. 仓库边界

- GitHub 默认分支是 `main`。
- 仓库用于代码和方法展示，不代表接受外部直接修改。
- 公开标准资料可用于理解本项目；真实数据、`.env`、案例库和本地输出不得提交。
- 当前能力和已知风险以 [`handoff/latest.md`](handoff/latest.md) 为准，历史记录见 `docs/handoff/archive/`。

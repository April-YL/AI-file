# Repository Noise Map

结论：当前仓库的核心逻辑主要在 `src/`、`tests/`、`docs/` 的规则/设计文档、`scripts/` 的固定工具脚本，以及必要的 fixture；下列内容属于非核心逻辑产物、隐藏状态或运行噪声。本清单只暴露结构，不要求删除。

## Scope

本文件用于标记当前工作区中不属于核心业务逻辑的文件和目录，包括缓存、临时测试输出、运行报告、Codex/Agent 产物、IDE 本地状态、环境与依赖目录、本地底稿资料。

本文件不修改任何代码逻辑，不改变测试，不清理文件，也不调整 `.gitignore`。

## Core Logic Boundary

下列内容通常视为核心或准核心：

- `src/`: 固定资产质检 Agent 的 ingest、rules、report、llm、UI 入口等实现。
- `tests/`: 规则、读取、报告、LLM 的测试代码。
- `tests/fixtures/`: 脱敏测试样例；其中已明确用于测试的 `.xlsx/.csv/.json` 仍属于测试资产。
- `docs/`: 项目规则、路线图、handoff、领域说明、规则矩阵等文档。
- `scripts/`: 可复用诊断、导出、检查脚本。
- `pyproject.toml`、`.gitignore`、`.env.example`、`AGENTS.md`: 项目配置与协作入口。
- `.cursor/agents/`、`.cursor/rules/`、`.cursor/skills/`: 已纳入版本管理的 Agent 协作材料。

## Non-Core Artifacts And Hidden Noise

### Python Cache

状态：非核心逻辑，运行/测试自动生成。

- `__pycache__/`
- `*.pyc`
- `src/**/__pycache__/`
- `tests/**/__pycache__/`
- `scripts/__pycache__/`

说明：这些文件只反映本机 Python 执行状态，不代表业务规则或测试逻辑。

### Pytest Cache And Temporary Workbooks

状态：非核心逻辑，测试运行产物。

- `.pytest_cache/`
- `.pytest_tmp/`
- `.pytest_tmp_disposal_ingest_enhance/`
- `.pytest_tmp_disposal_ingest_enhance2/`
- `.pytest_tmp_disposal_ingest_enhance3/`
- `.pytest_tmp_disposal_ingest_final/`
- `.pytest_tmp_disposal_rules_final/`
- `.pytest_tmp_disposal_rules_joint/`
- `.pytest_tmp_disposal_stage345/`
- `.pytest_tmp_disposal_stage345_final/`
- `.pytest_tmp_disposal_stage345_final2/`
- `.pytest_tmp_disposal_stage345_final3/`
- `.pytest_tmp_j_fix1/` through `.pytest_tmp_j_fix8/`
- `.pytest_tmp_k03_1b_final/`
- `.pytest_tmp_k03_1c_dev/`
- `.pytest_tmp_k03_1c_final/`
- `.pytest_tmp_k03_1c_final_review/`
- `.pytest_tmp_k03_1c_hardening/`
- `.pytest_tmp_k03_1c_hardening_full/`
- `.pytest_tmp_k03_1c_pipeline/`
- `.pytest_tmp_k03_ingest/`
- `.pytest_tmp_k03_mvp_acceptance/`
- `.pytest_tmp_k03_rules/`
- `.pytest_tmp_report_pipeline/`
- `.pytest_tmp_stage12_final1/` through `.pytest_tmp_stage12_final6/`
- `.pytest_tmp_stage12_fix1/` through `.pytest_tmp_stage12_fix3/`

只读盘点时，根目录下发现 39 个 `.pytest_tmp*` 目录。它们主要包含测试过程中生成的临时 Excel workbook，不是规则实现本身。

### Generic Temp Directory

状态：非核心逻辑，本地临时检查产物。

- `.tmp/`

说明：属于临时运行目录；不应被视为源代码、正式测试 fixture 或正式报告。

### Virtual Environment And Build Metadata

状态：非核心逻辑，本机依赖环境或安装元数据。

- `.venv/`
- `venv/`
- `src/fixed_asset_qc_agent.egg-info/`

说明：这些文件可由依赖安装或打包流程重新生成，不属于项目业务逻辑。

### IDE And Local Editor State

状态：非核心逻辑，本机开发环境状态。

- `.idea/`
- `.vscode/`

说明：`.cursor/agents`、`.cursor/rules`、`.cursor/skills` 已被项目当作协作资料使用；但 `.idea/`、`.vscode/` 属于个人 IDE 状态，不应作为业务逻辑判断依据。

### Environment And Secrets

状态：非核心逻辑，本机敏感配置。

- `.env`
- `.env.local`
- `.env.*.local`
- `.env.development`
- `.env.production`
- `*.pem`

说明：`.env.example` 是可入库模板；真实 `.env` 和密钥文件不应入库，也不属于系统逻辑。

### Runtime Reports And QC Outputs

状态：非核心逻辑，运行输出或人工分析产物。

- `outputs/`
- `artifacts/` 中非 `case_*.json` / `case_*.md` 的本地输出。
- `*_qc_report.json`
- `*_qc_review.html`
- `*_qc_annotated.xlsx`
- `qc_report.json`
- `.tmp_qc_out`

说明：正式回归样例可保留在 `artifacts/case_*.json`、`artifacts/case_*.md`；其他报告、HTML、标注副本通常是某次运行结果。

### Codex / Agent Runtime Artifacts

状态：非核心逻辑，Agent 会话、导出和索引产物。

- `agent-transcripts/`
- `docs/history/`
- `docs/cursor-transcript-index.html`
- `docs/reports/`

说明：这些内容可用于追溯协作过程，但不属于固定资产质检规则、读取逻辑或报告生成逻辑。

### Local Workpaper Library And Case Data

状态：非核心逻辑；可能包含真实或大体积底稿，应与脱敏 fixture 区分。

- `固定资产质检agent/资料库/`
- `固定资产质检agent/案例库/`
- `固定资产质检agent/质检测试结果/`

说明：这些目录包含本地底稿、案例、待分析/已分析结果和质检输出。它们可以用于人工验证，但不应默认视为可提交的核心代码或测试 fixture。

### Excel Lock And OS Files

状态：非核心逻辑，系统或 Office 自动生成。

- `~$*`
- `Thumbs.db`
- `Desktop.ini`
- `.DS_Store`

说明：这些文件只表示本地系统状态或 Office 临时锁，不代表底稿内容或质检逻辑。

## Current Git Visibility

只读盘点结果：

- `git status --short`：干净。
- `git ls-files --others --exclude-standard`：无普通未跟踪文件。
- `git ls-files --others --ignored --exclude-standard`：可看到大量 ignored 噪声，包括 `.pytest_tmp*`、`.venv/`、`__pycache__/`、本地底稿资料和运行输出。
- 扫描 `.pytest_cache/` 时出现权限受限提示，但目录已识别为 pytest cache。

## Practical Interpretation

这些文件和目录的共同特点是：它们解释了当前工作区为什么“看起来很满”，但不解释系统如何执行固定资产质检。做系统结构分析、规则变更、测试验收时，应优先看核心逻辑边界中的文件；做仓库卫生或交付打包时，再单独处理本清单列出的噪声。

## Impact Classification

Python Cache -> Impact Level A (Critical Noise) -> `__pycache__/` and `*.pyc` are interpreter-generated files. They must be ignored because they add no audit logic, rule evidence, or reproducible test value.

Pytest Cache And Temporary Workbooks -> Impact Level A (Critical Noise) -> `.pytest_cache/` and `.pytest_tmp*` are test runtime leftovers. They can contain generated workbook copies and should not influence source review or rule behavior.

Generic Temp Directory -> Impact Level A (Critical Noise) -> `.tmp/` is a local scratch area. It must not be treated as source, fixture, report, or handoff evidence.

Virtual Environment And Build Metadata -> Impact Level A (Critical Noise) -> `.venv/`, `venv/`, and `*.egg-info/` are environment/build outputs. They are reproducible from project configuration and must not drive architecture decisions.

IDE And Local Editor State -> Impact Level A (Critical Noise) -> `.idea/` and `.vscode/` are local editor state. They should be ignored unless a specific shared editor configuration is intentionally promoted.

Environment And Secrets -> Impact Level A (Critical Noise) -> `.env` and key files are local sensitive configuration. They must be ignored and excluded from commits; only `.env.example` is structural.

Runtime Reports And QC Outputs -> Impact Level B (Neutral Outputs) -> QC JSON/HTML/annotated Excel outputs can help reproduce a run, but they are downstream results. They should not affect core ingest/rule/report logic.

Codex / Agent Runtime Artifacts -> Impact Level B (Neutral Outputs) -> Agent transcripts, history exports, and generated progress reports can support debugging or audit trail review. They are not executable system behavior.

Local Workpaper Library And Case Data -> Impact Level C (Potentially Structural Assets) -> Workpapers, case libraries, SOP materials, and test-result folders may encode domain examples or acceptance evidence. They need explicit treatment as fixtures, private data, or external evidence before integration.

Excel Lock And OS Files -> Impact Level A (Critical Noise) -> Office lock files and OS metadata are machine-generated. They must be ignored because they are unrelated to workbook content or quality-control conclusions.

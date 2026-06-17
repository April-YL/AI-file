# Entry Point And Bootstrap Map

结论：当前系统实际入口是 CLI + 本地 Streamlit UI + 若干诊断/回归脚本；未发现独立 API server、scheduler 或后台任务启动器。

## Scope

本文件只记录当前仓库的入口脚本和启动流，不修改执行逻辑，不新增入口，不重构 CLI/UI/ingest。

## Installed Console Scripts

`pyproject.toml` 定义了 3 个安装后命令：

- `fa-qc-diagnose` -> `ingest.cli:main`
- `fa-qc-run` -> `report.cli:main`
- `fa-qc-ui` -> `fa_qc_ui:main`

这些是安装项目后最正式的用户入口。

## Main QC CLI Entry

入口：`src/report/cli.py`

启动方式：

- `fa-qc-run <input>`
- 或直接运行 `python -m report.cli <input>`（在 `src` 可导入时）

实际启动流：

1. `main()` 读取 `.env`。
2. argparse 解析输入文件、sheet override、LLM 开关、HTML/标注副本开关。
3. `load_input()` 先尝试读取 CSV 或 Excel FA list，用于输入格式校验和提示。
4. Excel 输入进入 `run_input_qc()`。
5. `run_input_qc()` 对 Excel 调用 `run_workbook_qc_from_path()`，对 CSV 调用 FA list 规则路径。
6. workbook 路径继续进入 `load_workbook_context()`。
7. `load_workbook_context()` 调用 `load_workbook_ingest()` 建立整本底稿上下文。
8. `run_workbook_qc()` 串行执行 summary、Lead、K.02、K.03、K.01、delivery、LLM 等检查。
9. CLI 导出 JSON、HTML、标注 Excel 副本。
10. 如果总体结论为 `FAIL`，CLI 以 exit code `3` 退出。

核心链路：

`report.cli.main -> report.pipeline.run_input_qc -> run_workbook_qc_from_path -> ingest.workbook_context.load_workbook_context -> ingest.workbook_ingest.load_workbook_ingest -> report.pipeline.run_workbook_qc -> report/export_*`

## Ingest Diagnostic Entry

入口：`src/ingest/cli.py`

启动方式：

- `fa-qc-diagnose`
- 或直接运行 `python -m ingest.cli`

实际启动流：

1. `main()` 解析文件/目录路径、`--json`、`--ingest`、`--max-mb`。
2. 未传路径时，尝试定位案例库目录。
3. 对每个 Excel workbook 调用 `diagnose_workbook()`。
4. 如果指定 `--ingest`，额外调用 `load_workbook_ingest()`。
5. 输出 sheet 分类、置信度、字段映射、缺失字段和可选 ingest 摘要。

定位：这是读取诊断入口，不生成正式 QC report，不导出标注副本。

## UI Entry Points

### Installed UI Command

入口：`src/fa_qc_ui.py`

启动方式：

- `fa-qc-ui`

实际启动流：

1. 定位 `src/report/ui_app.py`。
2. 调用 `python -m streamlit run src/report/ui_app.py --server.headless true --browser.gatherUsageStats false`。
3. 由 Streamlit 接管页面生命周期。

### Internal UI Launcher

入口：`src/report/ui_launcher.py`

作用：与 `src/fa_qc_ui.py` 类似，直接启动 `src/report/ui_app.py`。

定位：辅助 launcher，不是新的业务执行路径。

### Streamlit App

入口：`src/report/ui_app.py`

实际执行流：

1. Streamlit 加载页面时导入模块并加载 `.env`。
2. 用户上传 workbook/CSV。
3. 点击“开始质检”后，`_run_qc_cached()` 将上传文件写入临时目录。
4. 调用 `run_input_qc()` 执行同一套 QC pipeline。
5. 调用 `export_report_json()`、`export_review_html()`、`export_annotated_workbook()` 生成下载内容。
6. 页面展示 findings、人工复核摘录、质检摘要、HTML preview 和下载按钮。

定位：UI 不重写规则逻辑；它包装同一套 pipeline，并增加上传、缓存、临时目录和下载体验。

## Bootstrap Scripts

### Root Convenience Script

入口：`启动质检界面.bat`

启动流：

`启动质检界面.bat -> scripts/start-ui.bat`

定位：Windows 双击启动便利入口。

### Windows Batch UI Bootstrap

入口：`scripts/start-ui.bat`

启动流：

1. 切到项目根目录。
2. 如果 `.venv\Scripts\python.exe` 不存在，则创建 `.venv`。
3. 安装 `.[ui]` 依赖。
4. 优先运行 `.venv\Scripts\fa-qc-ui.exe`。
5. 如果 `fa-qc-ui.exe` 失败，fallback 到 `python -m streamlit run src\report\ui_app.py`。

定位：环境准备 + UI 启动脚本。

### PowerShell UI Bootstrap

入口：`scripts/start-ui.ps1`

启动流：

1. 切到项目根目录。
2. 如果 `.venv\Scripts\python.exe` 不存在，则创建 `.venv` 并安装 `.[ui]`。
3. 直接运行 `python -m streamlit run src\report\ui_app.py`。

定位：PowerShell 版本的 UI bootstrap。

## Auxiliary Script Entries

`scripts/` 下存在多个可直接运行的脚本，例如：

- `scripts/inspect_workbook.py`
- `scripts/run_case_lead_regression.py`
- `scripts/run_case_rollforward_regression.py`
- `scripts/run_case_addition_reconciliation.py`
- `scripts/run_case_ingest_routing.py`
- `scripts/test_llm_connection.py`
- transcript/export/progress/report 相关脚本

定位：这些是诊断、回归、导出或维护脚本，不是主系统启动入口。部分脚本会直接调用 `load_workbook_context()`、`run_workbook_qc()` 或 ingest 诊断函数，但服务于开发/验证流程。

## API And Scheduler Status

只读检索未发现以下服务型入口：

- FastAPI / Flask / APIRouter
- uvicorn / ASGI server
- APScheduler / schedule / cron
- Celery / RQ / Airflow

当前系统没有常驻 API 服务，也没有仓库内定义的定时调度器。执行由用户主动触发：CLI 命令、Streamlit UI 操作或辅助脚本。

## Startup Flow Summary

### Report CLI

`fa-qc-run -> report.cli.main -> run_input_qc -> workbook/CSV branch -> rules/report pipeline -> JSON/HTML/annotated outputs`

### Diagnostic CLI

`fa-qc-diagnose -> ingest.cli.main -> diagnose_workbook -> optional load_workbook_ingest -> console/JSON diagnostic output`

### UI

`启动质检界面.bat or scripts/start-ui.* or fa-qc-ui -> streamlit run ui_app.py -> upload file -> run_input_qc -> export outputs for download`

### Auxiliary Scripts

`python scripts/<tool>.py -> targeted diagnostic/regression/export logic -> optional shared ingest/pipeline calls`

## Execution Coupling Map

### Shared Execution Flows

Report CLI and UI -> STRONG COUPLING -> Both call `report.pipeline.run_input_qc()` as the core QC execution function. This means workbook/CSV routing, rule execution, LLM enablement behavior, and report construction are shared.

Report CLI and UI workbook path -> STRONG COUPLING -> Both ultimately use `run_workbook_qc_from_path()`, `load_workbook_context()`, `load_workbook_ingest()`, and `run_workbook_qc()` for Excel workbooks. The UI wraps uploaded files into a temp path, but the core path is the same.

Report CLI and UI exports -> STRONG COUPLING -> Both reuse `export_report_json()`, `export_review_html()`, and `export_annotated_workbook()`. The CLI writes files to user-selected/default paths; the UI writes to a temp directory and exposes bytes as downloads.

Report CLI and installed UI command -> WEAK COUPLING -> `fa-qc-run` and `fa-qc-ui` are separate console scripts, but they converge inside `report.pipeline.run_input_qc()` after UI upload handling.

UI launcher variants -> STRONG COUPLING -> `src/fa_qc_ui.py`, `src/report/ui_launcher.py`, `scripts/start-ui.bat`, and `scripts/start-ui.ps1` all converge on `streamlit run src/report/ui_app.py`. Differences are environment setup and fallback behavior, not QC logic.

Auxiliary regression scripts and report pipeline -> WEAK COUPLING -> Some scripts call `load_workbook_context()` or `run_workbook_qc()` directly for targeted regression checks. They reuse internal functions, but bypass CLI parsing and standard export behavior.

### Divergence Points

Ingest diagnostic flow vs report flow -> WEAK COUPLING -> `fa-qc-diagnose` uses `diagnose_workbook()` and optionally `load_workbook_ingest()`. It shares the workbook reading/classification layer but does not call `run_input_qc()`, does not execute full QC rules, and does not produce official report artifacts.

CSV report flow vs workbook report flow -> WEAK COUPLING -> `run_input_qc()` routes CSV to FA list QC and Excel to full workbook QC. They share report construction concepts, but Excel uses the full workbook context and multi-sheet pipeline.

UI flow vs CLI flow -> STRONG COUPLING with wrapper divergence -> UI does not call `report.cli.main()`; it directly calls `run_input_qc()` and export functions. It diverges for upload handling, Streamlit cache, temporary files, UI rendering, download filenames, and multi-file loop.

Bootstrap scripts vs installed UI command -> WEAK COUPLING -> Batch/PowerShell scripts prepare `.venv` and dependencies, then run `fa-qc-ui` or Streamlit directly. They share the UI target, but not Python package entry-point logic.

LLM connection script vs QC LLM flow -> WEAK COUPLING -> `scripts/test_llm_connection.py` validates LLM configuration/connectivity separately. It does not execute workbook QC, but it touches the same configuration/client layer used by the report pipeline when LLM is enabled.

Transcript/export scripts vs QC system -> NO COUPLING -> Agent transcript import/export, progress report exports, and transcript index builders do not participate in workbook QC execution. They are project maintenance artifacts.

### Coupling Classification Summary

`report.cli.main` <-> `report.ui_app._run_qc_cached` -> STRONG COUPLING -> Shared `run_input_qc()` and shared export functions.

`fa_qc_ui.main` <-> `report.ui_launcher.main` <-> `scripts/start-ui.*` -> STRONG COUPLING -> Same Streamlit app target.

`ingest.cli.main` <-> `report.pipeline.run_workbook_qc_from_path` -> WEAK COUPLING -> Shared ingest functions, different final purpose.

`scripts/run_case_*` <-> `report.pipeline` / `ingest.workbook_context` -> WEAK COUPLING -> Shared internal functions, script-specific validation behavior.

`scripts/inspect_workbook.py` <-> `ingest` layer -> WEAK COUPLING -> Diagnostic use of workbook reading concepts, not full QC execution.

API server / scheduler / background workers <-> QC pipeline -> NO COUPLING -> No such runtime entry points were found in the current repository.

Transcript/history/report-export maintenance scripts <-> QC pipeline -> NO COUPLING -> They support collaboration or documentation, not system startup.

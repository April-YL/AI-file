# 固定资产质检 Agent

这是一个面向固定资产审计底稿的本地质检工具。它读取 Excel 底稿，执行可结构化的基础复核，输出质检报告，并在原底稿副本上标注问题位置。

项目目标是减少重复核对，不能替代审计人员对重大错报风险、证据充分性和会计估计的专业判断。

## 当前能力

- 读取整本固定资产底稿并识别汇总页、K.00 Lead、K.01 后推、K.02 新增/处置和 K.03 折旧测试等程序页。
- 通过规则注册表和分程序 runner 执行确定性检查，结论仅使用 `PASS`、`WARN`、`FAIL`、`NEED_REVIEW`。
- 输出 JSON/HTML 质检结果、执行台账和带批注的 `*_qc_annotated.xlsx` 底稿副本。
- 提供 Streamlit 本地界面，用于上传底稿、执行质检、查看 findings 和下载交付物。
- 可选接入 OpenAI 兼容 LLM API；LLM 只作辅助说明或人工复核支持，不得单独把规则 `FAIL` 改为 `PASS`。

当前仍是持续开发中的审计辅助工具。K.00–K.03 已有不同程度的自动检查，但并非 checklist 每个质检点都已自动化；准确覆盖范围以 [`src/rules/registry.py`](src/rules/registry.py)、[`docs/qc-checklist.md`](docs/qc-checklist.md) 和 [`docs/planning/program-qc-coverage-index.md`](docs/planning/program-qc-coverage-index.md) 为准。

## 快速开始

要求 Python 3.10 或更高版本。

```powershell
git clone https://github.com/April-YL/AI-file.git
cd AI-file
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ui]"
```

Windows 用户也可以双击根目录的 `启动质检界面.bat`，或执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-ui.ps1
```

命令行最小示例：

```powershell
fa-qc-run tests\fixtures\workbook_with_lead.xlsx
```

读取任意底稿前，建议先查看工作簿结构：

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_workbook.py --path ".\固定资产质检agent\资料库\K1 SWP 固定资产 202YMMDD XYZ公司.xlsx"
```

当前启动脚本和业务使用主要按 Windows 验证。Python 包和 CLI 未刻意绑定盘符；Linux/macOS 可按标准 Python 方式安装，但图形界面、中文 Excel 和底稿导出应由使用者另行验证。

## 输出

- 结构化质检报告：findings、严重级别、程序维度汇总、执行台账和复核建议。
- 底稿标注副本：保留原件，默认生成 `*_qc_annotated.xlsx`，包含 Comments 工作表和单元格批注。

系统展示“已执行”只代表该规则在本次运行中具备输入并实际运行，不代表审计程序整体已充分完成。

## 资料与数据安全

仓库中的 `固定资产质检agent/资料库/` 随代码提供标准底稿、SOP、checklist 和程序执行参考资料，便于理解规则来源。案例库、真实项目底稿、质检输出和本地 `.env` 不应提交。

- 不提交真实资产编号、部门、人员、合同、发票或客户信息。
- LLM 密钥只放在根目录 `.env`，不得写入代码或文档。
- 使用真实底稿前，应确认本地部署、网络和 LLM 端点符合项目数据要求。

详见 [`docs/data-security.md`](docs/data-security.md)。

## 文档入口

- [新人上手](docs/ONBOARDING.md)：安装、运行、资料入口和当前能力。
- [最新交接](docs/handoff/latest.md)：当前基线、已知边界和下一步。
- [项目进度](docs/progress.md)：里程碑状态。
- [治理方案](docs/architecture/fa_qc_governance_plan.md)：规则真源、执行证据与 UI 展示边界。
- [Agent 协作规则](AGENTS.md)：修改、测试和 Git 操作约束。

## 拓展到其他科目

其他科目可以复用以下框架：

1. `ingest`：识别工作表、字段和输入证据。
2. `rules`：登记并执行确定性规则，输出统一 finding。
3. `execution_ledger` / observation：记录本次实际执行事实和取数证据。
4. `report`：生成报告、UI 展示和底稿标注副本。

固定资产的 rule_id、字段映射、SOP 口径和严重级别不能直接复制为其他科目的审计结论。新增科目应建立独立的领域词典、checklist 映射、fixture 和规则测试，并遵守治理准入要求。

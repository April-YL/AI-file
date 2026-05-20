# 最新交接

> 每次收工前更新本文。新成员接手先读 `docs/ONBOARDING.md`，再读 `AGENTS.md` 和本文。

## 项目终态（对齐）

固定资产质检 Agent 的完整目标是：

- **输入**：固定资产底稿 + 必要辅助文件（checklist、TE/SAD 等）。
- **过程**：按 `docs/qc-checklist.md` 检查是否存在 findings，模拟质检人员复核底稿。
- **必交付**：
  1. **质检报告**（findings 清单、严重级别、程序/资产维度汇总、复核建议）。
  2. **底稿标注**（在原底稿副本上批注/高亮问题位置，与 findings 一一对应）。

当前代码完成 **M1 切片** + **M2a Demo 流水线**（`fa-qc-run` + Excel FA list/汇总/Lead + JSON/HTML 报告）；**Streamlit 本地 UI 已可用**；**底稿标注尚未实现**。

## 当前状态

- Git 仓库已初始化并关联 GitHub 远程。
- 资料库与案例库诊断、SOP/checklist/字段映射文档已沉淀。
- `src/ingest/`：sheet 分类、字段映射、底稿诊断 CLI、FA list CSV/Excel 解析（`load_fa_list_from_workbook`）。
- `src/rules/` + `src/report/`：首批 3 条 FA list 规则 + JSON 报告；**`fa-qc-run` CLI 已可用**。
- 规则字典映射：`docs/rule-dictionary-mapping.md`、`src/rules/registry.py`、`tests/fixtures/rule_dictionary_*.csv`
- **距终态差距**：全 checklist 覆盖、正式质检报告 Excel 版、**底稿标注回写**、汇总/K.01 规则、整本多 sheet 端到端。

## 已完成

- 项目长期上下文：`AGENTS.md`（已按终态目标与必交付项更新）
- 项目结构说明：`docs/PROJECT_STRUCTURE.md`
- 领域词典、架构、任务与进度文档
- 质检 checklist：`docs/qc-checklist.md`
- 底稿字段映射：`docs/workpaper-fields.md`
- 案例库底稿读取诊断（6 份小型底稿）
- `src/ingest/`（含 `fa-qc-diagnose`）、`tests/ingest/`
- M1 首批规则与单测：`fa_list_required_fields`、`unique_asset_id`、`asset_value_consistency`
- `src/report/`：`run_fa_list_qc`、JSON 报告结构
- 脱敏 fixture：`tests/fixtures/fa_list_*.csv`、`tests/fixtures/fa_list_mixed.xlsx`
- **M2a Demo**：`fa-qc-run`（`report/cli.py`）、`load_fa_list_from_workbook`、`read_worksheet_rows`
- ingest：K.01 后推（`RollforwardColumnBinding` / 期初·期末合计、表头期初·期末加权识别）
- ingest：**汇总页单主表**（表头行打分遍历、列角色 `column_bindings`、`last_data_row`、连续空行结束主表、空列表头误匹配修复）
- rules：**AE-003** `psp_completion` + `psp_sheet_matcher`：汇总页标「已执行」时与工作簿 sheet 名称规范化/模糊勾稽；读盘路径与表名由 `run_workbook_qc` 传入；弱匹配 `NEED_REVIEW`、无匹配 `FAIL`、目标表过空 `WARN`
- report：**`summary_sheet_section`**（JSON / 人工核对 HTML / `fa-qc-run` 终端 / Streamlit「汇总页 (PSP)」页签）：汇总页 ingest 元数据、程序表、列绑定、AE-003 整体结论与 findings
- **本地 UI**：`fa-qc-ui`（`src/report/ui_app.py`）、`scripts/start-ui.bat`、根目录 `启动质检界面.bat`；多文件上传、问题清单/人工核对/HTML 预览与下载
- **Lead + 人工核对**：`lead_sheet.py`、`manual_review.py`、`export_review_html.py`；AE-001/002 规则与 `workbook_with_lead.xlsx` fixture

## 进行中（M2a = Agent P1）

- **字段映射与读取准确性**（接入主线，已起步）：
  - 扩展 `FIELD_SYNONYMS`（案例库表头：卡片编码、入账日期、未税成本、处置情况等）
  - `field_mapping_policy.py`：按 sheet 禁止误映射；使用寿命/date 误匹配防护
  - 回归：`tests/fixtures/field_mapping_case_headers.json` + `test_field_mapping.py`
  - **待做**：对案例库 6 份底稿重跑 `fa-qc-diagnose` 更新 `case-workpaper-diagnostic.md`
- **整底稿流水线**：K.01 后推 ingest 已具备（`RollforwardColumnBinding` / 期初·期末合计、`sheet_classifier` 期初/期末表头加权）；**下一步 ingest**：K.00 Lead 内分块（基础信息 / CRA / 两期 lead 表等）

## 下一步（M2a 验收导向）

1. **ingest（优先）**：按 `docs/case-workpaper-diagnostic.md` 完善字段映射；新增/更新 `tests/ingest/test_field_mapping.py` 与脱敏 fixture
2. ingest：K.01 后推表数据对象
3. rules：`rollforward_exists` / `rollforward_columns_complete`
4. report：Excel 报告 + openpyxl 批注回写
5. 案例库 1～2 份小型底稿端到端回归（`fa-qc-run` / UI）

**暂缓为主战场**：单独扩展 FA list 规则条数；TE/Canvas、证据充分性等标 NEED_REVIEW（**M3 由大模型 Agent 承接**）。

## 后续方向（M3 大模型 Agent）

- 已采纳 ADR-0002；详见 **[docs/llm-agent-roadmap.md](llm-agent-roadmap.md)**（含**三层 LLM 分工**：映射 / 规则语义 / checklist）。
- **M3a 已落地**：`src/llm/config.py`、`client.py`、`redact.py`；`fa-qc-run --llm` → 报告 `llm_enrichment`（**层 4 叙述**）。
- **M3b 已做（规则层）**：汇总页、`psp_completion`（AE-003，含 sheet 名称勾稽与空表 WARN）、整本 `run_workbook_qc`；`--llm` 时附带汇总程序表上下文。
- **人工核对摘录**：Lead → `manual_review_sections`（AE-001/002）+ HTML 页。

### M3c 任务列表（三层 LLM + 编排）

> 完整说明与验收标准见 [llm-agent-roadmap.md § M3c](llm-agent-roadmap.md#m3c--三层-llm--agent-编排)。**severity 仍仅由 rules 判定**；LLM 不将 FAIL 改为 PASS。

| ID | 状态 | 任务 | 负责人 | 依赖 |
| --- | --- | --- | --- | --- |
| C1 | 待做 | `src/llm/map_headers.py` + 映射 prompt + mock 单测 | 待定 | M3a |
| C2 | 待做 | ingest 挂钩：`--llm-map`；超阈值 `unmapped_headers` 触发；finding `ingest_header_mapping_review` | 待定 | C1、M2a 字段映射 |
| C3 | 待做 | `src/llm/rule_review.py`：AE-003 等 `NEED_REVIEW` 附加 `llm_rationale`；`--llm-rules` | 待定 | M3a |
| C4 | 待做 | `src/llm/checklist_assess.py`：对照 registry/checklist 输出 `checklist_assessments[]`；`--llm-checklist` | 待定 | 业务口径 |
| C5 | 待做 | `src/llm/orchestrate.py`：串联 C1–C4 + `review.py`；`--llm-all` | 待定 | C1–C4 |
| C6 | 待做 | 报告 schema 扩展（`checklist_assessments`、issue 上 `llm_*` 可选字段）；JSON/HTML 展示 | 待定 | C4 |
| C7 | 待做 | Tool use：`get_sheet_summary`、`list_findings`、`get_checklist_item`；调用审计日志 | 待定 | C5 |
| C8 | 待做 | UI 细粒度 LLM 勾选（映射 / 规则 / checklist / 报告） | 待定 | C5 |
| C9 | 待做 | `tests/llm/` 扩充；与 ADR-0002、roadmap 对齐 | 待定 | C1–C8 |

**建议实施顺序**：C1→C2（配合字段映射）→ C3 → C4→C6 → C5/C7/C8。

**与 M2a 并行**：K.01 `rollforward_*`、Excel 报告、底稿批注仍为规则/报告主线，**不阻塞** M3c 文档与 C1 原型。

## 已知问题

- **底稿标注**：未实现，为终态硬缺口。
- 质检报告尚无面向业务人员的 Excel 版；当前以 JSON 结构为主。
- Excel 底稿已支持 FA list + 汇总页（AE-003）；K.01 后推、底稿标注仍未接入。
- `fa-qc-run` 在 overall=FAIL 时退出码 3（便于 CI）；PASS/WARN 为 0。
- PDF 程序指引未抽取正文，可能需 OCR。
- A 公司底稿约 42MB 已跳过，需读取性能优化。
- 处置清单等场景：`单据编号` 不得误映射为 `asset_id`。

## 相关文件

- `AGENTS.md` — 终态目标与必交付项
- `docs/qc-checklist.md` — findings 检查来源
- `docs/workpaper-fields.md`、`docs/architecture.md`
- `src/ingest/records.py`、`src/report/cli.py`、`src/report/ui_app.py` — 流水线与 UI 入口
- `scripts/start-ui.bat`、`启动质检界面.bat` — 本地界面启动
- `src/ingest/`、`src/rules/`、`src/report/`
- `tests/rules/`、`tests/ingest/`、`tests/fixtures/`
- `docs/ONBOARDING.md`
- `docs/llm-agent-roadmap.md` — 三层 LLM 分工与 M3c 任务（C1–C9）

## Demo 命令（本次收工验证）

```powershell
pip install -e ".[dev,ui]"
pytest tests/ingest tests/rules -q

# 图形界面（选文件 → 一键质检）
fa-qc-ui

# 命令行
fa-qc-run tests/fixtures/workbook_with_lead.xlsx
```

输出 JSON 含 `dict_rule_code`（如 `FA-RC-001`）、`severity`、资产级汇总。

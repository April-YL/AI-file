# 最新交接

> 每次收工前更新本文。新成员接手先读 `docs/ONBOARDING.md`，再读 `AGENTS.md` 和本文。

## 项目终态（对齐）

固定资产质检 Agent 的完整目标是：

- **输入**：固定资产底稿 + 必要辅助文件（checklist、TE/SAD 等）。
- **过程**：按 `docs/qc-checklist.md` 检查是否存在 findings，模拟质检人员复核底稿。
- **必交付**：
  1. **质检报告**（findings 清单、严重级别、程序/资产维度汇总、复核建议）。
  2. **底稿标注**（在原底稿副本上批注/高亮问题位置，与 findings 一一对应）。

当前代码完成 **M1 切片** + **M2a 流水线**（`fa-qc-run` / `fa-qc-ui` + Lead/汇总规则 + **底稿标注首版** + 精简 HTML + 案例库 Lead 回归）。

## 当前状态

- Git 仓库已初始化并关联 GitHub 远程。
- 资料库与案例库诊断、SOP/checklist/字段映射文档已沉淀。
- `src/ingest/`：sheet 分类、字段映射、底稿诊断 CLI、FA list CSV/Excel 解析（`load_fa_list_from_workbook`）。
- `src/rules/` + `src/report/`：首批 3 条 FA list 规则 + JSON 报告；**`fa-qc-run` CLI 已可用**。
- 规则字典映射：`docs/rule-dictionary-mapping.md`、`src/rules/registry.py`、`tests/fixtures/rule_dictionary_*.csv`
- **距终态差距**：全 checklist 覆盖、正式质检报告 Excel 版、标注精度（单元格坐标/共性合并规则）、K.01 规则余量。

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
- ingest：**K.00 Lead 锚点分块**（`lead_sheet_blocks.py` + 扩展 `LeadSheetDataset`：6 块基础信息/CRA/预期+波动门槛/引导主表/波动说明/调整汇总；默认读 200 行）
- ingest：**Lead 版式变体** `no_cra_te_volatility`（案例 A：无 CRA 区，波动幅度金额 = TE）；`-`/`N/A` 空串不再误匹配锚点（修复 cra/mov/exp 全 0）
- ingest：**案例库 K1 SWP 回归**（B/C/D/E/F/G：cra≈5、mov≈4、exp≈7；A：cra=0、layout=no_cra_te_volatility）
- 文档：**Lead 质检规则规划** `docs/planning/lead-qc-rules.md`（`FA_lead规则说明` + GAM + **FY26 SOP K1.00【01】～【05】对照与遗漏清单**）
- report：**`summary_sheet_section`**（JSON / 人工核对 HTML / `fa-qc-run` 终端 / Streamlit「汇总页 (PSP)」页签）：汇总页 ingest 元数据、程序表、列绑定、AE-003 整体结论与 findings
- **本地 UI**：`fa-qc-ui`（`src/report/ui_app.py`）、`scripts/start-ui.bat`、根目录 `启动质检界面.bat`；多文件上传、问题清单/人工核对/HTML 预览与下载
- **Lead + 人工核对**：`lead_sheet.py`、`manual_review.py`、`export_review_html.py`；AE-001/002 规则与 `workbook_with_lead.xlsx` fixture
- **Lead P0 规则 + 报告块**：模块 1–5 共 13 条 `run_lead_rules`；`lead_sheet_report.py`；注册表 `LEAD-001`～`LEAD-010` + AE-004 已实现
- **底稿标注 v0**：`export_annotated_workbook.py` — `Comments【归档前删除】`（其他程序逐条 + FA list 共性行）+ `Comments【FA list】`（明细）+ 单元格批注；文档 [workpaper-annotation.md](workpaper-annotation.md)
- **UI（质检员向）**：Findings 分程序、人工复核摘录（AE-001/002 + 基准信息）、双 Comments 说明、标注底稿下载
- **安全/LLM**：`docs/data-security.md`、`.env.example`、`python-dotenv`、`fa_qc_ui` 入口、`scripts/test_llm_connection.py`
- **案例库 Lead 回归**：`scripts/run_case_lead_regression.py`、`artifacts/case_lead_regression.md`
- **Lead LEAD-004/007 修复（2026-05-26）**：ingest「上期末审定数」列优先于「期末审定数」子串；`sheet_ref` 同步进 `values`；GAM TT/TE **闭区间 + 浮点容差**；LEAD-007 读 `row.sheet_ref`、**净值行不要求索引号**；UI `_QC_CACHE_VERSION` +「清除质检缓存」
- **汇总页 AE-003 与 Comments 可用性修复（2026-05-28）**：
  - `psp_completion`：行级检查覆盖全部有效程序行；修复合并单元格场景（`K.02.1/1a`、`K.02.2/2a`）执行状态继承导致的误报。
  - K.03 折旧测试口径：SAP/TOD 二选一；新增 `execution_status_consistency`，当汇总页勾选与底稿 TOD 证据冲突时输出 `NEED_REVIEW`（不再直接按 waiver 误报）。
  - TOD 证据识别升级为“编号 + 语义 + 内容”组合，不依赖单一 sheet 命名（支持 by-item/逐项重算等变体）。
  - `export_annotated_workbook`：`Question/Comment` 短标题化（规则码映射 + 通用压缩）、去除冗长“模型提示”；`Comments【归档前删除】` 排序改为“汇总 → Lead → 其他”。
  - 验证：`tests/rules/test_psp_completion.py`（21 通过）、`tests/report/test_export_annotated_workbook.py`（8 通过）；实测 `...G科技-测试0526-01...` 输出中 `K.02.2a` 误报消失，K.03 改为一致性提示项。

## 进行中（M2a = Agent P1）

- **字段映射与读取准确性**（接入主线，已起步）：
  - 扩展 `FIELD_SYNONYMS`（案例库表头：卡片编码、入账日期、未税成本、处置情况等）
  - `field_mapping_policy.py`：按 sheet 禁止误映射；使用寿命/date 误匹配防护
  - 回归：`tests/fixtures/field_mapping_case_headers.json` + `test_field_mapping.py`
  - **Lead 回归表**：`artifacts/case_lead_regression.md`（B–G 共 6 份；A 42MB 永久跳过）
  - **待做**：对案例库 6 份底稿重跑 `fa-qc-diagnose` 更新 `case-workpaper-diagnostic.md`
- **Lead 质检规则（模块 1–5 P0）**：含 `lead_check_with_a3_row`（ingest 摘录 Check with A3/Diff/Notes + Diff≠0/缺说明 FAIL）；其余 `lead_*`、AE-004、`lead_rollforward_tb_reconciliation`；`lead_runner` + `lead_sheet_section`
- **K.01 规划文档（2026-05-26）**：`docs/planning/k01-qc-rules.md`、`docs/planning/k01-workpaper-layouts.md`
- **K.01 P0 规则（2026-05-26）**：ingest 增强（审2/审3 列块、变动行、多 sheet 优选）；`rollforward_exists`、`rollforward_columns_complete`（L1）；`rollforward_runner` + pipeline；registry **GL-006/007** implemented

## 下一步（M2a 验收导向）

1. **K.01**：案例库 B–G `fa-qc-run` 回归；`rollforward_abnormal_amounts`（GL-005）；可选 `rollforward_sheet_report` / UI 页签
2. **rules（Lead 余量）**：`lead_fluctuation_notes_refs`、`lead_arp_three_triggers`；`rollforward_abnormal_amounts`；Streamlit Lead/K.01 页签（可选）
2. **M3c（P1）**：`--llm-rules`、`--llm-checklist`（见 roadmap）；**非**优先扩展 `--llm` 报告叙述
3. **ingest**：案例库字段映射回归
4. report：独立 Excel 质检报告（非标注副本）、标注 Cell Ref. 与共性合并规则优化
5. 案例库端到端回归（`fa-qc-run` / UI）；Lead 见 `python scripts/run_case_lead_regression.py`

**暂缓为主战场**：单独扩展 FA list 规则条数。

## 产品优先级：LLM 与质检准确度（2026-05-21 确认）

| 优先级 | 内容 |
| --- | --- |
| **P0** | **质检点判对**：`rules`（Lead `lead_*`、K.01 `rollforward_*`、AE-003 等）+ ingest 稳定 |
| **P1** | **LLM 挂质检点**：`--llm-rules`（语义项）、`--llm-checklist`（逐条 K1） |
| **P2** | `--llm-map`（表头映射） |
| **P3** | `--llm` 报告叙述（`llm_enrichment`，**已实现但非重点**） |

**说明**：勾选「大模型增强」**不等于**全流程已用模型把关；当前 `--llm` 仅在规则跑完后写摘要，**不提升各检查点 FAIL/WARN 判定**。终态见 [llm-agent-roadmap.md](llm-agent-roadmap.md)。

## 后续方向（M3 大模型 Agent）

- 已采纳 ADR-0002（含 2026-05-21 优先级补充）；详见 **[docs/llm-agent-roadmap.md](llm-agent-roadmap.md)**。
- **M3a 已落地**：`src/llm/` 基础设施；`--llm` → 层 4 `llm_enrichment`（低优先级）。
- **M3b（规则层，P0）**：AE-003 ✅；Lead 自动规则、K.01 后推规则 **待做**（见 `docs/planning/lead-qc-rules.md`）。
- **人工核对摘录**：Lead AE-001/002 + HTML（Canvas 仍人工）。

### M3c 任务列表（LLM 主战场：ingest / 规则语义 / checklist）

> **severity 仅由 rules 判定**；LLM 不将 FAIL 改为 PASS。完整说明见 [llm-agent-roadmap.md § M3c](llm-agent-roadmap.md#m3c--三层-llm产品主战场)。

| ID | 优先级 | 状态 | 任务 |
| --- | --- | --- | --- |
| — | **P0** | 进行中 | M2a Lead/K.01 **确定性规则**（不依赖 LLM） |
| C3 | **P1** | 待做 | `rule_review.py` + `--llm-rules` |
| C4 | **P1** | 待做 | `checklist_assess.py` + `--llm-checklist` |
| C6 | P1 | 待做 | 报告展示 `checklist_assessments`、issue 上 `llm_*` |
| C1–C2 | P2 | 待做 | `map_headers` + `--llm-map` |
| C5,C7,C8 | P1 后 | 待做 | 编排、Tool、UI 细分开关 |
| C9 | 持续 | 待做 | `tests/llm/` |
| 层 4 | **P3** | 已实现 | `review.py` / `--llm`（维持，不加大投入） |

**建议实施顺序**：**P0 Lead/K.01 规则** → C3 → C4 → C6 → C1/C2 → C5/C7/C8。

## 已知问题

- **底稿标注**：首版已通（双 Comments + 批注）；无行号 finding、FA 合并粒度仍待业务确认。
- 质检报告尚无面向业务人员的独立 Excel 版；当前以 JSON + 标注副本为主。
- Excel 底稿已支持 FA list + 汇总页（AE-003）+ Lead 规则 + 标注导出。
- `fa-qc-run` 在 overall=FAIL 时退出码 3（便于 CI）；PASS/WARN 为 0。
- PDF 程序指引未抽取正文，可能需 OCR。
- A 公司底稿约 42MB 已跳过，需读取性能优化。
- 处置清单等场景：`单据编号` 不得误映射为 `asset_id`。

## 相关文件

- `AGENTS.md` — 终态目标与必交付项
- `docs/agent-collaboration.md` — **先答后改**协作约定
- `docs/qc-checklist.md` — findings 检查来源
- `docs/workpaper-fields.md`、`docs/architecture.md`
- `src/ingest/records.py`、`src/report/cli.py`、`src/report/ui_app.py` — 流水线与 UI 入口
- `scripts/start-ui.bat`、`启动质检界面.bat` — 本地界面启动
- `docs/workpaper-annotation.md`、`docs/data-security.md` — 标注交付与安全
- `src/report/export_annotated_workbook.py`、`scripts/run_case_lead_regression.py`
- `src/ingest/`、`src/rules/`、`src/report/`
- `tests/rules/`、`tests/ingest/`、`tests/fixtures/`
- `docs/ONBOARDING.md`
- `docs/llm-agent-roadmap.md` — 三层 LLM 分工与 M3c 任务（C1–C9）
- `docs/planning/lead-qc-rules.md` — K.00 分模块质检点、SOP 对照遗漏、M2 实现顺序
- `docs/planning/k01-qc-rules.md`、`docs/planning/k01-workpaper-layouts.md` — K.01 SOP 对照、版式 profile、P0 实现顺序

## Demo 命令（本次收工验证）

```powershell
pip install -e ".[dev,ui]"
pytest tests/ingest/test_lead_sheet.py tests/ingest/test_summary_sheet.py tests/rules -q

# 图形界面（选文件 → 一键质检）
fa-qc-ui

# 命令行
fa-qc-run tests/fixtures/workbook_with_lead.xlsx
```

输出 JSON 含 `dict_rule_code`（如 `FA-RC-001`）、`severity`、资产级汇总。

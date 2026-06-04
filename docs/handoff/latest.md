# 最新交接

> 每次收工前更新本文。新成员接手先读 `docs/ONBOARDING.md`，再读 `AGENTS.md` 和本文。

## 项目终态（对齐）

固定资产质检 Agent 的完整目标是：

- **输入**：固定资产底稿 + 必要辅助文件（checklist、TE/SAD 等）。
- **过程**：按 `docs/qc-checklist.md` 和 SOP 执行基础 review 与可结构化检查，识别 findings；需要审计判断或风险判断的事项标为 `NEED_REVIEW`，交由质检人员重点复核。
- **定位**：让 Agent 承担重复性核对和基础检查，帮助质检人员把更多时间用于高风险事项识别、重大审计判断和风险管理。
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

- **K.01 识别层 + P0 规则（2026-05-28）**：
  - ingest：`section_presence` / `section_regions` / `section_conflicts` / `recognition_confidence`；b1 区内合计/表头防干扰
  - 规则：`rollforward_exists`、`rollforward_columns_complete`、`rollforward_abnormal_amounts`（GL-006/007/005）；`rollforward_sheet_section`
  - 回归：`scripts/run_case_rollforward_regression.py`、`tests/ingest/test_case_rollforward_regression.py`
- **K.01 GL-002 首版（2026-06-02）**：
  - 规则：`rollforward_fa_list_reconciliation` 已接入 K.01 runner；主检查读取 K.01 表3（FA list 汇总表与后推明细表 check）结果。
  - 口径：表3 check 为 0 或差异金额不超过 SAD 时通过；超过 SAD 且无 Notes 时输出 `FAIL`；超过 SAD 但有 Notes 时通过（Notes 符号/格式不限制）。表3不可读时，检查表2是否存在/是否有 SUMIF 汇总金额，并把 Agent 自算 FA list 合计仅作为 `NEED_REVIEW` 兜底提示。
  - 验证：2026-06-03 更新口径后，`tests/rules` 123 通过；`tests/ingest/test_workbook_ingest.py --basetemp .pytest_tmp` 12 通过；`tests/report/test_workbook_pipeline.py --basetemp .pytest_tmp_report` 1 通过。
- **K.01 TB check 读取层（2026-06-02）**：
  - ingest：新增 `tb_reconciliation_detected`、`tb_reconciliation_confidence`、`tb_difference_values`、`tb_difference_row`、`tb_notes_text_present`、`tb_notes_row`、`tb_notes_text`。
  - 口径：只有 TB/试算表口径和“差异”同时出现，才视为可靠 TB check；仅有“变动金额”时不强判，后续规则应给 `NEED_REVIEW` 或人工复核提示。
  - 报告：`rollforward_sheet_section` 已输出 TB check 摘录字段，供后续 `rollforward_difference_over_sad` 使用。
  - 验证：`tests/rules` 108 通过；`tests/ingest/test_workbook_ingest.py --basetemp .pytest_tmp` 12 通过；`tests/report/test_workbook_pipeline.py --basetemp .pytest_tmp_report` 1 通过。
- **K.01 GL-008 >SAD Notes 检查（2026-06-02）**：
  - 规则：`rollforward_difference_over_sad` 已接入 K.01 runner，并从 K.00 Lead 读取 SAD。
  - 口径：TB check 差异未超过 SAD 不报；超过 SAD 且无 Notes 输出 `FAIL`；超过 SAD 且有 Notes 输出 `NEED_REVIEW`，由质检人员判断说明是否充分。
  - 兜底：TB check 或 SAD 读不可靠时输出 `NEED_REVIEW`，不直接判 PASS/FAIL。
  - 验证：`tests/rules/test_rollforward_rules.py` 27 通过；`tests/rules` 115 通过；`tests/ingest/test_workbook_ingest.py --basetemp .pytest_tmp` 12 通过；`tests/report/test_workbook_pipeline.py --basetemp .pytest_tmp_report` 1 通过。
- **K.01 GL-004 表4折旧费用与利润表/TB核对（2026-06-03）**：
  - ingest：新增 `table4_pl_amounts`、`table4_pl_total`、`table4_rollforward_depreciation`、`table4_difference`、`table4_notes_text` 等表4读取字段；表4区域定位不到时，会按“折旧费用与利润表科目核对 / 金额 / 累计折旧科目-本年计提 / 差异 / Notes”兜底定位。
  - 规则：`rollforward_depreciation_pl_reconciliation` 已接入 K.01 runner，并从 K.00 Lead 读取 SAD。
  - 口径：表4差异为 0 或差异金额不超过 SAD 时通过；超过 SAD 且无 Notes 输出 `FAIL`；超过 SAD 但有 Notes 时通过（Notes 符号/格式不限制）；表4差异或 SAD 读不到时输出 `NEED_REVIEW`。
  - 报告：`rollforward_sheet_section` 已输出表4 PL/TB 核对摘录字段。
  - 验证：`tests/rules/test_rollforward_rules.py` 38 通过；`tests/rules` 131 通过；`tests/ingest/test_workbook_ingest.py --basetemp .pytest_tmp` 12 通过；`tests/report/test_workbook_pipeline.py --basetemp .pytest_tmp_report` 1 通过。
- **输出准确性修复（2026-06-03）**：
  - FA list：累计折旧按贷方负数列示时不再触发金额非负 FAIL；净值勾稽按 `原值 - abs(累计折旧) - abs(减值准备)`；读取阶段过滤 `资产类别重分类`、合计/小计等非资产明细行。
  - K.01：修复表2/表3横向并排模板读取；表3 check 可直接读取 0 值；表1期末合计不再被右侧 check 列误识别为 0；TB 区域锚点按标准顺序切分，避免表4差异被当作后推净值异常。
  - 规则：表4折旧费用与利润表核对差异超过 SAD 且 Notes 写“差异小于 SAD”时输出 `FAIL`；超过 SAD 但有 Notes 时输出 `NEED_REVIEW`，由质检人员判断说明是否充分。
  - Lead/汇总页：折旧方法/使用寿命“无变化”不再误报；折旧费用说明中的“无重大处置资产”不再被误判为“无重大波动”；减少/处置仅有方向无原因会提示；未启用 LLM 时，汇总页明显空泛的不执行理由（如仅小于 TE、仅无减值迹象）由规则层先给 WARN。
  - Lead Notes：引导主表按行读取 `基于波动幅度判断，是否进一步调查？` 与 `基于定性考虑判断，是否进一步调查？` 两列；任一列为“是”时，该行必须填写 Notes 且下方异常波动分析区需有对应编号；两列均为“否”时可不填 Notes；两列空白/无法识别时退回金额+比例阈值兜底。
  - 验证：`tests/rules -q --basetemp .pytest_tmp_rules` 140 通过；`tests/ingest/test_records_workbook.py tests/ingest/test_workbook_ingest.py -q --basetemp .pytest_tmp` 17 通过；`tests/report/test_workbook_pipeline.py tests/report/test_export_annotated_workbook.py -q --basetemp .pytest_tmp_report` 13 通过。实测 `...E锂原 - 测试0603.xlsx --no-llm`：issues 由 405 降至 14，FA list 批量误报消失，K.01 剩余 GL-008 `NEED_REVIEW` 与 GL-004 `FAIL`。
- **汇总页识别与 LLM 规则语义复核修复（2026-06-03）**：
  - 根因：`E锂原 - 测试0603.xlsx` 的汇总页真实表名为 `汇总 `（尾随空格）；名称识别命中 SUMMARY，但内容分类误判为 K.01 后推，导致 `ctx.summary=None`，AE-003/PSP 规则和汇总页 LLM 复核均未执行。
  - ingest：`load_summary_from_workbook` 改为“名称明确命中汇总时优先作为汇总候选”，且手动指定 `汇总` 时可宽松匹配真实表名 `汇总 `。
  - LLM：UI 文案改为“启用大模型规则语义复核”；汇总页 PSP 不执行理由的 LLM 输入新增 `workbook_context`，包含 Lead TE/SAD/CRA/TT/预期/波动表、K.01 后推摘要、TB/表4差异、新增/处置清单、跨表勾稽和工作表列表。
  - 实测：真实底稿只读验证 `summary_source='汇总 '`、`program_count=12`；行15 处置测试“本期处置资产净值小于TE”输出 WARN；行22 减值测试“本期无减值迹象”输出 WARN。
  - 验证：`tests/ingest/test_summary_sheet.py -q --basetemp .pytest_tmp_summary` 7 通过；`tests/ingest/test_summary_sheet.py tests/report/test_workbook_pipeline.py tests/llm/test_summary_psp_review.py -q --basetemp .pytest_tmp_summary_regression` 13 通过；`tests/llm -q --basetemp .pytest_tmp_llm_all` 24 通过。
- **Lead 调整汇总表 LLM 设计（M3c-a，2026-06-03）**：
  - 设计：`docs/planning/lead-adjustment-llm-design.md`（版式/借贷方向、direct vs indirect 跨科目、LEAD-017 门控）。
  - 代码：`src/ingest/lead_adjustment_grid.py`、`src/llm/lead_adjustment_review.py`、`src/rules/lead_adjustment_gating.py`；流水线先 LLM 再 `run_lead_rules`（门控合计）。
  - 规则：LEAD-018/019 注册；`FA_QC_LLM_ADJUSTMENT_PASSES=1|3`（默认合并 1 pass）。
  - 待做：脱敏 fixture（英文双列、跨科目 AA#）、`pytest tests/llm/test_lead_adjustment_payload.py` 回归、案例库实测。
- **Lead LLM 语义复核上下文增强（2026-06-03）**：
  - 根因：Lead LLM 原先主要读取 Lead 单页的预期分析、引导表和波动说明；对“预期方向是否与 K.01 实际后推一致”“异常波动说明是否有程序/清单支持”等问题，上下文不足。
  - LLM：新增 `build_lead_semantic_context()`；`lead_expectation_semantic` 与 `lead_fluctuation_notes_semantic` 的输入新增 `workbook_context`。
  - 上下文包括：汇总页 PSP 执行/选否情况、K.01 后推期初/期末/区块/TB 差异/表4折旧差异、新增/处置清单记录数和金额、跨表勾稽结果、工作簿 sheet 列表。
  - 口径：上下文不足时 prompt 要求返回 `unclear`，由规则输出 `NEED_REVIEW`；LLM 仍只辅助语义复核，不覆盖确定性规则的 `FAIL/PASS`。
  - 验证：`tests/llm/test_lead_review.py -q --basetemp .pytest_tmp_lead_llm` 6 通过；`tests/llm -q --basetemp .pytest_tmp_llm_all_lead_context` 25 通过；`tests/report/test_workbook_pipeline.py -q --basetemp .pytest_tmp_report_lead_llm` 1 通过。
- **外链底稿单元格批注 + Comments 跳转（2026-06-02）**：
  - report：`export_annotated_workbook` 不再因 A3/外部链接跳过业务表批注；改用 OOXML 原位注入传统 Excel 批注，避免 `openpyxl.save()` 重写外链。
  - Comments：`Comments【归档前删除】`、`Comments【FA list】`、`QC_Locator` 的 Cell Ref./Navigate 可作为内部跳转索引，点击定位到对应业务表单元格（当前默认 B 列）。
  - 兜底：若业务表已存在复杂批注/VML 结构，首版跳过该表单元格批注，findings 仍保留在 Comments/定位表。
  - 验证：`tests/report/test_export_annotated_workbook.py --basetemp .pytest_tmp` 12 通过。
- **程序质检覆盖文档（2026-05-28）**：`docs/planning/program-qc-coverage-index.md`（总索引）、`k01-six-block-qc-matrix.md`、`summary-sheet-qc-matrix.md`、`k02-k03-qc-matrix.md`（规划模板）；Lead 仍见 `lead-qc-rules.md`

## 进行中（M2a = Agent P1）

- **字段映射与读取准确性**（接入主线，已起步）：
  - 扩展 `FIELD_SYNONYMS`（案例库表头：卡片编码、入账日期、未税成本、处置情况等）
  - `field_mapping_policy.py`：按 sheet 禁止误映射；使用寿命/date 误匹配防护
  - 回归：`tests/fixtures/field_mapping_case_headers.json` + `test_field_mapping.py`
  - **Lead 回归表**：`artifacts/case_lead_regression.md`（B–G 共 6 份；A 42MB 永久跳过）
  - **待做**：对案例库 6 份底稿重跑 `fa-qc-diagnose` 更新 `case-workpaper-diagnostic.md`
- **Lead 质检规则（模块 1–5 P0）**：含 `lead_check_with_a3_row`（ingest 摘录 Check with A3/Diff/Notes + Diff≠0/缺说明 FAIL）；其余 `lead_*`、AE-004、`lead_rollforward_tb_reconciliation`；`lead_runner` + `lead_sheet_section`
- **K.01 M2b（区块 2–6 勾稽）**：TB check 读取层、`rollforward_difference_over_sad`、GL-004 表4折旧核对已加；下一步做 GL-002 表3模板变体增强、TE 路由、Notes 充分性/折旧分摊合理性（见 `k01-six-block-qc-matrix.md`）

## 下一步（M2a 验收导向）

1. **K.01 M2b**：GL-002 表3模板变体增强、>TE 路由、Notes 充分性/折旧分摊合理性；识别置信度/锚点去重优化
2. **rules（Lead 余量）**：`lead_fluctuation_notes_refs`、`lead_arp_three_triggers`；Streamlit K.01 页签（可选）
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

## 2026-06-03 输出结果优化 0603-02 修复沉淀

本轮聚焦 UI 复测与 `E:\FAQC\输出结果优化0603-02` 中的 5 类误报/漏报：

- **Comments Cell Ref. 为空**：Lead 必填项、重要性、CRA/TT 等规则已补充 `source_row`，Comments 表应能定位到对应行。
- **Lead 预期分析误要求“减值准备”**：Lead LLM 语义复核提示已明确，标准 Lead 不要求单独对“减值准备”逐行建立预期；不得仅因缺少该项预期分析判异常。
- **LEAD-017 调整事项误判**：Lead 调整事项汇总表读取与规则层均过滤“本年度不涉及审计调整”等结论性文字，以及 TE/SAD 说明类 note；避免把非调整明细当作调整事项。
- **K.01 TB 与后推明细表差异漏报**：TB check 已读取差异单元格明细（如 `E43`、`AC43`），并检查相邻位置是否有 Note/NB 标识；超过 SAD 且无 Note 标识时输出 `GL-008 FAIL`。
- **K.01 Notes 错配**：TB check 不再使用远处表4折旧费用核对 Notes 作为 TB 差异说明；`B85` 应保留给折旧费用与利润表核对差异。
- **标注副本 XML 稳定性**：修复 OOXML 写入批注时可能重复插入 `xmlns:r` 导致 xlsx 解析失败的问题。

已验证：

- `.\.venv\Scripts\pytest.exe tests\rules\test_rollforward_rules.py -q --basetemp .pytest_tmp_rollforward_fix`：42 passed
- `.\.venv\Scripts\pytest.exe tests\rules\test_lead_internal_closure.py tests\ingest\test_lead_sheet.py -q --basetemp .pytest_tmp_lead_fix`：25 passed, 1 skipped
- `.\.venv\Scripts\pytest.exe tests\llm\test_lead_review.py -q --basetemp .pytest_tmp_lead_llm_fix`：6 passed
- `.\.venv\Scripts\pytest.exe tests\report\test_ooxml_workbook.py tests\report\test_export_annotated_workbook.py -q --basetemp .pytest_tmp_ooxml_fix`：15 passed

待 UI 复测重点：

- 汇总页 PSP 选否理由仍需确认大模型语义复核是否在 UI 参数中实际启用。
- Lead 调整事项汇总表若出现真实复杂借贷/跨科目调整，后续继续接入 `lead_adjustment_review` 的 LLM 判断。
- K.01 TB 差异若同时存在多行超过 SAD，当前会列示全部无 Note 标识的差异单元格，复测时重点看是否符合审计口径。

## 2026-06-04 K.02 新增/处置基础诊断沉淀

本轮开始补 K.02 新增测试诊断，按 SOP 将新增测试理解为三表程序包：`新增清单`、`K.02.1 新增测试`、`K.02.1a 新增选样输出`；处置测试同理为 `处置清单`、`K.02.2 处置测试`、`K.02.2a 处置选样输出`。

已完成：

- **K.02 程序包完整性**：新增 `addition_test_package_complete`、`disposal_test_package_complete`，当汇总页显示新增/处置测试已执行时，分别检查三表链条是否存在；支持名称变体，如 `K.02.1 细节测试`、`K.02.1b 新增清单`、`新增抽样输出结果`、`K.02.2b 减少清单`、`处置抽样输出结果`。
- **处置 sheet 识别补强**：`sheet_classifier` 支持 `K.02.2b 处置清单`、`K.02.2b 减少清单` 等变体，不把新增选样输出误当作处置选样输出。
- **新增清单字段完整性**：新增 `addition_required_fields`，检查新增清单必需字段：固定资产类别、编号、名称、入账开始日期、原值、新增方式。
- **新增总体同质性提示**：新增 `addition_population_homogeneity`，对在建工程转入、企业合并、调拨、重分类等非购置新增输出 `NEED_REVIEW`，提示确认是否单独分总体、索引其他 PSP/OSP 或设计额外程序。
- **ingest 支持**：`AssetRecord` 与 `parse_fa_list_rows(..., sheet_kind=ADDITION_LIST)` 已保留 `addition_method`（新增方式），供规则使用。
- **流水线接入**：`run_workbook_qc` 已接入 K.02 程序包完整性与新增清单基础规则；规则元数据已登记在 `src/rules/registry.py`。

已验证：

- `.\.venv\Scripts\pytest.exe tests\rules\test_addition_test_package.py tests\ingest\test_sheet_classifier.py -q --basetemp .pytest_tmp_k02_package`：16 passed
- `.\.venv\Scripts\pytest.exe tests\rules\test_addition_rules.py tests\ingest\test_records_workbook.py -q --basetemp .pytest_tmp_addition_rules`：10 passed
- `.\.venv\Scripts\pytest.exe tests\report\test_workbook_pipeline.py -q --basetemp .pytest_tmp_addition_rules_pipeline`：1 passed

下一步建议：

- 继续做 `addition_rollforward_reconciliation`：新增清单购置新增合计 vs K.01 后推购置新增金额，差异超过 SAD 时提示调查。
- 读取 `K.02.1 新增测试` 与 `K.02.1a 新增选样输出` 的总体金额/样本列表，为 `addition_sample_match` 做准备。
- 后续再补处置清单字段完整性、处置总体同质性与处置清单 vs K.01 后推勾稽。

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
- `docs/planning/program-qc-coverage-index.md` — **程序质检覆盖总索引**（汇总 / Lead / K.01 / K.02 / K.03 开发进度）
- `docs/planning/k01-qc-rules.md`、`docs/planning/k01-workpaper-layouts.md`、`docs/planning/k01-six-block-qc-matrix.md` — K.01 SOP 对照、版式、六区块矩阵

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

# 最新交接

> 每次收工前更新本文。新成员接手先读 `docs/ONBOARDING.md`，再读 `AGENTS.md` 和本文。

## 固定资料入口

以后查标准底稿、SOP 和程序执行方法，不再靠全仓搜索，统一先看这里：

1. `固定资产质检agent/资料库/K1 SWP 固定资产 202YMMDD XYZ公司.xlsx`：标准底稿模板
2. `固定资产质检agent/资料库/FY26_SOP K1 SWP 固定资产.xlsx`：带 SOP 说明的标准包
3. `固定资产质检agent/资料库/固定资产程序执行方法指引.pdf`：程序执行方法
4. `固定资产质检agent/资料库/K1 check list.xlsx`：质检 checklist
5. `docs/audit-workflow.md`：把上面几份资料整理成了固定资产的流程索引

建议阅读顺序：

1. `docs/audit-workflow.md`
2. `docs/qc-checklist.md`
3. `docs/workpaper-fields.md`
4. 标准底稿模板和 SOP 原文件
5. 需要时再看案例库文件

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
- **K.01 M2b（区块 2–6 勾稽）**：TB check 读取层、`rollforward_difference_over_sad`、GL-004 表4折旧核对已加；**ingest 稳定优先**后再扩 GL-002 变体、TE 路由等（见 `k01-six-block-qc-matrix.md`）
- **K.02 ingest + 门控（2026-06-04）**：程序包执行路径门控（waived / documented_limited / full_expected）；处置/新增 QC 详细矩阵；P1 多期 sheet 路由；K.02.1/K.02.2 测试页轻量扫描与 `addition_test_sheet` ingest 接入
- **ingest 优先（案例库）**：处置 P0（清单字段、`disposal_common` 净值汇总、K.01 处置行勾稽）待矩阵评审后开发；见 `docs/planning/k02-disposal-qc-matrix.md`

## 下一步（M2a 验收导向）

1. **K.02 处置 ingest P0**（评审 `k02-disposal-qc-matrix.md` 后）：处置清单字段映射、`disposal_common`（出售+报废净值）、K.01 处置行勾稽输入；案例 B–G 回归
2. **ingest 修复**：`scripts/run_case_ingest_routing.py` 中 `FaListSheetCandidate` 下标 bug；B/F `addition_method` 映射
3. **K.01 M2b**：GL-002 表3模板变体增强、>TE 路由、Notes 充分性；识别置信度/锚点去重优化
4. **rules（Lead 余量）**：`lead_fluctuation_notes_refs`、`lead_arp_three_triggers`
5. **M3c（P1）**：`--llm-rules`、`--llm-checklist`（见 roadmap）
6. report：独立 Excel 质检报告、标注 Cell Ref. 与共性合并规则优化

**暂缓**：K.02.2 E14 结构化读取、大量 disposal rules、单独扩展 FA list 规则条数。

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

- 读取 `K.02.1 新增测试` 与 `K.02.1a 新增选样输出` 的总体金额/样本列表，为 `addition_sample_match` 做准备。
- 后续再补处置清单字段完整性、处置总体同质性与 `disposal_rollforward_reconciliation`。

## 2026-06-04 addition_rollforward_reconciliation（方案 A）

- **ingest**：`RollforwardSheetDataset.movement_transactions`；从 K.01 表1/变动区识别「购置」等交易行金额。
- **规则**：`addition_rollforward_reconciliation` — 购置类新增清单原值合计 vs K.01 购置行；不一致 `WARN`，超过 SAD 时在 message 提示调查；读不到任一侧 `NEED_REVIEW`。
- **接入**：`run_addition_rules(..., rollforward, lead)`；`reconciliation.py` 的 `addition_list_rollforward` 链接同步使用购置口径。
- **验证**：`pytest tests/rules/test_addition_rollforward_reconciliation.py tests/ingest/test_sheet_classifier.py -q --basetemp .pytest_tmp_p0`
- **案例库复测**：`python scripts/run_case_addition_reconciliation.py`（B 购置合计约 173 万非单类 2.5 万；E 应能识别新增清单）

## 2026-06-04 P0 分类与 K.01 购置合计修复

- **P0-1 / P0-1b**（`sheet_classifier.py`）：名称明确的「新增清单」「处置清单」「汇总」「Lead」「FA list」不再被后推表头内容覆盖为 `rollforward`。
- **P0-2**（`rollforward_sheet.py`）：K.01 表1 矩阵购置行按各类别 **审定列（每 3 列一组取末列）** 汇总，不再只取首个类别金额。
- **单测**：`test_sheet_classifier.py` 新增清单/处置/汇总/Lead 用例；`test_addition_rollforward_reconciliation.py` 矩阵购置汇总用例。

## 2026-06-04 案例库购置勾稽诊断与研发顺序（B–G）

**案例库路径**：`固定资产质检agent/案例库`（不入 Git）。回归产物：`artifacts/case_addition_reconciliation.md`、`artifacts/case_efg_diagnosis.json`。

| 案例 | 新增清单识别 | 典型问题（修复 P0 后快照） |
| --- | --- | --- |
| B | ✅「新增清单」 | K.01 购置为表1各类别审定合计（非单类 2.5 万）；清单侧购置行仍可能为 0，需查 `addition_method` |
| C | ✅ | 双套 24/25 底稿；K.01 购置合计与清单是否一致需业务确认 |
| D | ✅ | 同 C；原误读生产设备单列 |
| E（4 份） | ✅（P0-1 后） | 曾误标 rollforward；清单与 K.01 购置金额可一致 |
| F | ✅ | 多期 -24；清单购置 0 行 vs K.01 有购置 |
| G | ✅ `K.02.1b 新增清单` | 处置清单仍易误标 rollforward；K.01 与清单差异大需核对口径 |

## 2026-06-08 K.02.1 新增测试页 ingest 补强

本轮继续按“模板定结构，SOP 定口径，ingest 先读对”的方法完善 K.02.1 新增测试页与 K.02.1a Skywind 选样输出读取。

已完成：

- `K.02.1 新增测试`页已新增 6 个模块识别：执行路径、总体定义、金额勾稽、关键项目与代表性抽样、测试样本属性表、异常说明与结论。
- 测试样本表补充读取字段：总账账户代码、资本化日期、使用寿命、残值率、折旧方法、证据金额、证据描述、金额差异、属性结果。
- `K.02.1a 新增选样输出`按 Skywind 工具输出拆成 4 个模块识别：源数据与样本池摘要、抽样策略与样本量、总体与会计记录核对、已选取样本明细。
- K.02.1a 已选样本表补充读取字段：源样本号、抽样 ID、样本类型、资产类别、资产编号、资产名称、入账开始日期、使用寿命、残值率、原值、新增方式。
- 整本 ingest 摘要已输出 K.02.1 与 K.02.1a 的 `module_assessments`，用于后续 report 先展示“读到了哪些模块、识别状态如何”。
- 标准模板右侧 SOP/易错点说明区可能包含“差异”“剩余总体”等文字，会干扰金额锚点；已在 ingest 中优先限定左侧业务编制区，并要求金额/数量字段取到数值。
- K.02.1a 的 `sample_method` 已修复为读取业务区的 `随机抽样 (Random)`，不再误读右侧 SOP/易错点说明文字。

业务口径补充：

- 一般正式质检底稿中没有右侧 SOP 区域；该防护主要用于标准模板、训练模板和开发测试模板。
- 右侧 SOP 区防干扰不能被理解为真实底稿常见结构，也不能替代对真实底稿版式、锚点和交叉勾稽的校准。
- 程序包不完整不等于程序执行不到位：
  - I 科技：汇总页对新增测试/新增选样输出选“否”，理由为新增购置金额小于 SAD，其他新增已在在建工程底稿执行程序；应识别为 `summary_waived`。
  - H 公司：汇总页选“是”，但 K.02.1 新增测试中说明本期购置金额小于 TE/SAD，不再执行 TOD 测试；应识别为 `test_sheet_waiver_note`。
- K.02.1 当前模块识别状态属于 ingest 简单判断，不是规则结论；后续 rules 仍只输出 `PASS`、`WARN`、`FAIL`、`NEED_REVIEW`。

已验证：

- `.\.venv\Scripts\pytest.exe tests\ingest\test_addition_test_sheet.py -q --basetemp .pytest_tmp_k02_i_h_fix`：6 passed
- `.\.venv\Scripts\pytest.exe tests\ingest\test_workbook_ingest.py tests\ingest\test_addition_test_sheet.py -q --basetemp .pytest_tmp_k02_i_h_fix_wb`：18 passed
- 标准模板 `FY26_SOP K1 SWP 固定资产.xlsx` 单页只读复核：右侧 SOP 说明区不再被误读为金额；`difference_amount` 读为约 `-0.00000003`，`remaining_population_amount` 读为约 `5,852,456.94`。
- 标准模板 `K.02.1a 新增选样输出` 单页只读复核：4 个模块均为 `recognized`；`sample_method` 读为 `随机抽样 (Random)`；选样输出读取到代表性样本和替换样本。
- 案例库只读复核：B/E/G 的 K.02.1a 金额块、抽样策略、选样明细可识别；I 科技按汇总页拒绝执行识别；H 公司按测试页说明性拒绝执行识别。

下一步建议：

- 先在 report/人工核对页面展示 K.02.1 与 K.02.1a 模块摘录，再推进 `K.02.1a` 选样输出与新增清单、K.01 后推之间的样本一致性和金额一致性规则。
- 规则层推进前，继续用案例库校准 K.02.1a 的少数变体：I 科技虽有 K.02.1a sheet 但汇总页已拒绝执行，H 公司无 K.02.1a 但测试页已有不执行说明，这两类不应被简单视为漏做。

**研发顺序共识（2026-06-04）**：先 **ingest 稳定**（sheet 路由、多期选当期、K.01 矩阵口径、清单字段），再扩 **勾稽 rules**；`addition_rollforward_reconciliation` 保留，案例库以 ingest 门禁为主。

**下一步（ingest 优先）**：P1 多期 `-24` 路由；B/F `addition_method` 映射；暂缓铺更多清单↔K.01 勾稽直至两侧口径稳定。

**复跑**：`python scripts/run_case_addition_reconciliation.py`、`python scripts/diagnose_case_efg.py`

## 2026-06-04 K.01 与 Lead LLM 复测修复沉淀

本轮根据更新后的 UI 复测结果，聚焦 `K1 SWP 固定资产 20251231 E锂原 - 测试0604.xlsx` 中的 K.01 读取错位与 Lead 语义复核误提示。

已完成：

- **K.01 表1/表3读取分离**：`rollforward_sheet.py` 新增表1矩阵读取，`ending_totals` 优先读取表1合计列的期末审定数；表1 `CHECK` 列、表3 `表2 check with 表1` 分别保存，避免把表3差异误读为 K.01 期末余额。
- **LEAD-010 定位修复**：Lead 与 K.01 后推核对优先读取 K.01 表1 `CHECK` 列，并把 finding 定位到 K.01 对应行；当 CHECK 不可读时，才退回 Lead 与 K.01 期末数直接比对。
- **测试0604 复测结果**：K.01 期末数读取为原值 `694,376,870.69`、累计折旧 `134,308,399.27`、减值 `0`、净值 `560,068,471.42`；LEAD-010 仅报原值和净值差异，不再误报累计折旧。
- **GL-002 / GL-008 复测结果**：表3 FA list 与后推 check 差异、TB check 超 SAD 且无 Note 标识均可在 K.01 中识别并定位。
- **LEAD-013 语义复核修复**：LLM 输入新增 `note_required_by_threshold` 与 `volatility_threshold_reason`；金额阈值和比例阈值同时存在时，必须两者均超过才强制要求 Note。金额变动为 0 时，即使比例显示 100%，也不要求补 Note；未超阈值但编制者自愿写 Note，不按强制异常波动标准判断。
- **LEAD-012 语义复核收窄**：预期分析已包含主要业务原因和变动方向，且未见与 Lead/K.01 可见方向冲突时，不应再要求补 K.01 期初、期末及变动金额。LLM 返回 `unclear` 不再生成 `LEAD-012` Comments，避免与 `LEAD-014` 重复。

已验证：

- `.\.venv\Scripts\pytest.exe tests\ingest\test_workbook_ingest.py tests\rules\test_rollforward_rules.py tests\rules\test_lead_rules_extended.py -q --basetemp .pytest_tmp_k01_fix_core`：67 passed
- `.\.venv\Scripts\pytest.exe tests\report\test_workbook_pipeline.py tests\report\test_export_annotated_workbook.py -q --basetemp .pytest_tmp_k01_fix_report`：13 passed
- `.\.venv\Scripts\pytest.exe tests\llm\test_lead_review.py -q --basetemp .pytest_tmp_lead012_fix`：9 passed
- `.\.venv\Scripts\pytest.exe tests\llm -q --basetemp .pytest_tmp_lead012_fix_all`：37 passed

待复测重点：

- UI 重新跑 `测试0604`，确认主 Comments 中不再出现“减值准备 0 金额 + 100% 变动需补 Note”的 LEAD-013。
- 确认 LEAD-012 不再因“补充 K.01 后推明细表期初/期末/变动金额”进入 Comments；预期分析简略但无明显冲突时，仅保留 LEAD-014 的人工复核提示。
- 若 K.01 表1 `CHECK` 列在其他模板中位置变化，需继续补充表1矩阵读取回归。

## 2026-06-04 K.02 程序包门控 + QC 矩阵 + ingest 多期路由沉淀

本轮按 SOP 先理解处置/新增测试三表程序包，再推进 ingest 与门控；**研发顺序共识**：第 1 层 ingest 稳定 → 第 2 层 rules 勾稽 → 第 3 层 LLM/checklist。

### 处置/新增测试口径（SOP 对齐）

| 程序 | 三表程序包 | 样本总体口径 |
| --- | --- | --- |
| 新增测试 K.02.1 | 新增清单 + K.02.1 新增测试 + K.02.1a 选样输出 | 新增清单原值合计（购置类勾稽 K.01 购置行） |
| 处置测试 K.02.2 | 处置清单 + K.02.2 处置测试 + K.02.2a 选样输出 | **出售+报废净值**（E14/G/I/K），非原值、非处置损益 |

程序包不完整 ≠ 程序未执行：汇总页拒绝+理由合理，或拒绝说明写在 K.02.1/K.02.2 测试底稿时，按 **documented_limited** 处理。

### 已完成（代码 + 文档）

- **程序包门控**（`addition_test_package.py`）：`K02ExecutionScope` = `waived` / `documented_limited` / `full_expected`；缺表一律 **NEED_REVIEW**（不再 FAIL）；读取 K.02.1/K.02.2 测试页 waiver 说明（`k02_test_sheet.py`）；流水线传入 `workbook_path`
- **QC 规划矩阵**：`docs/planning/k02-disposal-qc-matrix.md`（DT-A～G）、`k02-addition-qc-matrix.md`；总索引 `k02-k03-qc-matrix.md` 已链接
- **ingest P1 多期路由**（`sheet_period_routing.py`）：双套 24/25 底稿按 sheet 名称后缀选当期；接入 `sheet_loader` / `records` / `summary` / `lead` / `rollforward`
- **新增测试 ingest 第一阶段**（`addition_test_sheet.py`）：识别 K.02.1/K.02.1a 存在性与 waiver 说明；`build_addition_execution_path` 汇总执行路径；`workbook_ingest` / `workbook_context` 已接入
- **新增测试 ingest 第二层读取**（`addition_test_sheet.py`）：K.02.1 可按锚点读取购置总体金额、K.01 后推购置金额、差异、关键项目金额、剩余代表性总体，并读取实际测试样本表（样本类型、资产编号、资产名称、资产原价、支持性文件金额、证据描述、差异、四项测试属性结论）；K.02.1a 可按锚点读取已上传数据、样本池总体金额、会计记录金额、差额、关键项数量/金额、代表性样本量、样本选择方法，并读取已选样本表（源样本号、抽样 ID、样本类型、资产编号、资产名称、原值、新增方式）
- **sheet 识别**：`ADDITION_TEST` / `ADDITION_SAMPLE_OUTPUT`；K.02.1 / K.02.1a 名称变体；`addition_method` 同义词扩展
- **回归脚本**：`scripts/run_case_ingest_routing.py`（已知 bug：`FaListSheetCandidate` 不可下标，待修）

### 案例库 ingest 门禁（B–G，修复 P0 后快照）

| 案例 | 关注点 |
| --- | --- |
| B | 新增清单有；购置 0 行（`addition_method`）；K.01 购置为各类别审定合计 |
| C/D/F | 双套 24/25 底稿，需多期路由 |
| E | 清单与 K.01 购置可一致 |
| G | 处置清单易误标 rollforward；K.02.2 恒为 unclassified |

### 已验证

- `pytest tests/rules/test_addition_test_package.py tests/ingest/test_k02_test_sheet.py tests/ingest/test_sheet_period_routing.py tests/ingest/test_addition_test_sheet.py -q --basetemp .pytest_tmp_k02_gate`：23 passed
- `.\.venv\Scripts\pytest.exe tests\ingest\test_addition_test_sheet.py tests\ingest\test_sheet_classifier.py tests\ingest\test_workbook_ingest.py -q --basetemp .pytest_tmp_k02_ingest_detail`：29 passed
- 只读验证标准模板 `FY26_SOP K1 SWP 固定资产.xlsx`：`K.02.1 新增测试` 可读到总体金额锚点与 1 条实际测试样本；`K.02.1a 新增选样输出` 可读到样本池/抽样金额锚点与 2 条选样输出样本

### 下一步（ingest 优先，处置 P0）

1. 评审确认 `k02-disposal-qc-matrix.md`（尤其 DT-A 执行路径、DT-C E14 净值汇总、DT-D K.01 勾稽）
2. DT-B 处置清单字段映射 → DT-C `disposal_common` → DT-D K.01 处置行
3. 修复 `run_case_ingest_routing.py`；案例 B–G 回归

**暂缓**：K.02.2 E14 结构化读取（P1.5/P2）、DT-E/F/G 规则、大量 disposal rules

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
- `docs/workpaper-ingest-and-rule-methodology.md` — **底稿识别与质检规则开发方法论**（模板定结构、SOP 定口径、ingest 先读对、rules 再判对）
- `docs/llm-agent-roadmap.md` — 三层 LLM 分工与 M3c 任务（C1–C9）
- `docs/planning/lead-qc-rules.md` — K.00 分模块质检点、SOP 对照遗漏、M2 实现顺序
- `docs/planning/program-qc-coverage-index.md` — **程序质检覆盖总索引**（汇总 / Lead / K.01 / K.02 / K.03 开发进度）
- `docs/planning/k01-qc-rules.md`、`docs/planning/k01-workpaper-layouts.md`、`docs/planning/k01-six-block-qc-matrix.md` — K.01 SOP 对照、版式、六区块矩阵
- `docs/planning/k02-disposal-qc-matrix.md`、`docs/planning/k02-addition-qc-matrix.md`、`docs/planning/k02-k03-qc-matrix.md` — K.02 处置/新增详细矩阵与总索引
- `src/ingest/addition_test_sheet.py`、`src/ingest/k02_test_sheet.py`、`src/ingest/sheet_period_routing.py` — K.02 ingest 与多期路由
- `src/rules/addition_test_package.py` — K.02 程序包执行路径门控

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

## 2026-06-08 K.02 新增清单 ingest 案例校准

本轮继续按“模板定结构，SOP 定口径，ingest 先读对，report 先展示，rules 再判对，案例回归校准，质检经验补例外”的方法推进 K.02 新增测试。重点不是新增规则结论，而是先把新增清单读准，避免后续规则基于错误总体金额或错误资产明细判断。

已完成 ingest 校准：

- **新增清单金额列口径**：新增清单不能机械取 `期初原值`。B 公司期初原值为 2025-01-01 余额，应取 `期末原值`；H 公司存在原资产上追加新增，应取 `新增原值`。
- **新增方式读取**：I 公司新增清单 A 列为 `新增方式`，购置只有 2 笔；新增方式字段需保留并用于后续筛选购置/外购总体。
- **非明细行过滤**：E 公司 60/66 行分别为 `外购-小计`、`在建转固-小计`，G 公司 49 行为全部新增合计，均不作为资产明细。
- **完整明细读取**：I 公司 2 笔购置在第 240-241 行，新增清单识别到候选 sheet 后需读取完整明细，不能只读前 100/150 行。
- **表尾金额行过滤**：仅有金额、无资产编号/名称/类别/新增方式的尾部行不作为资产明细。

案例库只读回归结果：

| 案例 | 新增清单 ingest 结果 |
| --- | --- |
| I 公司 | 识别 238 条明细；购置 2 笔；购置金额 `386,061.06`；A 列 `新增方式` 已识别 |
| B 公司 | 识别 20 条明细；金额列取 `期末原值`；购置金额 `866,546.67` |
| E 公司（4 个版本） | 识别 57 条明细；`外购-小计`/`在建转固-小计` 已过滤；外购金额 `128,976,911.37` |
| G 公司 | 识别 40 条明细；合计行已过滤；购置金额 `41,598,444.51` |
| H 公司 | 识别 47 条明细；金额列取 `新增原值`；购置金额 `749,900` |

已验证：

- `.\.venv\Scripts\pytest.exe tests\ingest\test_field_mapping.py tests\ingest\test_records_workbook.py -q --basetemp .pytest_tmp_addition_list_ingest`：`46 passed`

下一步建议：

- 先在 report/人工核对视图展示新增清单字段映射、购置/外购总体金额、非购置新增分布，再推进规则判断。
- K.02 新增测试规则应优先基于“购置/外购总体”与 K.01 勾稽；非购置新增（在建转入、资产合并、内部划转等）先作为 `NEED_REVIEW` 或说明性提示，不直接等同于购置新增总体。
- 程序包完整性仍需保留例外口径：程序包不完整不必然代表程序执行不到位；若汇总页拒绝执行且理由合理，或满足拒绝执行条件但说明写在 K.02.1 新增测试中，应按已记录的受限/拒绝路径处理。

## 2026-06-09 K.02 新增测试规则化首轮：B 公司案例

本轮根据 `E:\FAQC\新增测试人工质检点.txt` 将人工质检过程拆为可规则化检查点，先落地 K.02.1a 选样输出与 K.02.1 新增测试之间的样本一致性检查。当前只用案例库中的 B 公司做第一次案例回归；本轮未读取标准模板，因为标准模板为空模板，不适合作为本次测试依据。

已完成：

- 新增 `addition_sample_match` 规则，用于检查 K.02.1a 已选取样本是否进入 K.02.1 实际测试，并核对关键项目金额是否一致。
- K.02.1a Skywind 选样输出读取已兼容 B 公司格式：该表“已选取样本”没有资产编号/资产名称列，但可读取源样本号、抽样 ID、样本类型和金额。
- B 公司读取结果：K.02.1a 已选样本 1 条；K.02.1 实测样本 1 条；两边均为关键项，金额均为 `380,000`，匹配通过。
- K.02 报告结构已能展示新增测试页、选样输出页、执行路径和一致性预览。

本次 B 公司规则结论：

- `addition_sample_match`：`PASS`。
- 因为本规则未产生 `FAIL/WARN/NEED_REVIEW` finding，所以标注底稿不会因该规则新增批注。

界面与导出口径：

- 质检界面走同一条 `run_input_qc` / `run_workbook_qc` 流水线，上传 Excel 后会生成 JSON、HTML 和 `*_qc_annotated.xlsx` 标注底稿下载。
- K.02 识别结果会进入报告结构和界面摘要；标注底稿的 Comments 表和单元格批注主要来自 findings。
- 因此，B 公司本次新增测试匹配为 `PASS` 时，界面仍会正常导出标注底稿，但不会额外出现 K.02 样本匹配问题批注。

已验证：

- `.\.venv\Scripts\pytest.exe tests\rules\test_addition_consistency.py::test_b_company_addition_selected_sample_matches_tested_sample tests\report\test_workbook_pipeline.py::test_workbook_qc_b_company_includes_addition_sheet_section -q --basetemp .pytest_tmp_k02_addition_rules_b_only`：`2 passed`

后续建议：

- 用户自行通过质检界面测试 B 公司导出，重点确认报告摘要能看到 K.02 模块，且标注副本可以正常下载。
- 下一步可扩展其他案例回归，优先验证 I/H 这类拒绝执行或测试页说明路径，避免把“程序包不完整”误判为“程序未执行到位”。
- 证据充分性、折旧政策一致性、控制权转移证据是否充分等人工判断点，建议作为下一阶段 `NEED_REVIEW` 型规则逐步落地。

## 2026-06-09 K.02.1a 抽样输出补强：TE / CRA / 认定 / 替换样本

本轮把 K.02.1a 从“能读样本”推进到“能判断抽样参数是否与 Lead 一致”。已把前置信息结构化读取出来，包括 TE、测试涵盖认定、舞弊/特别风险、综合风险评估，并接入四条规则：

- 样本池总体金额与新增清单购置/外购金额一致性
- K.02.1a TE 与 Lead TE 一致性
- K.02.1a 综合风险评估与 Lead CRA 一致性
- 测试涵盖认定不应默认包含完整性；替换样本需有原样本不可用原因

B 公司已验证到的关键事实：

- K.02.1a TE = `241,890.00`
- K.02.1a 测试涵盖的认定 = `存在/发生, 计量/计价, 权利与义务`
- K.02.1a 综合风险评估 = `最低`
- Lead 页 TE = `213,730.00000000003`
- Lead 页相关认定中，`计价/计量（V/M）= Low`

阶段判断：

- K.02.1a 抽样输出已经**基本能输出结果**。
- 但仍处于**继续校准中**，还需要更多案例验证 I/H/E/G 等变体，以及继续收紧替换样本和认定范围边界。

本轮 B 公司结果：

- 样本池总体金额一致性：`PASS`
- TE 一致性：`FAIL`
- CRA 一致性：`FAIL`
- 测试涵盖认定不含完整性：`PASS`

已验证：

- `.\.venv\Scripts\pytest.exe tests\rules\test_addition_sampling_output.py -q --basetemp .pytest_tmp_addition_sampling_output2`：`7 passed`
- `.\.venv\Scripts\pytest.exe tests\rules\test_addition_consistency.py tests\report\test_workbook_pipeline.py -q --basetemp .pytest_tmp_addition_k02_b2`：`5 passed`
## 2026-06-09 K.02 新增测试 LLM 语义复核接入

本轮把 K.02.1 / K.02.1a 的 LLM 提示词补成了“只管语义充分性、不抢规则判断”的形态，并接入工作簿流水线。

已完成：

- 新增 `src/llm/addition_review.py`，定义 K.02.1 新增测试的 LLM 语义复核提示词与 payload。
- 提示词明确约束：
  - 不重新判断金额、样本、TE、CRA；
  - 不用规则已发现的差异去覆盖结论；
  - 只判断拒绝执行理由、样本选择理由、异常说明、特殊新增来源、跨表叙述是否充分。
- `src/report/pipeline.py` 已接入新增测试 LLM 复核，仅在 `config.enabled=true` 时调用。
- 新增 `tests/llm/test_addition_review.py` 和流水线集成测试，验证 mock LLM 结果可进入报告。

验证：

- `.\.venv\Scripts\pytest.exe tests\llm\test_addition_review.py tests\report\test_workbook_pipeline.py -q --basetemp .pytest_tmp_addition_llm_pipeline`：`10 passed`

当前结论：

- 新增测试 LLM 已进入 pipeline，但仍定位为“语义复核辅助”，不替代规则层的金额与样本判定。
- 后续如果要继续扩展，可优先补充 K.02.1a 的样本选择、拒绝执行理由与跨表一致性案例库回归。

## 2026-06-11 K.02.2 处置测试案例诊断：J / G

本轮按“先案例诊断，再补规则”的顺序，只读检查了两个处置测试案例：

- `K1 固定资产 20251231 J有限公司.xlsx`
- `K1 SWP 固定资产 20251231 G科技.xlsx`

### 诊断结论

J 公司适合作为“完整执行处置测试”的正向案例：

- 汇总页显示 `处置清单`、`K.02.2 处置测试` 均执行，且存在 `K.02.2a 处置选样输出`。
- 处置清单可读 42 条明细，处置净值合计 `2,044,999.37`，全部归入出售/报废口径。
- `K.02.2 处置测试` 可读到处置/报废总金额 `2,044,999.37`、Breakdown/K.01 金额 `2,044,999.37`、差异 `0`，并可读到 1 条测试样本。
- `K.02.2a 处置选样输出` 可读到 TE `1,961,000.00`、CRA `最低`、样本池总体金额 `2,044,999.37`，并读到 1 条代表性样本和 1 条替换样本。
- 规则机会点：选样输出中资产 `10300002409` 为“代表性样本”，但 K.02.2 实测页同一资产写为“关键项（key item）”；同时 K.02.2a 关键项数量为 0。应补充处置样本一致性规则，先以 `NEED_REVIEW` 提示样本分类不一致。

G 科技适合作为“有处置清单但拒绝执行 K.02.2 详细测试”的案例：

- 汇总页显示 `处置清单` 执行，`K.02.2 处置测试` 不执行；不执行理由为“实际处置金额小于TT，不进行本次测试”。
- 工作簿没有 `K.02.2` / `K.02.2a` sheet，这与汇总页拒绝执行路径基本一致，不应误报程序包缺失。
- 处置清单可读 10 条明细，总净值 `757,611.35`；其中出售/报废净值仅 `486.75`，其余 `757,124.60` 为“转入xxxxx”类其他减少。
- 规则口径：处置测试总体应优先使用“出售/报废净值”，不能用处置清单总净值机械判断是否应执行 K.02.2。

### 本轮待修复

1. 读取稳定性：整本 `ingest` / 完整规则读取在 G 科技上偏慢，应跳过 `DS_INTERNAL_*` 等内部 sheet，并减少重复全量扫描。
2. 处置样本一致性：补充 K.02.2a 已选样本与 K.02.2 实测样本之间的资产编号、净值、样本类型一致性检查。
3. 处置执行路径：G 科技这类“汇总页明确不执行 K.02.2，且理由为实际处置金额小于 TT”的情况，不应触发程序包缺失提示。

## 2026-06-11 LLM ingest review 项目级识别层接入

本轮把 LLM 从“报告摘要/单点语义复核”继续前移到 **ingest 识别层**，定位为“读取结果复核员”：帮助发现 sheet 漏读、错分、字段/锚点可疑、Notes 归属风险；不计算金额，不改变 `rules` 的 `PASS/WARN/FAIL/NEED_REVIEW`。

已完成：

- `src/llm/ingest_review.py`：新增项目级 `ExpectedIngestObject` 清单和 `run_workbook_ingest_reviews()` 入口，覆盖所有核心程序对象：
  - 汇总、K.00 Lead、K.01、FA list；
  - K.02.1 新增清单 / 新增测试 / 新增选样输出；
  - K.02.2 处置清单 / 处置测试 / 处置选样输出；
  - K.03.1 SAP、K.03.2 折旧测试、K.03.3 折旧政策复核。
- K.01 profile 保留为程序级增强：六区块、表3/表4/Notes 归属等专项提示，不再作为唯一接入对象。
- `src/report/pipeline.py`：流水线按 `WorkbookQcContext` 与 `WorkbookStructure` 已识别对象判断缺失项，统一触发 LLM missing discovery；结果只进入 `ingest_review_section`，不生成普通 rule issue。
- `src/report/export_annotated_workbook.py`：标注底稿新增 `LLM识别复核【归档前删除】` sheet，用于展示 LLM 读取层判断、候选 sheet、候选行、锚点证据和建议动作，与 Comments findings 分开展示。
- 文档修正：`docs/planning/llm-ingest-review-framework.md`、`docs/planning/llm-ingest-profile-k01.md` 已明确“项目级识别层覆盖所有核心程序 sheet，程序级 profile 只是增强”。

已验证：

- `.\.venv\Scripts\pytest.exe tests\llm\test_ingest_review.py tests\report\test_workbook_pipeline.py tests\report\test_export_annotated_workbook.py -q --basetemp .pytest_tmp_llm_ingest_all`：`36 passed`
- `ReadLints`：相关代码与测试无 linter errors。

后续建议：

- 用案例库/真实复测底稿启用 LLM 跑一次 UI，重点查看 `LLM识别复核【归档前删除】` 是否能帮助质检人员判断 Agent 是否读对底稿。
- 逐步补 Lead、K.02.1、K.02.2、K.03 的程序级 profile；不要把 profile 完整度作为项目级 LLM ingest 兜底是否启用的前提。
- 若 LLM 输出噪音偏多，优先调候选生成和触发阈值，不让 LLM 结果进入业务 findings。

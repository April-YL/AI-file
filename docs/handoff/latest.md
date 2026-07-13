# 最新交接

> 每次收工前更新本文。新成员接手先读 `docs/ONBOARDING.md`，再读 `AGENTS.md` 和本文。


## 2026-07-13 K03 rules 阶段 2：SAP 策略与参数规则

本阶段在既有 `K03ExecutionProfile` 路径分派机制内完善 SAP 策略与参数规则，并完成规则口径统一；未扩展 TOD、折旧政策、特别风险、实体类型或证据充分性判断。

- `sap_precision_selection` 使用工作簿级 profile 已关联的 Lead 计价/计量（V/M）CRA，不使用 SAP 模板预设 CRA 代替 Lead CRA。Lead V/M CRA 为 Minimal 时，中精度 SAP 可单独采用；CRA 不低于 Low 时，中精度 SAP 只有在实际识别到已执行的 TOD by-item 或 TOD 抽样补充程序时才可接受，否则输出 `NEED_REVIEW`。
- `sap_te_consistency` 独立比较 SAP TE 与 Lead TE；`sap_high_cra_consistency` 仅适用于高精度 SAP，独立比较 SAP 页 CRA 与 Lead V/M CRA。两项参数明确不一致时统一为 `AUTO_FAIL` / `FAIL`。
- `DP-SAP-001`、`DP-SAP-002` 是从原始检查点 `DP-003` 拆出的 Agent 可执行子规则，已登记 registry 和规则映射；不作为原始 35 条来源字典的新行写入脱敏 CSV。
- SAP 路径适用但 Lead/SAP 必要参数无法可靠读取时，相关规则在 `execution_ledger` 记录 `DATA_INSUFFICIENT`；仅高精度适用的 CRA 一致性规则在中精度 SAP 下记录 `NOT_APPLICABLE`，不得默认为已执行或通过。
- 同一底稿实际执行多张 SAP 程序页时，runner 分别执行并合并 observation；finding 数量与 `checked_data` 中的全部被检查工作表保持可追溯一致，不再只保留最后一张 SAP 页证据。
- 验收结果：K03 SAP、K03 runner、registry 与规则执行覆盖相关测试合计 `32 passed`；本轮测试未新增 workspace hygiene 问题。
- 后续边界：特别风险下 TOD 要求、实体类型选择和 SAP 证据充分性仍需人工复核或后续阶段实现，不得在当前 UI/JSON 中展示为已自动完成。


## 2026-07-12 K03 rules 阶段 1：按识别画像分派执行路径

本轮只完成 K03 识别结果到现有规则 runner 的接线与路径分派，未新增 SAP、TOD 或折旧政策的具体判断规则。

- `src/report/pipeline.py` 已将 `WorkbookQcContext.k03_execution_profile` 传入 `run_k03_rules()`；主流程开始消费 ingest 已识别的 K03 工作簿级画像。
- `src/rules/k03_runner.py` 按 `primary_depreciation_path` 和 `component_sheets` 分派现有规则：SAP 中精度、SAP 高精度、TOD by-item、TOD 抽样，以及 SAP + TOD 抽样组合路径。
- 一般四选一路径只执行已识别的方法；未采用的其他测试路径在 `execution_ledger` 记录为 `NOT_APPLICABLE`，不产生错误结论。
- 路径无法识别，或画像已选择某路径但对应程序页无法匹配时，相关规则记录为 `DATA_INSUFFICIENT`，不得默认通过。
- K03.3 折旧政策复核继续作为独立必要程序处理，不随折旧测试路径切换；未识别政策复核页时，政策规则单独记录为 `DATA_INSUFFICIENT`。
- “本期计提”继续只作为辅助数据页，不作为必要程序页，也不作为已执行折旧测试的依据。
- 新增 `tests/rules/test_k03_runner.py`，覆盖 TOD by-item 单一路径、SAP + TOD 抽样组合路径、K03.3 独立缺失，以及仅存在“本期计提”辅助页四类场景。
- 验收结果：K03 runner 及既有 SAP、TOD 抽样、TOD by-item、政策复核测试合计 `26 passed`；测试运行未新增 workspace hygiene 问题。
- 下一阶段应在当前分派机制内逐路径完善具体规则；不得绕过 `K03ExecutionProfile` 在 rules 层重新猜测底稿结构。


## 2026-07-12 UI 精修通过版沉淀

本轮 UI 精修已完成并提交、推送：`d758c6a Refine audit review UI workflow`，远端为 `origin/main`。

- 页面定位已重新确认：`复核工作台` 展示当前待处理事项和下一步入口；`执行复核` 负责复核配置、上传底稿、执行质检和运行进度；`复核结果` 负责交付物、Findings 明细、质检点执行台账、基本信息摘录和运行耗时。
- 结果页摘要区采用固定结构：Findings 汇总一行，质检点执行台账一行；不要把两类卡片混在同一行，也不要塞进 Tab 内容里。
- Findings 汇总必须按原始 `severity` 事实统计：`FAIL`、`WARN`、`NEED_REVIEW`；不得用 UI 优先级分类替代 severity 数量。
- Findings 明细和质检点执行台账采用“左表右详情”交互；右侧详情展示定位、说明、取数来源和系统取数证据，UI 只展示事实，不新增审计结论。
- 本轮 UI 提交范围仅限 `src/report/ui_*`、`src/report/ui_pages/*`、`src/report/ui_components/*` 相关展示层和 `tests/report/test_ui_v33_contract.py`；未改 ingest、rules、pipeline、LLM、registry、execution_ledger 原始结构、Finding 字段、severity、JSON/HTML 报告或底稿标注逻辑。
- 验证结果：`tests/report/test_ui_v33_contract.py` 为 `7 passed`；多次只读核对最新运行事实未变，示例为 15 条非 PASS，`FAIL 3 / WARN 5 / NEED_REVIEW 7`，`rule_execution_matrix=90`，`execution_ledger items=80`。
- 当前本地仍有独立的 ingest/K03/artifacts 修改和若干未跟踪 docs/打包/资料文件；后续提交必须与 UI 修改分开处理，避免混提交。

## 2026-07-12 K03 ingest 识别阶段闭环

本轮只完成 K03 ingest 结构识别闭环，未新增或修改 K03 rules。

- 已新增工作簿级 `K03ExecutionProfile`，并挂到 `WorkbookIngestContext` / `WorkbookQcContext`。
- Profile 用于识别折旧测试路径、组件页、证据完整性、Lead V/M CRA/TT 关联和结构识别 warning。
- 已识别组件包括 SAP 中精度、SAP 高精度、TOD by item、TOD 抽样、K03.2a 抽样输出、K03.3 折旧政策复核、以及本期计提等辅助页。
- `K03.3` 作为独立必要程序处理，不并入 SAP/TOD 折旧测试四选一路径。
- `本期计提` 仅作为辅助数据页，不作为 K03 必要程序页，也不作为已执行折旧测试的判断依据。
- Lead CRA/TT 只关联折旧相关 V/M 认定；未识别 V/M 时不再默认取第一行 CRA，而是留空并输出 warning。
- 案例库回归已跳过 `~$` 开头的 Excel 临时锁文件，并刷新 Lead/K01 regression artifact 以匹配当前本地案例库。
- 已验收：K03 ingest 18 passed；K02 / Lead / K01 / workbook ingest 38 passed, 15 skipped；workspace hygiene 无测试产物；`src/rules/k03_*` 无 diff。
- 测试证据口径：真实 SOP/J 底稿用于验证实际底稿呈现；人工构造用例只用于边界测试，不能作为真实底稿中各路径常见程度的证据。
- 下一阶段可以进入 K03 rules，但 rules 应消费 `k03_execution_profile`，不得在 rules 层重新猜测底稿结构。

## 2026-07-09 K03 第一阶段与 checklist 口径同步

- K.03 第一阶段已接入主流程：SAP 中精度、SAP 高精度、TOD 抽样、TOD by-item、折旧政策复核均可被识别，并进入对应规则或执行台账。
- 本轮新增/接入的 K03 规则口径包括：`sap_precision_selection`、`sap_depreciation_difference`、`depreciation_tod_sampling`、`depreciation_tod_difference`，并保留既有 TOD by-item 与政策复核规则。
- `K1 check list_rule_mapping.xlsx` 已新增最新口径 sheet：`规则映射v0.5_K03更新` 和 `当前规则能力目录_v2`；DP-003、DP-004、DP-006、DP-007 已从“计划/缺口”同步为当前主流程已纳入的部分自动覆盖。
- 文档口径已同步到 `docs/checklist-rule-mapping.md`、`docs/rule-dictionary-mapping.md`、`docs/qc-checklist.md`、`docs/planning/program-qc-coverage-index.md`、`docs/planning/k02-k03-qc-matrix.md`、`docs/k03_mvp_plan.md` 和 `docs/workpaper-fields.md`。
- 当前边界：K03 SAP/TOD 第一阶段规则主要做路径识别、关键字段/参数、差异处理和程序执行提示；证据充分性、SAP + TOD 组合结论、复杂政策合理性仍需人工复核或后续 LLM/规则增强。
- 已验证：K03 focused tests 15 passed；registry / execution ledger / coverage tests 27 passed。历史 Excel sheet、`docs/history/**` 和 source dictionary fixture 未作为本轮同步对象修改。

## 2026-06-30 黑箱治理与 HOW 样板沉淀

- 新增治理主文档 `docs/architecture/fa_qc_governance_plan.md`，明确 `registry.py` 是系统承认的可执行规则真源，`review_rules.md` / skill rules 仅作为 reference / backlog，未完成迁移闭环的规则不得在 UI/JSON 中展示为已检查或已执行。
- 治理链路已明确为：input workbook → `ingest_result` / 现有 ingest 输出 → `registry.py` → runner / rules → `execution_ledger` → `observation` → UI / JSON；其中 UI/JSON 只展示，不推断。
- 当前代码层已先做 K.01 两条证据级 HOW 样板，后续推广到其他模块前，应按治理文档先确认规则类型和 observation 模板。
- 本轮文档沉淀不改变 runner、execution_ledger 顶层结构、severity、finding 判断逻辑或 LLM 调用逻辑。

## 2026-06-24 K1 mapping 编号补全复核

- 正式映射工作簿 `固定资产质检agent/资料库/K1 check list_rule_mapping.xlsx` 在 2026-06-24 使用的 sheet `规则映射v0.4编号补全版` 已由 102 行更新为 110 行，并经人工检查确认问题已解决；当前最新口径见上方 2026-07-09 的 v0.5 记录。
- 本轮补入 registry 已登记但映射表缺失的 `DP-BI-PRE-001`～`DP-BI-PRE-004`、`DP-BI-004`、`DP-POL-PRE-001`～`DP-POL-PRE-002`、`DP-POL-007`。
- 已修复 `MT-002 / special_movement_identification` 与 `GL-003 / lead_prior_year_reconciliation` 复核意见中的疑问口径；当前说明明确这些点的 runner 纳入状态、人工复核边界和与既有规则的重叠关系。
- 本轮只更新 K1 mapping Excel 与说明文档，不改变 `src/rules/registry.py`、runner、execution_ledger、severity 或 finding 判断逻辑。

## 2026-06-24 UI 分类口径 v1

- 已完成 `fa-qc-ui` Findings 分类收敛：UI 展示分类只影响页面优先级，不改变 `PASS/WARN/FAIL/NEED_REVIEW`、JSON 报告、registry、execution_ledger 或规则判断。
- 当前 UI 三类为：`高优先级问题`、`需人工处理`、`其他提示`。
- `FA_LIST` findings 默认归入 `其他提示`，避免 FA list 明细字段、金额、使用寿命、残值率等高频问题淹没 Lead/K.01/PSP 等核心事项。
- mapping / registry 中 `qc_checkpoint` 以 `N-` 或 `No-` 开头的项目默认归入 `其他提示`；后续如需细化，应优先按 `K1 check list_rule_mapping.xlsx` 的系统质检点列校正，而不是靠 UI 关键词猜测。
- K.03.2 by-item 折旧测试问题已收敛：`k03_tod_by_item_*` 中超过 SAD 的单项/总体差异不再自动进入 `高优先级问题`；`NEED_REVIEW` 的 by-item 项仍进入 `需人工处理`。
- SAD 是明显微小错报门槛，不等同重大差异阈值；UI 不再仅因 “SAD / difference / amount / te” 等泛化关键词把 finding 提升为高优先级。若未来要判断是否达到 TT 或影响整体结论，应由规则输出结构化字段，不在 UI 中猜测。
- 高优先级当前采用明确 rule_id 白名单，主要保留 PSP、Lead/K.01、样本池/后推等核心勾稽和程序范围事项。
- 已验证：`tests/report/test_ui_priority_classification.py -q` 5 passed；`tests/report/test_ui_priority_classification.py tests/report/test_workbook_pipeline.py -q` 17 passed。用户已用实际 UI 结果复测，确认大面积错分已消失。

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
- K1 checklist 与 Agent 实际 rules 的映射已沉淀：口径文档见 `docs/checklist-rule-mapping.md`，正式映射工作簿为 `固定资产质检agent/资料库/K1 check list_rule_mapping.xlsx`，当前最新 sheet 为 `规则映射v0.5_K03更新`；当前规则能力目录最新 sheet 为 `当前规则能力目录_v2`。
- `src/ingest/`：sheet 分类、字段映射、底稿诊断 CLI、FA list CSV/Excel 解析（`load_fa_list_from_workbook`）。
- `src/rules/` + `src/report/`：首批 3 条 FA list 规则 + JSON 报告；**`fa-qc-run` CLI 已可用**。
- 规则字典映射：`docs/rule-dictionary-mapping.md`、`src/rules/registry.py`、`tests/fixtures/rule_dictionary_*.csv`
- **距终态差距**：全 checklist 覆盖、正式质检报告 Excel 版、标注精度（单元格坐标/共性合并规则）、K.01 规则余量。

## 已完成

- 项目长期上下文：`AGENTS.md`（已按终态目标与必交付项更新）
- 项目结构说明：`docs/PROJECT_STRUCTURE.md`
- 领域词典、架构、任务与进度文档
- 质检 checklist：`docs/qc-checklist.md`
- K1 checklist 与 Agent rules 映射：`docs/checklist-rule-mapping.md`；正式 Excel 为 `固定资产质检agent/资料库/K1 check list_rule_mapping.xlsx`，最新 sheet `规则映射v0.5_K03更新`，当前规则能力目录最新 sheet `当前规则能力目录_v2`。当前 v0.5 进一步同步 K03 SAP/TOD 抽样规则口径。后续开发新 rule 前，先查该映射表确认 checklist 行、现有覆盖、执行条件和缺口。
- 历史 v0.4 曾补齐 14 条“未登记字典编号”，包括 `AT-LLM-001`、`DP-BI-001`～`DP-BI-003`、`DP-POL-001`～`DP-POL-006`。
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

## 2026-06-11 整本底稿性能与启动界面首轮修复

本轮针对 J / G 两个处置测试案例中暴露的“整本 Excel 反复扫描、启动界面首次运行偏慢”问题做了首轮修复。结论是：可以明显降低重复读取，但 J 公司底稿仍偏重，后续若继续优化，应进入“单次打开 workbook、多 sheet 共用读取结果”的较大改造。

已完成：

- `src/ingest/workbook_ingest.py`：整本 ingest 先使用 `analyze_workbook_structure()` 的识别结果，再把已识别出的 sheet 名传给各加载器，减少后续模块重复全工作簿扫描。
- 候选 sheet 选择改为按识别置信度排序，修复 J 公司一度误选 `For Disclosure` 作为 K.01 后推表的问题；当前 J / G 均能正确选到 `K.01 Agree SL to GL`。
- `src/ingest/sheet_loader.py`、`src/ingest/records.py`、`src/ingest/summary_sheet.py`、`src/ingest/lead_sheet.py`：当调用方已提供 sheet 名时，直接读取该 sheet，不再先扫描全工作簿。
- `src/rules/addition_test_package.py`、`src/report/pipeline.py`：K.02 程序包完整性检查复用已读出的测试页 waiver/limited note，减少为了查说明文字再次打开 workbook。
- `src/report/ui_app.py`：递增 `_QC_CACHE_VERSION` 为 `20260611-disposal-performance`，避免 Streamlit 界面沿用旧缓存。

已验证：

- `.\.venv\Scripts\pytest.exe tests\rules\test_addition_test_package.py tests\ingest\test_workbook_ingest.py tests\ingest\test_disposal_list.py tests\report\test_workbook_pipeline.py -q --basetemp .pytest_tmp_perf_fix4`：`42 passed`
- G 科技完整报告入口（不含导出标注）：约 `18.30s`，`ingest_seconds=10.706`，`rules_seconds=7.59`，issues `109`
- J 有限公司完整报告入口（不含导出标注）：约 `90.64s`，`ingest_seconds=43.347`，`rules_seconds=47.288`，issues `20`，其中 `disposal_sample_match` issues `2`
- J 有限公司报告 + 标注副本导出：约 `114.54s`，其中报告约 `105.54s`、标注导出约 `9.01s`

当前判断：

- 启动界面与 CLI 使用同一条 `run_input_qc` / `run_workbook_qc_from_path` 流水线，因此本轮优化同样作用于启动界面首轮运行。
- J 公司已从原先 120 秒超时改善为可完成，但离 120 秒边界仍近；如叠加 LLM、机器负载或更大底稿，仍可能超时。
- 本轮未改业务规则含义，主要改读取路径、候选 sheet 复用和 UI 缓存版本；原始案例底稿未被修改。

后续建议：

- 下一轮性能优化优先做“单次打开 workbook，共享多 sheet 行数据”的 ingest cache，而不是继续在单个规则里零散修补。
- 对 J 公司 rules 阶段约 47 秒的耗时继续拆分，重点看 `build_report`、手工复核区、K.01/Lead section 构建是否存在重复遍历大对象。
- UI 侧可考虑增加更明确的阶段提示：读取底稿、执行规则、导出标注分别显示耗时；暂不建议为了快而默认跳过标注，因为“质检报告 + 底稿标注”仍是必交付项。

## 2026-06-15 K.02.2 处置测试 ingest 增强：总体核对矩阵、锚点分块与置信度门控

本轮在完善处置 rules 前，先补强 K.02.2 处置测试的结构化读取准确性。开发口径已与业务确认：

- 处置清单中的程序说明和清单编制说明可在实际底稿中删除，不作为必要保留项；处置清单字段名称允许变体，继续复用 FA list / 新增清单的字段映射与动态表头识别机制。
- K.02.2 和 K.02.2a 的行列位置均不固定，不得按固定行列读取。
- K.02.2“处置/报废总金额”来源于处置清单；“Breakdown 中处置/报废金额”来源于 K.01 后推明细表。
- K.01 后推明细表不直接包含净值项；净值必须由 `原值 - 累计折旧 - 减值准备`计算。处置清单可能含净值列，但仍应使用另外三项重新计算并核对。

已完成：

- `src/ingest/disposal_test_sheet.py`：新增 K.02.2 总体核对矩阵结构，按语义和上下文识别以下行项目及金额维度，不绑定固定行列：
  - 行项目：处置清单总金额、K.01 Breakdown 金额、差异、是否需要进一步调查。
  - 金额维度：原值、累计折旧、减值准备、计算净值。
  - 每个金额保存值、公式、来源行列和单元格坐标。
- 公式来源检查：
  - 处置/报废总金额的原值、累计折旧、减值公式应引用处置清单。
  - Breakdown 金额的对应公式应引用 K.01。
  - 净值公式应引用同一行的原值、累计折旧和减值准备。
- 锚点分块增强：
  - 候选金额表头附近必须同时出现处置总金额、Breakdown、差异/调查等总体核对行项目。
  - SOP 指引、易错点等长段说明文字不作为业务金额锚点。
  - 详细测试样本表即使同样包含原值、累计折旧、减值和净值列，也不会被误判为总体核对模块。
- 置信度兜底增强：
  - K.02.2 总体核对矩阵输出 `recognition_confidence`、`recognition_evidence`、`missing_components`、`ambiguous_candidates` 和 `usable_for_rules`。
  - K.02.2 与 K.02.2a 输出模块级 `module_assessments` 和 sheet 级 `usable_for_rules`。
  - 公式来源未确认、候选模块冲突或结构缺失时，`usable_for_rules=False`，后续确定性 rules 不应直接据此判 FAIL。
- `src/ingest/workbook_ingest.py`：整本 ingest 摘要已展示总体核对矩阵、模块评估和规则可用门控。
- `tests/ingest/test_disposal_test_sheet.py`：新增动态行列、SOP 同名文字干扰、错误公式来源和模块评估测试。

已验证：

- `.\.venv\Scripts\pytest.exe tests\ingest\test_disposal_test_sheet.py tests\ingest\test_disposal_list.py tests\report\test_workbook_pipeline.py::test_workbook_qc_includes_disposal_sample_issue tests\rules\test_disposal_consistency.py -q --basetemp .pytest_tmp_disposal_ingest_final`：`18 passed`
- FY26 SOP 示例包 `K.02.2 处置测试 ` 实测：
  - 总体核对模块识别为第 13–17 行；详细测试样本表未被误识别。
  - 四个金额维度及处置清单/K.01 公式来源识别正确。
  - 净值公式关系识别正确。
  - 总体核对矩阵置信度 `1.0`，`usable_for_rules=True`。

下一步建议：

- 基于 `reconciliation_matrix.usable_for_rules` 开发 P0 `disposal_rollforward_reconciliation`，核对处置清单、K.02.2 与 K.01 的原值、累计折旧、减值准备及计算净值。
- 处置清单净值列存在时，与重新计算净值核对；不存在时不直接判缺失。
- 当总体核对模块低置信度或公式来源未确认时，规则应输出 `NEED_REVIEW`，不得直接判 `FAIL`。

## 2026-06-15 K.02.2 处置测试 rules 阶段 1–5：总体勾稽、清单、选样、详细测试与 LLM 语义复核

本轮在处置测试 ingest 增强完成后，同时完成了阶段 1“总体金额勾稽”和阶段 2“处置清单确定性规则”。实现顺序仍按“先总体核对、再清单规则、最后联合回归”执行，避免混淆读取问题与规则口径问题。

已完成的总体核对规则：

- `disposal_reconciliation_readability`：K.02.2 总体核对模块未达到确定性规则执行条件时，仅输出 `NEED_REVIEW`。
- `disposal_reconciliation_formula_source`：检查处置/报废总金额是否引用处置清单、Breakdown 金额是否引用 K.01；来源错误为 `FAIL`，无法确认时为 `NEED_REVIEW`。
- `disposal_net_value_recalculation`：检查 K.02.2 总体核对模块中净值是否等于原值减累计折旧减减值准备。
- `disposal_rollforward_reconciliation`：核对处置清单、K.02.2 总体核对模块和 K.01 后推处置行的原值、累计折旧、减值准备及计算净值。
- `disposal_difference_investigation`：差异超过 Lead SAD 时，检查对应金额维度是否标记需要进一步调查。

已完成的处置清单规则：

- `disposal_required_fields`：检查处置清单资产身份、原值、累计折旧、减值准备、处置日期和减少方式；净值列允许缺失。
- `disposal_list_net_value_recalculation`：处置清单存在净值列时，使用原值、累计折旧和减值准备重新计算并核对。
- `disposal_method_classification`：减少方式无法归类为出售、报废或其他减少时，输出 `NEED_REVIEW`；未分类金额不得直接纳入处置测试总体。
- `disposal_other_reduction_over_tt`：其他减少与出售/报废性质不同；金额超过 TT 或未读取到 TT 时，提示人工确认是否需要单独总体和其他审计程序。

已完成的选样输出规则（阶段 3）：

- `disposal_sample_pool_amount_match`：将 K.02.2a 样本池总体金额与处置清单中出售/报废净值核对，不使用包含其他减少的清单总减少金额。
- `disposal_sampling_te_cra_consistency`：检查 K.02.2a 使用的 TE、CRA 是否与 Lead 一致。
- `disposal_sample_replacement_reason`：存在替换样本但未说明替换原因时，输出 `NEED_REVIEW`。
- K.02.2a 行列位置不固定；选样输出已识别但 `usable_for_rules=False` 时，仅提示读取复核，不直接产生确定性差异结论。

已完成的 K.02.2 详细测试规则（阶段 4）：

- `disposal_test_attributes_complete`：检查 K.02.2 三个固定测试属性是否完整执行。
- `disposal_test_amount_recalculation`：检查净值、处置损益及售价差异的重算关系；净值使用原值、累计折旧和减值准备确认，不要求后推明细表直接提供净值。
- `disposal_sale_evidence_complete`：出售样本检查支持性证据金额和证据描述；报废样本不机械要求售价。
- `disposal_exception_followup`：测试属性为否、存在非零差异或其他异常但未记录后续处理时，输出 `NEED_REVIEW`。

已完成的 LLM 语义复核（阶段 5）：

- `src/llm/disposal_review.py`：围绕不执行理由、样本选择说明、证据描述、异常跟进和其他减少处理执行语义复核。
- LLM 仅辅助评价文字说明是否充分，不负责计算金额、匹配样本或覆盖确定性规则产生的 `FAIL` / `WARN`。
- LLM 处置语义复核已接入整本底稿流水线；未启用 LLM 时不影响确定性规则执行。

关键业务口径：

- 汇总页明确拒绝执行处置测试时，不运行处置总体金额规则和处置清单规则，避免对允许不编制的底稿误报。
- K.01 后推明细表不直接含净值项；K.01 净值仅由原值、累计折旧和减值准备计算。
- 处置清单净值列不是必需字段；存在时必须与重新计算净值一致。
- 累计折旧兼容正数和负数展示口径，净值重算使用累计折旧和减值准备的绝对值。
- 总体勾稽仅使用出售/报废减少；其他减少与未分类减少不混入 K.02.2 出售/报废测试总体。
- K.02.2 总体核对模块 `usable_for_rules=False` 时，只输出读取复核提示，不继续产生确定性金额差异结论。

接入情况：

- `src/rules/disposal_reconciliation.py`：阶段 1 总体核对规则。
- `src/rules/disposal_list_rules.py`：阶段 2 处置清单规则。
- `src/rules/disposal_sampling_output.py`：阶段 3 选样输出规则。
- `src/rules/disposal_detailed_test.py`：阶段 4 K.02.2 详细测试规则。
- `src/llm/disposal_review.py`：阶段 5 处置语义复核。
- `src/rules/disposal_runner.py`：按执行路径门控并统一编排总体核对、清单、选样输出、详细测试和样本一致性规则。
- `src/report/pipeline.py`：向处置规则传入处置清单、清单汇总、K.01 和 Lead，并在启用 LLM 时执行处置语义复核。
- `src/rules/registry.py`：新增规则均已注册为 implemented。

已验证：

- `.\.venv\Scripts\pytest.exe tests\rules\test_disposal_reconciliation.py tests\rules\test_disposal_list_rules.py tests\rules\test_disposal_consistency.py tests\rules\test_addition_test_package.py tests\report\test_workbook_pipeline.py tests\rules\test_registry.py -q --basetemp .pytest_tmp_disposal_rules_final`：`37 passed`
- `.\.venv\Scripts\pytest.exe tests\rules\test_disposal_sampling_output.py tests\rules\test_disposal_detailed_test.py tests\rules\test_disposal_consistency.py tests\rules\test_disposal_reconciliation.py tests\rules\test_disposal_list_rules.py tests\llm\test_disposal_review.py tests\report\test_workbook_pipeline.py tests\rules\test_registry.py -q --basetemp .pytest_tmp_disposal_stage345_final3`：`35 passed`
- FY26 SOP 示例包实测：处置规则输出 `0 issues`。
- 已验证汇总页明确拒绝执行时，即使工作簿残留处置清单，也不会触发处置清单或总体金额规则。

后续建议：

1. 使用更多实际处置底稿回归阶段 1–5，重点覆盖动态行列、字段名称变体、出售与报废混合、其他减少占比较高以及替换样本场景。
2. 继续验证 K.02.2a 已选样本与 K.02.2 实测样本之间的资产编号、净值和样本类型一致性边界，避免因底稿表述差异产生误报。
3. 结合实际 LLM 输出复核触发阈值和提示质量；LLM 结论继续保持辅助性质，不覆盖确定性规则结论。
## 2026-06-16 FAQC J 案例复测修复沉淀：新增测试与 Lead/K.01 误报收敛

本轮基于 `E:\FAQC\待优化0615.txt` 以及 `E:\AI file\固定资产质检agent\质检测试结果\待分析` 中 J 公司最新复测结果，重点处理“此前已矫正问题再次大规模误报”的风险。结论是：本次问题不是单一规则错误，而是读取层截断、业务口径误解、LLM 兜底越界、K.01 期初识别不稳共同叠加导致。

### 已修复问题

1. 新增清单被截断
   - 问题：整本 ingest 的 `max_rows` 参数被传入新增清单、处置清单、FA list 等资产级总体清单，导致 J 公司新增清单只读到前部记录，后续规则基于不完整总体判断，产生大量错误。
   - 修复：程序页仍可限行读取，但资产级总体清单改为完整读取，不再受程序页 `max_rows` 截断。
   - 验证：J 公司新增清单可读到 1006 条记录；购置新增金额恢复为 `5,852,456.94`，购置记录数为 588。

2. 新增测试总体口径被混淆
   - 问题：新增清单为完整性目的包含全部新增，包括购置和在建工程转入；但固定资产 K.02.1 新增测试默认测试购置新增。此前一度把“清单全部新增”误当作“新增测试总体”，使在建工程转入被错误纳入 K.02.1 异常判断。
   - 修复：K.02.1 Breakdown 购置金额继续取 K.01 后推明细表购置行；购置总金额继续取新增清单中的购置新增；选样输出样本池按购置总体核对。
   - 业务口径：在建工程转入默认在在建工程底稿测试，除非未开在建工程底稿且转固金额重大，否则不在固定资产新增测试中直接作为异常。

3. 新增 LLM 识别越界
   - 问题：LLM 识别层在看到“在建工程转入/转固”等非购置方式时，可能把完整性清单中的正常项目提示为特殊新增来源问题。
   - 修复：当非购置来源仅为默认在建工程转入/转固类项目时，LLM 不再输出 `special_addition_source` 类提示；LLM 仅作为兜底复核，不扩大 SOP 口径，不覆盖确定性规则结论。

4. Lead/K.01 期初识别误报
   - 问题：J 公司 Lead 中期初数可通过关键锚点定位，但 K.01 后推表内没有足够可靠的期初语义锚点。此前把泛化的“账面数”列误当作 K.01 期初列，导致期初原值、累计折旧、净值出现大额假差异。
   - 修复：K.01 期初勾稽只在识别到明确期初锚点时执行，例如年初、期初、上期末等语义；不按固定行列读取，也不把普通“账面数”默认视为期初。
   - 注意：用户确认的 `L64/L65、2023/12/31、审定数` 是 Lead 侧关键锚点信息，后续如要增强 K.01 期初识别，也必须通过锚点语义识别，不能硬编码行列。

5. Lead/K.01 差异展示收敛
   - 问题：同一底层差异可能同时触发累计折旧差异和派生净值差异，导致报告看起来像多个独立错误。
   - 修复：当原值、累计折旧、减值准备等组件差异已经存在时，净值差异作为派生影响合并展示，不再重复单独报错。

6. A3 与 Diff 类问题合并
   - 问题：Check with A3 与 Diff 相关问题在同一科目下可能重复展示。
   - 修复：同一科目的 A3/Diff/缺少说明合并为一个 issue，便于质检人员一次性复核。

### 本次暴露的关键教训

- `ingest` 读取底稿并整理字段时，程序说明页可以限行，但资产总体清单不能限行；否则规则读到的是不完整总体。
- 清单完整性口径和测试总体口径必须分开：新增清单可以包含全部新增，但 K.02.1 默认测试购置新增。
- 锚点识别必须优先于固定行列；即使用户指出某案例的行列位置，也只能作为理解样例，不能写成固定位置规则。
- LLM 兜底层应帮助发现“读错、漏读、语义可疑”，不能替代 SOP，也不能把正常业务口径扩大成异常。
- 大规模误报时，应优先建立案例最小回归基线，再修复明确根因，避免反复局部补丁。

### 当前验证结果

- 核心回归命令：
  - `.\.venv\Scripts\pytest.exe tests\ingest\test_workbook_ingest.py tests\rules\test_addition_rules.py tests\rules\test_addition_rollforward_reconciliation.py tests\rules\test_addition_sampling_output.py tests\rules\test_lead_rules_extended.py tests\rules\test_lead_check_with_a3_row.py tests\llm\test_addition_review.py -q --basetemp .pytest_tmp_stage12_final6`
- 结果：`59 passed`，仅有 pytest cache 权限类 warning，不影响规则结果。
- J 公司新增测试侧：新增清单完整读取后，购置总体与 K.01 购置行口径恢复一致，新增测试相关误报已明显收敛。
- Lead/K.01 侧：期初差异不再在缺少 K.01 明确期初锚点时强行判断；期末累计折旧差异及其派生净值影响合并展示。

### 待解决问题

1. 需要继续补充 J 案例完整回归
   - 当前已完成核心规则回归和关键读取验证，但仍建议用 J 公司完整流水线再跑一次报告和标注输出，确认 UI/报告层没有残留重复 issue。

2. 需要优化报告与标注层展示
   - 多个底层 issue 在报告中仍可能显得偏散，应继续做 finding 合并、批注定位去重、Question/Comment 文案压缩。
   - `QC_Locator` 等技术定位信息应隐藏或移至内部列，避免干扰审计人员阅读。

3. 需要继续完善日期与截止性规则
   - 新增资本化日期、处置日期、期后/期前截止等检查仍待补齐。

4. 需要继续完善控制转移证据复核
   - 对处置销售、报废、其他减少的支持性证据充分性，目前仍有较多需要 `NEED_REVIEW` 的人工判断场景。

5. 需要补强 K.01 期初锚点变体识别
   - 后续可增加对更多可靠期初锚点组合的识别，但原则仍是名称 + 内容 + 上下文锚点，不按固定行列。

6. 需要扩大案例层回归
   - J 公司只是本轮最小回归基线；后续应增加 G 科技、SOP 修改版、标准模板及更多实际底稿，形成新增、处置、Lead/K.01 的组合回归集。

### 下一步建议

优先顺序建议为：先跑 J 公司完整流水线确认报告和标注层残留问题，再处理报告展示去重与文案压缩，随后补充日期/截止性规则和 K.01 期初锚点变体。LLM 继续保持“兜底复核”定位，只在确定性规则无法判断或读取可疑时辅助提示，不进入金额勾稽主判断。

## 2026-06-18 Finding 追踪链第一批修复：K.02 新增/处置定位与批注回写

本轮针对“新增测试 finding 位置索引有误，且实际 comments 未成功添加为业务页批注”的同类风险，先处理 K.02 新增测试和处置测试中最影响可追踪性的第一批问题。结论是：问题主要不在导出层，而在部分规则产出的 `QcIssue` 缺少真实 `source_row`，或使用了虚拟 sheet 名，导致报告可以列出 finding，但标注副本无法回写到业务 sheet 的具体单元格。

已完成：

- `addition_sample_match`：K.02.1a 已选样本未进入 K.02.1 时，finding 现在优先指向 K.02.1a 的实际样本行；K.02.1 存在额外实测样本时，指向 K.02.1 的实测样本行。
- `addition_sample_match`：关键项金额差异、异常说明类 finding 补充了可用的 sheet/row 来源，避免仅落在 `K.02.1 / K.02.1a` 这种虚拟位置。
- `disposal_sample_match`：K.02.2a 已选处置样本未进入 K.02.2 时，finding 现在优先指向 K.02.2a 的实际样本行。
- `disposal_sample_match`：关键项数量不一致时，finding 指向 K.02.2a 关键项数量统计行；样本类型不一致继续指向 K.02.2 实测样本行。
- 导出层新增回归测试，确认带有真实 `source_sheet + source_row` 的 K.02.2 finding 会同时出现在 `Comments【归档前删除】`，并回写为业务 sheet 单元格批注。

未改变：

- 未改变新增/处置测试的规则结论、严重级别、SOP 判断口径或 LLM 辅助逻辑。
- 未改 frozen architecture、报告导出主流程或 Comments 表结构。
- 未处理所有历史 sheet-level finding；Lead、K.01、K.03、FA list 等其他程序的定位治理仍需后续按批次处理。

已验证：

- `.\.venv\Scripts\pytest.exe tests\rules\test_addition_consistency.py tests\rules\test_disposal_consistency.py tests\report\test_export_annotated_workbook.py -q`
- 结果：`24 passed`；仅有 pytest cache 权限 warning，不影响规则和标注结果。

后续建议：

1. 下一批优先排查 K.03 折旧测试、折旧政策复核、折旧政策相关 finding 是否仍存在虚拟 sheet、缺少 source_row 或无法业务页批注的问题。
2. 建议建立统一的 Finding 追踪链检查：每条 finding 至少能说明归属规则、来源 sheet、来源行、是否可批注、无法批注原因。
3. 对确实只能 sheet-level 定位的问题，应在报告层明确标记为“页级问题”，不要伪装成可定位到单元格的问题。

## 2026-06-23 Execution Ledger 规则执行台账沉淀

本轮新增 `execution_ledger`，用于区分“规则已执行且未发现异常”和“因资料不足或场景不适用而未执行”。它解决的是报告可解释性问题，不改变任何规则结论。

核心口径：

- `EXECUTED`：规则流程已经运行；如有 finding，则记录 `finding_count`。
- `DATA_INSUFFICIENT`：资料、工作表或读取结果不足，规则未执行；该状态本身不等于底稿错误。
- `NOT_APPLICABLE`：当前场景不适用，例如汇总页已明确拒绝执行某程序，相关细项检查不再机械运行。
- 台账只记录执行事实，不计算 severity，不替代 `PASS` / `WARN` / `FAIL` / `NEED_REVIEW`，也不新增业务判断。

接入范围：

- 新增 `src/rules/execution_recorder.py`，统一记录规则执行状态，并校验有 finding 的规则必须标记为 `EXECUTED`。
- 各 runner 按实际执行分支记录已执行、资料不足或不适用；覆盖 FA list、Lead、K.01、K.02.1、K.02.2、K.03 和交付完成度检查。
- `src/report/summary.py`、`src/report/export_json.py`、`src/report/pipeline.py` 输出并校验 `execution_ledger`。

设计边界：

- 台账属于 Finding Model / Report 的辅助说明，不属于 Control Plane 策略决策。
- Rules 仍是确定性结论来源；台账不允许把未执行规则推断为 PASS。
- LLM 语义复核仍只作为辅助 finding 来源，不通过台账覆盖确定性规则。

后续建议：

1. 后续新增规则时同步接入 `RuleExecutionRecorder`。
2. 对资料不足未执行的规则，优先写清楚缺什么资料。
3. 继续用测试覆盖 execution ledger 的状态汇总、finding 规则一致性和 JSON 输出结构。

## 2026-06-23 UI v2 与新增测试替换样本口径沉淀

本轮 UI 调整重点是让质检人员先看到“哪些问题需要处理、哪些检查没有执行、为什么没有执行”。UI 展示层只做阅读体验优化，不修改底层 finding、severity 或 JSON 报告结论。

UI v2 已调整：

- 首页结果按单个文件展示 Findings 总数和最高系统规则提示。
- Findings 分为高优先级问题、需人工判断和其他问题，分类仅用于页面展示。
- 新增“质检点执行摘要”和“质检点执行台账”，展示 `EXECUTED`、`DATA_INSUFFICIENT`、`NOT_APPLICABLE`。
- 增加外部数据状态提示：TE/SAD 当前优先从 Lead 识别，A3 映射、CRA 标准模板导入仍为后续接入项。
- 系统诊断、HTML 预览和下载区下沉，避免干扰质检人员优先处理 findings。

UI 边界：

- UI 分类不改 `severity`、`rule_id`、`source_sheet`、`source_row` 或 JSON 输出。
- UI 的“执行状态”只表示系统流程是否运行，不代表审计结论。
- 如果报告没有 `execution_ledger`，UI 只提示无法展示台账，不反推规则是否已执行。

新增测试替换样本口径：

- `src/llm/addition_review.py` 新增替换/替代/备选/备用样本边界。
- 未明确启用的替换样本，不属于必须进入 K.02.1 新增测试页的样本。
- LLM 不应仅因未启用替换样本未出现在 K.02.1，就要求解释“为何未测试”。
- 只有输入材料明确显示替换样本已启用、已替代原样本或已纳入实际测试时，才评价其测试一致性。

后续建议：

1. UI v2 需要用真实底稿人工复核一轮，确认质检人员能按“高优先级问题 -> 人工判断 -> 执行台账”顺序阅读。
2. 如果后续新增外部资料接入，例如 A3、CRA 标准模板，应同步更新 UI 的外部数据状态提示。
3. 新增测试 LLM 口径继续保持辅助性质，不覆盖 `addition_sample_match` 等确定性规则。

## 2026-06-24 UI ledger observation handoff

This note records the stabilized UI/execution-observation scope from this round. It intentionally uses ASCII text to avoid Windows console encoding drift during commit preparation.

Done:

- Kept the architecture unchanged: no checkpoint_catalog, no standalone runtime_trace, and no UI inference layer.
- Added bounded observation under execution_ledger.items, with only path, inputs, checks, and notes.
- Added observation for the first 3 pilot rules: addition_sample_match, rollforward_fa_list_reconciliation, and lead_rollforward_tb_reconciliation.
- Updated the UI ledger columns to show checkpoint, rule number, rule_ID, execution status, check method, dependent materials, key check summary, and finding/output count.
- Renamed the summary card wording to clarify that the count is the current run's execution points from execution_ledger, not the full checklist population.
- Sorted the ledger by audit procedure order: global/delivery, K.00, K.01, FA list, K.02.1, K.02.2, K.03.1, K.03.2, K.03.3, then LLM/other.
- Restored the system diagnostics panel by adding the missing output-quality renderer.
- Completed registry display metadata for K.03.2, K.03.3, and related LLM rules, with tests to prevent question-mark mojibake from returning.

Frozen boundaries:

- registry remains static rule metadata.
- execution_ledger remains the only runtime truth source.
- findings remain exception/result records only.
- UI only joins, sorts, formats, and displays; it must not infer audit conclusions or execution status.

Still open:

1. Only 3 pilot rules currently have full observation.
2. Full registry metadata for check method, dependent materials, and key check summary is not yet complete across all rules.
3. The full-checklist-vs-current-run missing-execution explanation remains deferred.
4. Different workpapers may produce different ledger counts because the ledger records the current run facts, not the full checklist population.

Next recommended work:

1. Extend observation rule-by-rule, starting with high-value deterministic rules in K.01, K.02.1, K.02.2, and K.03.
2. Continue enriching registry metadata as static auditor-readable descriptions only; do not store current-run input facts there.
3. If missing-execution visibility is needed later, prefer a narrow missing-rule list over a complex reconciliation panel.
4. Keep registry display tests that block question-mark mojibake and lock key K.03 display names.

## 2026-06-24 K02 anchors, Lead thresholds, Summary LLM, and K03 Chinese cmts

This note records the repair scope completed after the UI/ledger round. The scope is intentionally limited to K.02 addition/disposal anchoring, K.00 Lead threshold access, summary-page LLM waiver semantics, and K.03 comment wording. It does not change the frozen architecture, severity model, or report structure.

### K.02 addition and disposal anchors

The core issue was that some K.02 findings were landing in one generic Comments cell because the issue anchor was not a real business-sheet anchor. The fix direction is:

- Findings should carry a real source_sheet plus source_row whenever a specific workbook row exists.
- For addition sampling and disposal sampling, sample-level findings should land on the actual sample output or test-sheet sample row, not on a generic sheet-level placeholder.
- Report annotation now supports source_col so a finding can land on the relevant business column when the rule knows the field-level anchor.
- When multiple findings truly share the same source cell, cell comments are merged instead of overwriting each other.

Important business rule for K.02 addition:

- K.02.1 addition test mainly covers purchase-type additions.
- Addition list totals must distinguish purchase additions from non-purchase additions such as transfer-in, construction in progress transfer, merger, reclassification, or allocation.
- If the K.02.1 test page contains formulas or links to source sheets, prefer those workbook formulas/links as the first source of truth.
- If the test page uses hard-coded numbers, re-check against the underlying addition list and K.01 rollforward because hard-coded numbers are the most likely to become stale.
- K.02.1a sample amount differences should land on the K.02.1a sample amount row, not all on the K.02.1 test page.

### Lead threshold fixed entry point

TE, SAD, and TT should be read through the Lead helper entry point instead of each rule finding thresholds by itself.

- `lead_te()` reads TE from K.00 Lead.
- `lead_sad()` reads SAD from K.00 Lead.
- `lead_tt()` reads TT from K.00 Lead CRA/TT rows and chooses the reliable positive overall threshold value.
- Disposal other-reduction-over-TT now uses this shared Lead TT entry point.

This reduces repeated threshold-search logic and makes later rules more stable: future K.01/K.02/K.03 rules should call the Lead helper first, and only fall back to local parsing when the helper cannot provide a reliable value.

### Summary page LLM waiver prompt

The summary-page LLM prompt now constrains addition/disposal waiver reasoning with a threshold decision tree instead of treating TE, TT, and SAD as parallel standards.

Current intended meaning:

- SAD layer: if the addition/disposal amount is below K.00 Lead SAD, the amount basis is normally acceptable. Do not require extra TE or TT support unless the input shows nature-risk exceptions.
- TT layer: if the addition/disposal amount is below K.00 Lead TT, the amount basis is acceptable, but the reason still needs to state or support that there are no nature-risk exceptions. Do not require TE.
- TE layer: if the reason only says the total amount, disposal net value, or addition amount is below K.00 Lead TE, that is not enough by itself. It must also state that no single item exceeds TT and that no nature-risk exception exists.
- Vague wording such as "small amount", "immaterial", or "below materiality" without a named SAD/TT/TE basis remains insufficient or unclear.

The prompt also requires the model rationale to state which SAD/TT/TE layer was applied, and the suggested action should only ask for the missing information at that layer.

### K.03 Chinese cmts output

K.03 rule output wording was changed from English to Chinese for auditor-facing comments.

- `k03_tod_by_item` messages now describe by-item depreciation-test issues in Chinese, including missing detail table, missing key depreciation fields, over-SAD differences, total difference issues, and K.03 vs K.01 depreciation reconciliation.
- `k03_policy_review` messages now describe depreciation-policy review issues in Chinese, including unreadable policy table, missing policy sections, policy change without explanation, FA list useful-life/rate mismatches, and obvious policy anomalies.
- The rule logic and severity model were not intentionally changed; this is an output wording repair.

### Verification notes

Focused verification completed in this round:

- `pytest tests\\llm\\test_summary_psp_review.py -q -p no:cacheprovider -k "not weak_match"` -> 7 passed, 1 deselected.
- Earlier focused checks for Lead TT and disposal threshold behavior passed: `tests\\rules\\test_disposal_list_rules.py` -> 8 passed.

Known environment note:

- Full `tests\\llm\\test_summary_psp_review.py` currently hits a Windows pytest temp-directory permission problem on the test that uses `tmp_path`. The prompt-related tests passed; the remaining error is environmental temp-directory access, not a summary LLM assertion failure.

Next recommended work:

1. Re-run the real workbook through the UI and inspect K.02 addition/disposal Comments anchors on the annotated workbook.
2. Confirm summary-page waiver LLM output no longer asks for TE/TT when the reason already satisfies the SAD layer.
3. Extend the shared Lead threshold helper pattern to future rules before adding new local threshold parsing.
4. Add a small K.03 output-language regression later if the project wants to lock Chinese cmts wording at the test level.

## 2026-07-03 HOW governance closure snapshot

This is a HOW governance closure snapshot, not a final product release.

Snapshot base HEAD before this handoff note: `8b47394`

Coverage summary under the current ledger / HOW diagnostics scope:

- FA list: 6/6 evidence-level HOW.
- Lead / PSP: complete under the current ledger diagnostics scope.
- K.01: current deterministic ledger 6/6 evidence-level HOW, with 2 known issues tracked separately.
- K.02.1: 8/8 evidence-level HOW under the established batch scope.
- K.02.2: 17/17 evidence-level HOW under the established batch scope.
- K.03: 17/17 evidence-level HOW.
- Global diagnostics on `tests/fixtures/workbook_with_lead.xlsx`: legacy=0, missing=0, evidence-level HOW=62.

Scope note:

- The completion above is based on the current ledger / HOW diagnostics scope.
- It does not mean every registry rule is covered under every possible fixture or workbook variant.
- `execution_ledger` remains the runtime fact record, and `observation` records evidence-level HOW only. UI / JSON should display structured results and should not infer missing explanations.

Remaining known issues:

1. K.01 table4 notes classification / extraction known issue.
2. K.01 table3 material difference with note pass/fail rule-position known issue.
3. Packaging demo files are still not governed or committed: `fixed_asset_qc_agent.spec` and `scripts/package_launcher.py`.

## 2026-07-06 Rule Execution Matrix category clarification

The Rule Execution Matrix is a governance diagnostic table. It explains where each observable check went in the current run. It is not an audit conclusion table and does not mean every rule has been executed in every workbook.

Current matrix categories:

- `implemented_rules`: 82 rules from `registry.py` with implementation status `implemented`.
- `delivery_checks`: 2 delivery-stage checks, `first_delivery_standard` and `final_delivery_standard`.
- `runtime_guardrails`: 1 runtime protection check, `lead_ingest_readability`.

Delivery checks are important delivery-stage checks. They are separated because they run only when a delivery stage is supplied. They should not be described as low-value or incidental non-registry observations.

Runtime guardrails are protection checks, not normal business QC rules. `lead_ingest_readability` exists to stop or explain downstream Lead checks when the Lead sheet is not reliable enough for deterministic rules.

Current guardrail scope:

- Lead currently has an explicit readability guardrail: `lead_ingest_readability`.
- Other modules have some local readability or precondition checks, but not a unified module-level `ingest_readability` guardrail.

Backlog, not implemented in this round:

1. FA list ingest_readability guardrail.
2. PSP / Summary ingest_readability guardrail.
3. K.01 rollforward ingest_readability guardrail.
4. K.02.1 addition ingest_readability guardrail.
5. K.02.2 disposal ingest_readability guardrail.
6. K.03 depreciation / policy ingest_readability guardrail.

Boundary:

- This clarification does not change rule conclusions, finding counts, severity, registry rule status, UI, LLM behavior, or execution_ledger structure.

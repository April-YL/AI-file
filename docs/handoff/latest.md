# 最新交接

> 更新时间：2026-07-16。本文只保留当前可执行基线、已知边界和下一步；历史阶段记录见 [`archive/through-2026-07-13.md`](archive/through-2026-07-13.md)。

## 当前基线

- 分支基线：`main`；本次Pilot锁定前父提交为`45587d8 Configure QC history storage on project drive`，锁定后的准确版本以当前文件所在Git提交为准。
- 本次基线包含此前累计开发改动及本轮版本追溯改动；是否锁定由UI结合`src/`和`pyproject.toml`的Git状态实时显示。本阶段未执行`push`。
- 产品形态：本地 Python 程序 + Streamlit UI + 可选 OpenAI 兼容 LLM API。
- 必交付：结构化质检报告和 `*_qc_annotated.xlsx` 底稿标注副本均已有可运行首版。
- 规则真源：`src/rules/registry.py`；UI/JSON 只能展示 runner 和 `execution_ledger` 记录的本次运行事实。
- 自动结论仅使用 `PASS`、`WARN`、`FAIL`、`NEED_REVIEW`；LLM 不得单独把规则 `FAIL` 改为 `PASS`。

## 当前不可偏离的目标

- Pilot 两批测试的目标是区分真实问题、系统误报、系统漏报、资料不足和待人工确认，不是消灭 findings；原质检“无重大 findings”不代表不存在规范性提示。
- 已确认批量异常的最低层共同根因是工作表/字段识别过早定案、缺少候选证据验证和规则级 Readiness，导致错误字段进入规则形成批量确定性输出，或工作表错分后规则未执行。
- 修复顺序固定为：工作表与字段识别 → 字段可信度与规则级 Readiness → 统一 Orchestrator / LLM Router → 具体规则 → Finding、报告和标注。必须沿真实执行链在最低共同根因层做最小系统性修复，禁止按样本打补丁。
- 目标架构同时包含统一 Orchestrator 和统一 LLM Router。LLM Router 统一管理总开关、`identification`、`rule_review`、`hybrid_rule`、`narrative` 分能力开关及按规则控制；LLM 可参与识别兜底、纯 LLM 语义规则和代码 + LLM 联合规则，不只是报告增强。
- 错误或不可信字段不得产生确定性 `FAIL`；资料不足不得记为 `PASS`；规则未执行不得静默跳过；LLM 不得绕过 registry 和统一编排直接生成正式 finding，也不得无依据把确定性 `FAIL` 改为 `PASS`。
- 本轮纳入 FA list 是为修复已确认的批量误报和检查覆盖漏失，不改变 K.00–K.03 的长期主线。正式决策见 [`ADR-0003`](../decisions/ADR-0003-unified-orchestrator-and-llm-governance.md)，规则治理见 [`fa_qc_governance_plan.md`](../architecture/fa_qc_governance_plan.md)。循环A和循环B的最小结构及识别止损能力已形成候选实现，仍须结合真实样本持续校准规则口径。

## 本地运行历史存储

- UI 运行历史已从 Windows 用户目录迁移到项目盘默认目录 `E:\AI file\local_data\fixed_asset_qc`；`history.db` 保存项目及运行元数据，`artifacts/<run_id>/` 保存 JSON、HTML 和标注底稿。
- 可通过环境变量 `FA_QC_DATA_DIR` 覆盖默认位置；配置示例见 `.env.example`。`local_data/` 已加入 `.gitignore`，真实底稿和本地交付物不得提交。
- 2026-07-14 已将原 C 盘 23 次运行、11 个项目和 23 个产物目录复制到 E 盘；复制核对为 60 个文件、47,599,758 字节，源目标一致。
- C 盘原目录 `C:\Users\Admin1\.audit_workpaper_review_agent` 暂作迁移备份，未删除。需重启 UI 后再抽查历史查看及 JSON、HTML、标注底稿下载；确认正常后，删除旧副本仍须单独授权。
- 路径解析聚焦测试为 `2 passed`；本轮测试未新增 workspace hygiene 问题。该结果不是全仓测试结论。

## Pilot版本追溯与T02验收

- 已建立统一版本信息，当前产品版本为`0.1.0`，Pilot构建号为`PILOT-20260716.01`；版本快照随新运行进入报告JSON、SQLite运行记录、UI和标注Excel的`QC_执行追溯`页。
- UI左下角展示当前程序版本和锁定状态；复核结果页展示所选运行对应的运行版本。运行28–40没有历史版本证据，统一显示“历史未记录”，不得用当前版本倒填。
- SQLite仅增加`agent_version`、`pilot_build`、`source_revision`和`lock_status`四个可兼容字段。升级前已备份`local_data/fixed_asset_qc/history.db`；升级后与备份逐字段比较，原运行数据和项目数据一致。
- 升级后仍保留39次历史运行，编号范围1–40；运行28–40的报告JSON均存在，39条旧记录的新增版本字段均为空。
- 版本追溯专项测试为`32 passed`，workspace hygiene检查未发现本轮新增问题；用户已人工确认左下角版本显示、历史记录可见以及运行40显示“运行版本：历史未记录”。该结果不是全仓测试结论。
- `PILOT-20260715.01`为循环A已提交基线；`PILOT-20260716.01`为循环B候选基线。源码提交前UI应显示“未锁定”，形成当前Git基线且运行源码干净后应显示“已锁定”。源码锁定只表示代码可追溯，不等同于业务准确性最终验收。本地底稿、测试资料和其他源码目录外文件不参与锁定判断。
- 测试批次和回归轮次继续在Pilot测试台账中管理；每次形成新的正式测试构建时递增Pilot构建号，新运行追加版本快照，不覆盖历史记录。

## 当前覆盖

| 模块 | 当前能力 | 重要边界 |
| --- | --- | --- |
| 汇总页 / PSP | 程序执行、拒绝理由和工作表引用等检查 | 复杂豁免理由仍可能需要人工判断 |
| K.00 Lead | 基础信息、CRA/TT、预期分析、变动说明、调整汇总等读取与规则 | 项目背景和重大判断不自动替代 |
| K.01 后推 | 六区块识别、列/金额勾稽、FA list 和折旧费用等规则 | 仍有个别版式和 notes 分类边界 |
| K.02 新增/处置 | 清单、总体勾稽、选样输出和详细测试规则已接入 | 真实底稿锚点与证据充分性需持续回归 |
| K.03 折旧 | SAP/TOD/政策路径识别、runner 分派、关键参数和差异规则 | 特别风险、实体类型、复杂政策合理性仍需人工复核 |
| 报告与标注 | JSON、HTML、UI、执行台账、Comments 表和单元格批注 | 正式 Excel 汇总报告仍待完善 |
| LLM | 已形成统一 Router 与分能力开关候选实现；识别层可在歧义时调用受控兜底 | 默认关闭；LLM只能从系统候选中辅助选择，失败必须降级，不得自由映射字段或单独改写确定性结论 |

## 循环B候选基线与真实样本复测（2026-07-16）

- 循环B沿现有执行链收口FA list、新增清单和处置清单的Sheet身份准入、三类List隔离、字段候选证据、规则级Readiness、受控LLM识别兜底、最多一次局部重整及批量异常问题簇防护；没有按客户名称、文件名、运行编号或固定单元格增加样本补丁。
- 用户已复测5张经典底稿，其中4张 findings 已恢复至合理水平，说明此前由错误Sheet、错误字段或证据不足引起的主要批量异常已得到控制。
- Run 62仍存在较多 findings，其中349条来自`unique_asset_id`。当前只读分析确认FA list和“固定资产编号”列识别基本合理，主要疑点是系统在缺少实体或子资产维度时过早采用单一资产编号作为唯一键；尚不能确认这些结果是真实问题、误报或二者混合。
- Run 62暂列独立待确认事项，不计为循环B已修复，也不据此否定另外4张的回归结果。后续须先确认唯一键业务作用域，再决定是否修改识别层身份口径、规则准入或仅优化问题簇展示。
- `PILOT-20260716.01`当前只作为循环B候选基线；形成独立Git提交并保持运行源码干净后，可锁定源码版本。Run 62未完成确认前，不宣称循环B已完成业务准确性最终锁定。

## K.03 最新事实

- `K03ExecutionProfile` 是 K.03 工作簿级识别真源；rules 不得重新猜测程序路径。
- 新增 K.03 执行路径与程序总控：`k03_program_execution_consistency`、`k03_depreciation_path_identified`、`k03_path_combination_consistency` 已进入 registry、主 runner、execution ledger 和 observation。
- 总控只读取汇总页程序状态与 `K03ExecutionProfile`：K.03.1 SAP、K.03.2 TOD、K.03.3 政策分别比较；政策保持独立，不得由 SAP/TOD 替代。
- 实际执行只认组件状态 `EXECUTED`。`TEMPLATE_ONLY`、`INCOMPLETE`、`AMBIGUOUS`、孤立的 K.03.2a 选样输出和 `primary_depreciation_path` 标签本身均不得作为已执行证据；K.03.2a 也不得被错当成 K.03.2 主程序。
- 路径组合口径：允许一条 SAP 与一条 TOD 作为补充组合；中/高精度 SAP 同时执行、TOD by-item/抽样同时执行或同角色存在多张已执行页时转 `NEED_REVIEW`。汇总明确 SAP/TOD 均不执行且无实际路径时，总控记 `NOT_APPLICABLE`；资料不明时记 `DATA_INSUFFICIENT`。
- 汇总与执行不一致、重复汇总行勾选冲突、实际已执行但汇总缺少对应程序行时转 `NEED_REVIEW`。存在 finding 的聚合规则保持 `EXECUTED`；无 finding 但任一分支无法比较时记 `DATA_INSUFFICIENT`，避免虚假显示总控已完整执行。
- 原 `psp_completion` 中 K.03 汇总勾选与实际执行的重复 finding 已迁移到总控规则；PSP 对 SAP/TOD 二选一的拒绝理由豁免逻辑继续保留。
- 总控 observation 记录汇总程序、状态、来源行及组件 role、sheet、execution state，未改变 execution ledger 或报告 JSON 顶层结构。
- SAP 中精度、SAP 高精度、TOD by-item、TOD 抽样按实际执行路径分别进入 runner；K.03.3 折旧政策复核保持独立必要程序。
- `sap_precision_selection` 使用 Lead 计价/计量（V/M）CRA；中精度 SAP 在 CRA 不低于 Low 时需结合实际执行的 TOD 补充程序复核。
- `sap_te_consistency` 比较 SAP TE 与 Lead TE；`sap_high_cra_consistency` 只适用于高精度 SAP，并比较 Lead V/M CRA。
- 新增 `sap_medium_category_deviation_explanation`：按中精度 SAP 横向版式逐资产类别及合计读取偏差、偏差阈值、底稿超阈值判断、同列 NB 索引和 Notes 正文；各类别及合计均以偏差绝对值与各自阈值比较。
- 新增 `sap_high_category_deviation_explanation`：按高精度 SAP 纵向版式逐资产类别读取差异、已分配偏差阈值、底稿超阈值判断和可追溯 Notes。
- 两条规则的共同口径：未超阈值不产生 finding；金额判断与底稿“是/否”矛盾时为 `NEED_REVIEW`；超阈值无对应说明为 `FAIL`；有对应说明为 `NEED_REVIEW`，说明充分性继续由人工复核。
- Notes 必须与具体类别或合计建立可追溯关系；全表任意 Notes 或总体结论不得替代逐项说明。NB 标记按完整编号精确匹配，避免 `NB1` 与 `NB10` 错配；“待补”、`N/A` 等占位内容不视为有效说明。
- 类别、偏差、阈值或“是否超过”无法可靠读取，以及关键金额为无缓存公式时，专项规则记录 `DATA_INSUFFICIENT`，不得把空值当作零或默认通过。
- 适用但参数不可可靠读取时记录 `DATA_INSUFFICIENT`；非对应路径记录 `NOT_APPLICABLE`，不得默认通过。
- 多张已执行 SAP 页分别检查并保留 observation。最近聚焦验收为 `32 passed`，不是全仓测试结论。
- 本阶段两位独立子代理分别复核中精度横向链路和高精度纵向链路；发现并修正 Notes 占位符误放行、空白超阈值判断未降级、NB 精确绑定测试不足等准确性问题。最终 SAP/registry/runner/覆盖矩阵聚焦验收为 `39 passed`，且本轮 workspace hygiene 检查通过；该数字不是全仓测试结论。
- K03 3A TOD 抽样规则闭环已完成：K.03.2 TOD 抽样主测试表与 K.03.2a 选样输出改为基于语义锚点、表头字段组合、数据形态和区块边界动态识别；生产逻辑不使用固定行号、列号、单元格地址或固定 sheet 顺序。
- TOD 抽样 9 条子规则已接入 registry、runner、execution ledger、observation 和测试：选样输出配套、抽样货币单元、TE 一致性、总体与 K.01 勾稽、样本数量、样本编号、测试属性、差异跟进、测试结论。
- 真实 SOP 只读验证：K.03.2 主测试表和 K.03.2a 选样输出均唯一识别；主测试 7 个资产编号与选样输出 7 个默认应测试样本一致，5 个替换样本保留为候补池，未自动计入默认测试集合。
- 最近 3A 聚焦验收：TOD 规则/registry/ledger `41 passed`，动态角色与版式变体 `10 passed`，新增闭环门槛 `3 passed`；本轮未新增 workspace hygiene 问题。
- K03 3B 大型底稿读取性能已优化：真实 SOP K03 组件读取从约 `118s` 降至约 `16.8s`；读取逻辑仍覆盖真实有值行，大型 by-item 明细本轮识别 `11,440` 行，只跳过纯格式造成的虚假使用范围尾部。
- 3B 真实 SOP 只读验证识别 6 个 K03 组件页：SAP 中精度、SAP 高精度、TOD by-item、K.03.3 政策复核、TOD 抽样主表、K.03.2a 选样输出；K.02 和“本期计提”等非 K03 程序页未被纳入 K03 组件。
- 3B 聚焦验收：新增远端格式膨胀用例通过；K03 ingest 重点用例 `8 passed`；非本地 K03 ingest 用例在排除一个历史路径口径用例后 `26 passed, 3 deselected`。排除项涉及“参数型 SAP 页是否进入 executed path”的定义口径，留待后续 K03 路径口径校准，不属于 3B 性能范围。
- K.03 总控最终聚焦验收覆盖总控规则、K.03 runner、PSP 迁移、registry、execution recorder 和覆盖矩阵，共 `83 passed`；两位只读监督子代理最终均确认无剩余 P0/P1、无本阶段范围漂移。该结果不是全仓测试结论。

## 已知风险

1. checklist 尚未全部自动化；不得把 registry 外的规划项展示为已执行。
2. K.01 table4 notes 分类、table3 重大差异与说明位置仍是已知校准点。
3. K.02/K.03 对真实底稿变体的识别和单元格锚点仍需持续回归。
4. LLM 调用目前分散且部分发生在规则执行之后，尚不能稳定承担识别兜底、纯 LLM 语义规则和联合规则；金额勾稽、唯一性、必填等确定性部分仍须由代码基于已验证字段执行。
5. 仓库中标准资料可供阅读；真实案例库、`.env` 和本地质检输出不得提交。
6. 真实 SOP 整本加载性能已在 K03 3B 收口；仍需注意纯格式/批注/公式无缓存等非值型证据不应被误当成 by-item 明细数据。
7. 新增 SAP 类别偏差说明规则已用脱敏构造底稿覆盖关键边界，但仍需用更多真实脱敏版式回归类别表头、合计列、NB 位置和 Notes 区块变体。
8. K.03 总控已覆盖构造用例，但仍需用真实脱敏汇总页回归程序编号、合并状态单元格、缺行和重复行等版式变化；执行画像本身识别错误时，总控应保持 `DATA_INSUFFICIENT`，不得自行重新扫描工作表猜路径。

## Pilot 第1批测试状态

- 第1批覆盖运行28–40，共13张底稿；本地测试台账记录959条Agent原始问题，并归集为284个待复核问题簇。
- 该批样本按原质检口径均为“无重大审计风险 findings”，但仍可能存在规范性提示；不得据此把Agent全部finding视为误报。
- 当前不要求另有质检人员 findings 清单。标准答案由用户结合底稿逐条确认；大模型二次复查只能形成疑似漏报候选，用户确认后才计为漏报。
- 第1批运行对应代码版本未锁定，只用于发现和分析问题，不用于严格衡量版本提升幅度。
- 本地台账和真实底稿、报告、标注副本均留在`local_data/`或本地资料目录，不提交Git；本文不记录真实公司名称和逐条真实问题。
- Pilot完整流程见[`../pilot-testing-and-repair-workflow.md`](../pilot-testing-and-repair-workflow.md)。

## Pilot 待办顺序

| 顺序 | 待办 | 当前状态 | 完成标志 |
| --- | --- | --- | --- |
| T01 | 沉淀Pilot测试与修复规程 | 已完成 | 流程、测试策略入口和handoff已更新 |
| T02 | 建立版本锁定与展示机制 | 功能已完成，随当前基线锁定 | UI、JSON、运行历史和Excel追溯已使用统一版本信息；锁定状态由运行源码Git状态实时确定 |
| T03 | 复核第1批运行28–40 | 可只读开展 | 用户完成真问题、误报、资料不足和疑似漏报确认 |
| T04 | 审计第1批Excel标注副本 | 可与T03同步只读开展 | 形成格式、定位、批注和原底稿完整性问题清单 |
| T05 | 生成正式Repair Queue | 等待T03/T04 | 具体问题满足Frozen状态、分级、证据和验收要求 |
| T06 | 分批实施系统性修复 | 等待修复范围确认 | 基于真实代码链路修复，不使用单案例补丁 |
| T07 | 第1批回归测试 | 等待修复完成 | 原问题修复、正常样本无新增误报、Excel输出通过 |
| T08 | 开展第2批扩大样本测试 | 等待第1批稳定 | 使用新测试批次和锁定构建版本追加测试 |
| T09 | Pilot阶段汇报 | 等待第2批 | 形成可追溯的测试、问题、修复和回归汇报 |

T03和T04可以同步只读开展；所有代码、配置、测试产物和文档写入仍须按`docs/agent-collaboration.md`列明范围并取得确认。P0–P3只用于已确认具体问题，不用于T01–T09项目待办。

## 循环 A 与 Run 43 回归验收（2026-07-16）

- 循环 A 已完成最小 Orchestrator、统一 LLM Router、识别 Readiness 与证据契约的首轮收口；本节当前状态优先于上文尚未实施统一 Router 的历史描述。
- 同一脱敏样本的原 Run 43 共输出 6,178 条 findings；锁定基线回归中，LLM 关闭的 Run 58 为 11 条，LLM 开启的 Run 59 为 12 条。原值、使用年限、新增必填和残值率等三个批量问题簇（2,545 / 2,028 / 1,591 条）已由字段可信度判断与规则级 `DATA_INSUFFICIENT` 阻断，不再生成确定性批量 FAIL。
- Run 59 的执行台账为：51 条已执行、16 条 `DATA_INSUFFICIENT`、37 条 `NOT_APPLICABLE`，并记录 9 次经 Router 路由的 LLM 调用。结果说明规则语义与代码+LLM联合路径可运行；本样本未触发 identification 识别兜底，因此不能据此宣称识别兜底已经过真实样本验收。
- 回归发现 PSP 不执行理由的 LLM 结果会参与 `psp_completion` 最终判断，故其能力分类已从纯 `rule_review` 收口为 `hybrid_rule`，并归属 `psp_completion`；纯汇总页语义 finding 仍保持 `rule_review`，未改变规则口径。
- Run 59 中 4 条新增清单语义提示属于同一问题簇，暂保留为循环 B 的准确性复核与报告层降噪候选；本次不通过单样本补丁消除。
- 本次验收不提交真实底稿、真实报告、标注副本或本地运行数据库；历史运行数据未修改。

## 推荐下一步

1. 用脱敏真实整本底稿回归 K.03 总控，重点核对汇总页 K.03.1/K.03.2/K.03.3 状态、组件 `EXECUTED` 状态、允许的 SAP+TOD 组合及政策独立性，并检查报告 finding 与底稿标注锚点一致。
2. 同步回归 SAP 中/高精度类别偏差说明规则，优先核对类别及合计、NB 索引、Notes 正文和单元格标注锚点。
3. 回到原 K03 计划文档核对阶段 4 by-item 校准范围，优先确认 by-item 边界、样本/总体口径、差异跟进和证据字段的自动化价值。
4. 对 K.00–K.03 高价值确定性规则逐条补齐 observation 和边界测试。
5. 完善正式 Excel 质检报告，同时保持报告与底稿标注 findings 一致。
6. 拓展其他科目前，先建立独立领域词典、checklist 映射和治理准入清单，不直接复制固定资产结论。

## 接手阅读顺序

1. [`../../README.md`](../../README.md)
2. [`../ONBOARDING.md`](../ONBOARDING.md)
3. [`../architecture/fa_qc_governance_plan.md`](../architecture/fa_qc_governance_plan.md)
4. [`../qc-checklist.md`](../qc-checklist.md)
5. [`../planning/program-qc-coverage-index.md`](../planning/program-qc-coverage-index.md)

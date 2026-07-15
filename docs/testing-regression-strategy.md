# 测试与回归策略

## 目标

本策略用于固定资产质检 Agent 开发中后期的 bug 修复和规则扩展。核心目标不是“每次都跑最多测试”，而是**按修改影响选择最小有效测试**，防止：

- token、时间和 LLM 额度消耗过快；
- 同一个问题反复修改；
- 修 A 破 B；
- 读取层 bug 被误当成规则 bug；
- 报告层或 UI 重复展示被误当成规则重复；
- execution_ledger 没记录导致检查过程继续黑箱化。

默认原则：先只读诊断，确认修改范围后执行锁定；测试也受确认范围约束。

## Pilot 测试入口

真实底稿 Pilot 的结果复核、版本锁定、人工标准答案、Repair Queue、Excel 标注副本审计和管理层汇报，统一按[`pilot-testing-and-repair-workflow.md`](pilot-testing-and-repair-workflow.md)执行。

进入 Pilot 回归前必须记录产品版本、Pilot 构建版本、测试批次和回归轮次。没有锁定构建版本的历史批次可以用于发现问题，但不得用于严格衡量版本提升幅度。当前 Pilot 由用户结合底稿逐条确认标准答案；大模型独立复查只形成疑似漏报候选，不能自动批准漏报。

修复前必须沿`ingest → runner → rules → execution_ledger → report → annotation → UI`进行只读诊断，在最低正确层做最小系统性修复。不得按真实客户名称、底稿文件名、运行编号或单一固定行号做补丁式修复。

## 测试分级

| 级别 | 名称 | 适用场景 | 默认动作 |
| --- | --- | --- | --- |
| L1 | 单规则 / 单函数小测试 | 单条规则、单个 parser、单个 report helper | 优先选择，跑对应 `tests/` 小文件或说明建议命令。 |
| L2 | 四案例结构摘要回归 | 影响 sheet 识别、字段映射、runner、关键勾稽 | 使用 B/G/H/J 的结构摘要字段做对比。 |
| L3 | 整本 pipeline 回归 | 影响 `pipeline.py`、跨 ingest/rules/report 编排 | 选择 B 或 J 跑整本流水线；默认不生成标注副本。 |
| L4 | 报告 / 标注 / UI 产物验收 | 改 JSON、HTML、Comments、标注副本、UI 下载 | 需要明确确认后生成产物；优先 B，小样本不够时加 J。 |
| L5 | 完整测试 | 大范围重构、提交前专项验收、用户明确要求 | 使用项目脚本跑完整或较大范围测试。 |

默认从 L1 开始。只有当修改影响跨层、输出结构或用户明确要求时，才升级到 L2–L5。

## 修改范围与推荐测试

| 修改范围 | 最小测试 | 升级条件 |
| --- | --- | --- |
| `src/ingest/summary_sheet.py`、PSP 读取 | L1 summary/PSP ingest 测试；L2 检查 B/G/H/J 的 `summary` 和 `summary_programs` | 如果影响 PSP findings，再跑对应 rules/report 小测试。 |
| `src/ingest/lead_*` | L1 Lead ingest 测试；L2 检查 B/G/H/J 的 Lead sheet、CRA 行、变动行 | 如果影响 Lead rules，再跑 Lead 规则测试。 |
| `src/rules/lead_*` | L1 对应 Lead 规则测试 | 如果规则依赖真实底稿结构，补 L2 Lead 案例摘要。 |
| `src/ingest/rollforward_*`、`src/rules/rollforward_*` | L1 K.01 ingest/rules 测试；L2 检查 B/G/H/J 的 K.01 选择和勾稽基线 | 如果影响候选排序，重点看 G/H/J。 |
| `src/rules/addition_*`、新增读取 | L1 新增相关测试；L2 检查 B/G/H/J 的新增清单、测试 sheet、选样输出 | 如果生成 report finding，补 L3 B 或 J。 |
| `src/rules/disposal_*`、处置读取 | L1 处置相关测试；L2 优先 G/H/J | J 是完整执行正向案例；G/H 是缺失或豁免边界案例。 |
| `src/ingest/k03_*`、`src/rules/k03_*` | L1 K.03 测试；L2 检查 B/G/H/J 的 K.03 sheet | 如果候选误入 K.01，重点看 G/J。 |
| `src/rules/registry.py` | L1 `tests/rules/test_registry.py` | 如果新增规则进入 UI/report，补对应模块测试。 |
| `src/rules/execution_recorder.py` | L1 `tests/rules/test_execution_recorder.py` | 若字段结构变化，补 report/UI 读取检查。 |
| `src/report/pipeline.py` | L3 B 或 J 整本 pipeline | 如果影响多模块编排，至少 B+J；必要时加 G/H。 |
| `src/report/export_annotated_workbook.py` | L1/L4 report 标注测试 | 产物生成前需确认；重点看 Comments 去重、QC_Locator、隐藏 sheet。 |
| `src/report/export_json.py`、`summary.py` | L1 report 测试；必要时 L3 | 看 JSON 字段稳定，不随意改变下游 UI 字段。 |
| `src/report/ui_app.py` | 固定 JSON / report dict 字段检查 | UI 只展示，不重新判断规则；不要为 UI 修复改 rules。 |
| `src/llm/` | mock LLM 测试 | 默认不真实调用 LLM API；真实调用需单独确认额度影响。 |
| 文档或协作规则 | 人工检查 diff | 不跑代码测试，除非文档变更伴随脚本或测试文件。 |

## 四张经典案例的用途

案例摘要见 `artifacts/case_workbook_structured_summary.md` 和 `artifacts/case_workbook_structured_summary.json`。

| 案例 | 主要用途 | 重点风险 |
| --- | --- | --- |
| B | 标准 SWP 小型完整底稿；适合快速整链路回归 | FA list 与 K.01 多项不一致；处置测试不适合确定性规则。 |
| G | 新增差异、无处置测试、K.03 明细较多 | K.03 明细可能进入 rollforward 候选；新增勾稽差异大。 |
| H | 非 SWP 命名、新增/处置豁免、在建工程转入 | 当前 FA list 选择成 `处置清单`，是读取层风险样本。 |
| J | 较大完整底稿，新增/处置/选样/K.03 齐全 | 记录量大，适合发现 report 重复、UI 卡顿、候选排序问题。 |

使用案例时只比较轻量字段，避免测试变重：

- `selected_sheets`
- `key_counts`
- `reconciliation_baseline`
- `recognized_sheets_by_kind` 中关键模块是否存在
- `module_notes` 中测试 sheet、样本数、豁免 note 是否稳定

暂不默认比较完整 JSON、完整 HTML、完整标注副本、逐行 finding 明细或 LLM 原始输出。

## 分层判断顺序

遇到质检结果异常时，先按下面顺序定位，不要直接改规则：

1. **ingest 是否读对**：sheet 是否选对、表头是否定位、字段是否映射、记录数是否异常。
2. **rules 是否判对**：输入数据正确后，再看规则条件、severity、rule_id、message。
3. **pipeline 是否重复编排**：同一规则是否被调用两次，LLM finding 是否重复 extend。
4. **report 是否重复汇总**：JSON、HTML、Comments、QC_Locator 是否重复展示。
5. **UI 是否误展示**：UI 是否把 execution status 当成审计结论，或自行重新判断。
6. **LLM 是否漂移**：LLM 是否新增真实调用，是否覆盖确定性规则，是否产生不可复现结果。

典型判断：

- 数据为空、sheet 错、字段缺失：优先查 ingest。
- finding 数异常增加：先查 rules 输出，再查 pipeline 是否重复 extend。
- JSON 正常但界面异常：优先查 report/UI。
- execution_ledger 缺规则：查 runner 是否用 recorder 记录。
- LLM 输出不稳定：优先 mock 或关闭 LLM，确认 deterministic rules 是否稳定。

## 通过标准

测试通过不只看命令退出码，还要看与本次修改相关的业务结果是否稳定。

### ingest 通过标准

- 关键 sheet 仍被选中到正确模块；
- 关键字段映射未异常减少；
- 记录数没有无理由大幅变化；
- H 这类已知读取风险样本的问题不能被规则层掩盖。

### rules 通过标准

- 目标 rule_id 仍稳定；
- severity 只按确认口径变化；
- PASS/WARN/FAIL/NEED_REVIEW 枚举不新增；
- registry 元数据可附加；
- 修改 `src/rules/` 时同步考虑 `tests/rules/`。

### execution_ledger 通过标准

- 有 finding 的 rule_id 必须在 ledger 中标记为 `EXECUTED`；
- 数据不足使用 `DATA_INSUFFICIENT`；
- 不适用使用 `NOT_APPLICABLE`；
- ledger 只记录执行事实，不等同审计结论。

### report / 标注通过标准

- findings 不重复展示；
- Comments 表和 QC_Locator 结构稳定；
- 标注副本默认只在确认后生成；
- report 层不改变 rules 的判断口径。
- Comments 列宽、行高、换行、筛选和冻结窗格可用；
- Tab/Cell Ref.、内部跳转、业务表批注和高亮锚点正确；
- 原公式、外链、合并单元格、隐藏行列、原有批注和打印设置未被破坏；
- UI 下载产物与本地生成产物一致，文件可正常打开；
- `QC_执行追溯`中的版本、构建、测试批次和回归轮次可追溯。

### UI 通过标准

- UI 只展示后端结构化结果；
- 能区分“未识别、数据不足、不适用、已执行无 finding、已执行有 finding”；
- 不在 UI 层重新计算规则结论；
- execution_ledger 展示为执行状态，不展示为审计结论。

### LLM 通过标准

- 默认 mock，不真实调用 API；
- 不把确定性 FAIL 改成 PASS；
- 不新增高频逐行调用；
- 若真实调用 LLM，需说明调用范围和额度影响，并等待确认。

## 默认不做

除非用户明确确认，不默认做以下动作：

- 跑完整测试；
- 跑四张完整底稿的全量报告；
- 生成 JSON/HTML/annotated workbook 产物；
- 调用真实 LLM API；
- 把完整报告或完整底稿内容贴进对话；
- 修改 `.env`、真实资料、案例库原始底稿；
- 将报告、标注副本、临时产物加入 git。

## 推荐工作流

1. **只读诊断**：判断问题属于 ingest、rules、LLM、report、UI 哪一层。
2. **列测试建议**：按修改范围选择 L1–L5，不一次性上完整测试。
3. **确认修改范围**：写清楚改什么、不改什么、怎么验收。
4. **执行锁定**：只改确认清单内文件；测试也只做确认范围内的测试。
5. **小范围验证**：优先 L1；必要时升级到 L2/L3。
6. **结果回报**：说明实际修改、测试或建议测试、剩余风险。
7. **是否沉淀**：如需更新 handoff、规则文档、snapshot，单独确认后再写。

## 后续自动化建议

第一阶段先把四张底稿摘要作为人工选择测试的依据。后续可在确认后逐步增加：

- `scripts/run_case_snapshot.py`：只输出 selected_sheets、key_counts、reconciliation_baseline 的差异；
- `tests/regression/test_case_snapshot.py`：使用脱敏摘要做轻量断言；
- 固定 JSON 样例给 UI 做字段展示测试；
- LLM mock 响应样例，避免真实额度消耗。

自动化时仍遵守写入确认规则：新增脚本、测试、snapshot 文件都属于写入动作。

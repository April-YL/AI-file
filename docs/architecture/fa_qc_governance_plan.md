# 固定资产质检 Agent 治理方案

## 目标

本方案用于约束固定资产质检 Agent 的规则来源、资料识别、执行记录、执行证据和展示边界，核心目标是避免系统运行成为黑箱。

统一编排、LLM Router 和准确性修复的当前决策以 [ADR-0003](../decisions/ADR-0003-unified-orchestrator-and-llm-governance.md) 为准。本方案负责把该决策落实为规则准入和运行追溯要求。

当前治理重点不是让 Agent 做更多判断，而是保证每次运行后都能稳定回答：

- 系统识别到了哪些资料，在哪里，依据是什么。
- 识别结果是否足以支持某一条具体规则执行；若不足，阻断字段和降级原因是什么。
- 哪些规则属于可执行规则清单，哪些规则本次实际进入执行，哪些规则未执行或不适用。
- 本次是否调用 LLM、用于哪种能力、调用失败后如何降级。
- 每条已执行规则看了哪里、读了什么值、按什么逻辑检查、输出了什么结果。
- UI 和 JSON 报告展示的是运行事实和执行证据，而不是展示层自行推断。

## 核心分层

### 1. 参考清单：review_rules.md / skill rules

`review_rules.md`、skill rules、历史 checklist 映射和人工整理规则，只作为 reference / coverage backlog。

它们的作用是提示后续还需要补哪些规则、哪些检查点尚未自动化、哪些规则口径需要迁移或确认。

它们不是运行真源，不得被 runner、execution_ledger、UI 或 JSON 报告直接当作已执行规则。

未迁移到 `registry.py`、runner、execution_ledger 和 observation 的参考规则，不得在 UI 或 JSON 报告中展示为“已检查”“已执行”或“已通过”。这类规则只能展示为参考清单、覆盖缺口或待迁移 backlog。

后续如果确认某条 skill rule 需要进入自动质检链路，必须完成迁移：

1. 在 `src/rules/registry.py` 中登记为可追踪规则。
2. 在对应 runner 中接入实际执行逻辑。
3. 确保 execution_ledger 能记录执行事实。
4. 为规则补充 observation，记录执行证据。
5. 增加或更新对应测试。

旧结构本阶段不删除，只冻结并标注为非运行真源。

### 2. 资料识别事实层：ingest_result

`ingest_result` 记录系统从输入底稿中识别到了什么资料，以及这些资料位于哪里。

如果当前代码尚未形成统一的 `ingest_result` 对象，本阶段先由现有 `workbook_context`、各 ingest 输出对象、以及 runner 实际定位结果承载资料识别事实。后续再逐步统一结构，不为了治理文档立即重构 ingest。

它至少应覆盖：

- sheet：识别到的工作表。
- section：识别到的资料区块或程序区块。
- table：识别到的表格或汇总区域。
- header：识别到的表头、关键列、期间列、金额列。
- data range：实际用于后续规则的数据范围、行列位置或单元格位置。

`ingest_result` 还应记录识别依据：

- 命中的 sheet 名或 sheet 名模式。
- 命中的标题、关键词、程序编号或区块名称。
- 命中的表头文本和关键列。
- 命中的行号、列号、单元格或数据区域。
- 是否使用了 fallback 识别路径。

关键或歧义字段不得只保留一个映射结果，还应保留候选、选择结果、证据、反证、采纳或拒绝理由、位置和识别来源。可用的独立系统证据至少包括：

- `HEADER_SEMANTIC`：表头和业务语义。
- `VALUE_TYPE`：编号、日期、金额、百分比等数据类型或格式。
- `VALUE_DISTRIBUTION`：非空率、重复率、取值范围和样本值合理性。
- `STRUCTURAL_CONTEXT`：相邻列、表格区块、工作表用途和跨字段关系。

关键或歧义字段原则上至少满足两类独立系统证据。LLM 可以帮助理解语义和缩小候选范围，但 LLM 输出本身不单独构成字段采纳证据。

`ingest_result` 的识别状态应使用稳定枚举，例如：

- `FOUND`：明确识别到资料。
- `MISSING`：未识别到必要资料。
- `AMBIGUOUS`：存在多个可能位置，无法稳定确认。
- `FALLBACK_USED`：主识别路径失败，使用兜底定位结果。

rules 只能基于 `ingest_result` 或 runner 实际读取结果执行，不得绕过资料识别事实自行假设资料存在。

observation 中的 `checked_data` 必须能追溯到 `ingest_result` 或 runner 的实际定位结果。若资料不足，应记录 `missing_data`，不得伪造 location、values_read 或识别依据。

### 2.1 规则级 Readiness

Readiness 判断“某条规则是否具备执行条件”，不得以整本底稿统一可用或不可用代替。每条规则至少声明所需资料、字段、最低识别证据、是否允许 LLM 参与，以及资料不足时的降级动作。

Readiness 至少使用：

- `READY`：所需资料和字段达到最低证据要求，可以进入规则执行。
- `DATA_INSUFFICIENT`：资料缺失、字段歧义或证据不足，规则不得形成确定性 `FAIL`。
- `NOT_APPLICABLE`：当前底稿场景不适用该规则。

聚合 `NEED_REVIEW` 可以用于降低重复展示，但必须保留全部受影响规则、阻断字段、具体原因和数据位置；不得用一条汇总 finding 掩盖未执行范围。

### 3. 规则真源：registry.py

`src/rules/registry.py` 是 Agent 唯一可执行规则真源。

它定义当前系统承认哪些规则、规则编号是什么、对应哪个程序或检查点、实现状态是什么。

`registry.py` 是可执行规则清单，不等于本次运行的实际执行清单。本次哪些规则实际进入执行，应由 runner 基于 `ingest_result`、当前底稿场景和资料适用性决定。

runner、execution_ledger、UI 和 JSON 报告不得直接依赖 `review_rules.md` 或 skill rules 判断规则是否已执行。

新增或修改规则时，必须以 `registry.py` 为准，并同步确认：

- 规则类型是纯代码、纯 LLM 语义还是代码 + LLM 联合规则。
- 所需资料、字段、最低证据和 Readiness 降级动作是否明确。
- 是否有实际 rule 函数。
- 是否被 runner 接入。
- 是否有 execution_ledger 记录。
- 是否有 observation 执行证据。
- 是否有测试覆盖。

### 3.1 统一 Orchestrator 与 LLM Router

Orchestrator 负责组织唯一正式执行链的阶段顺序、运行上下文、状态传递和失败降级，不重新实现 ingest、rules 或 report 的业务逻辑。

LLM Router 是所有 LLM 能力的唯一调用入口，统一管理 LLM 总开关、`identification`、`rule_review`、`hybrid_rule`、`narrative` 分能力开关、按规则启停、模型与提示词版本、结构校验、超时、重试和失败策略。UI、CLI 和配置文件不得形成彼此独立的 LLM 控制链。

识别兜底失败时不得猜测字段；纯 LLM 语义规则失败时降级为 `NEED_REVIEW`；联合规则失败时保留确定性事实，并将未完成的语义判断降级为 `NEED_REVIEW`。所有正式规则仍必须在 registry 登记。

### 3.2 循环B已落地的识别与止损边界

循环B在现有正式执行链内完成最小系统性收口，没有建设第二条生产流水线：

- FA list、新增清单和处置清单先经过工作表身份路由；候选表按名称、表头语义、结构和数据形态形成证据，三类 List 不得互相替代。
- 关键字段先由确定性映射生成候选和证据；只有存在歧义且 Router 的 `identification` 能力允许时，LLM 才能在系统候选中辅助选择，不能自由生成字段映射，也不能直接执行规则。
- 字段采纳后仍须通过规则级 Readiness；资料、字段或最低证据不足时记录 `DATA_INSUFFICIENT`，不得形成确定性 `FAIL`，也不得静默记为 `PASS`。
- 识别需要重整时，只允许对受影响的工作表或字段进行一次局部确定性重整；仍不可靠时固定降级，不重复调用或猜测。
- Orchestrator 在规则执行后统一评估批量异常问题簇；该防护用于阻止可疑批量结果直接进入交付，并保留原始 findings、受影响规则和行级追溯，不在报告层篡改上游规则事实。

上述能力的当前状态为循环B候选基线。真实样本复测5张，其中4张 findings 已恢复至合理水平；Run 62仍存在较多资产编号唯一性 findings。当前只读分析认为其可能涉及唯一键业务作用域证据不足，但尚未确认属于真实问题、误报或混合情形，因此不得据此修改唯一性规则或宣称循环B已完成业务准确性最终验收。

### 4. 实际执行层：runner / rules

runner / rules 负责实际执行检查。

确定性规则应由代码读取已识别资料并执行，不使用 LLM 生成判断过程。

除纯代码规则外，系统还允许经过 registry 登记的纯 LLM 语义规则和代码 + LLM 联合规则。纯 LLM 语义规则必须产生结构化结论、依据和引用位置；联合规则必须明确代码事实、LLM 判断和固定合并策略。LLM 不得绕过 Orchestrator 和 registry 直接生成正式 finding，也不得无依据把确定性 `FAIL` 改为 `PASS`。

如果资料不足，规则应输出资料不足或需要复核的结果，并让 execution_ledger 记录未执行原因或执行状态；不得因为资料未识别就默认为通过。

### 5. 运行事实：execution_ledger

`execution_ledger` 记录规则级运行事实，而不是解释系统。

它应回答：

- 规则是否在 registry 中。
- 本次是否被 runner 接入并尝试执行。
- 本次执行状态是什么。
- 如果未执行，原因是什么。
- 本次输出 finding 数是多少。

`execution_ledger` 不应扩展成承载全部解释、完整对账、置信度和展示文案的结构。诊断字段可以在诊断报告中输出，但不进入 ledger 核心结构。

### 6. 执行证据：observation

`observation` 记录规则 HOW，即规则如何执行。

它不是规则说明，也不是 LLM 事后总结，而是规则或 runner 基于实际读取结果生成的结构化执行证据。

当前 K.01 证据级 HOW 样板使用以下结构：

- `checked_data`：检查了什么资料，包含 sheet、section、key columns、识别依据、实际读取值或缺失资料。
- `check_logic`：怎么检查，用审计人员可读语言描述。
- `expected_result`：预期结果或判断标准。
- `actual_result`：实际检查结果。
- `result_summary`：是否触发 finding，触发多少条。

`values_read` 必须是结构化记录，不使用自由文本字符串。建议字段包括：

- `label`
- `value`
- `row`
- `column`
- `cell`
- `unit` 或 `amount_type`

`identified_by` 必须来自实际识别证据，例如：

- 命中的 sheet 名。
- 命中的标题或关键词。
- 命中的行列位置。
- ingest 或 runner 实际识别到的 section。

DATA_INSUFFICIENT 或资料缺失时，`checked_data` 可以为空或部分为空，但必须记录 `missing_data`，不得伪造位置或读取值。

### 7. 展示层：UI / JSON

UI 和 JSON 报告只展示已有结构化字段，不自由总结、不生成解释、不补判断。

未完成 `registry.py` 登记、runner 接入、execution_ledger 记录和 observation 证据补充的规则，不得在 UI 或 JSON 报告中展示为已检查或已执行规则。

UI 展示证据级 HOW 时，应将 JSON 字段映射为中文业务标签，例如：

- `checked_data` 显示为“检查资料”。
- `values_read` 显示为“实际读取值”。
- `check_logic` 显示为“检查逻辑”。
- `expected_result` 显示为“判断标准”。
- `actual_result` 显示为“实际结果”。
- `result_summary` 显示为“执行结果”。

没有证据级 HOW 的规则，UI 应明确显示：

> HOW 未记录：该规则已执行，但尚未补充证据级执行说明。

UI 不得将旧字段、规则名称或 finding 文案拼接成新的执行解释。

## 完整运行链路

固定资产质检 Agent 的完整治理链路为：

```text
input workbook
→ Orchestrator：组织唯一正式执行链
→ ingest_result：识别到了什么资料、候选在哪里、依据是什么
→ LLM Router / identification：仅在允许且需要时提供受控识别兜底
→ Rule Readiness：逐条规则判断 READY / DATA_INSUFFICIENT / NOT_APPLICABLE
→ registry.py：系统承认的可执行规则真源
→ runner / rules：执行纯代码、纯 LLM 语义或代码 + LLM 联合规则
→ execution_ledger：是否执行、finding 数、未执行原因
→ observation：看了哪里、读了什么值、怎么判断、结果是什么
→ UI / JSON：只展示，不推断
```

`review_rules.md` / skill rules 不进入上述运行链路，只作为 reference / backlog。

## 当前阶段

当前阶段是 Pilot 两批测试的准确性修复。第一批覆盖运行 28–40，第二批覆盖运行 41–57；修复应先处理工作表/字段识别过早定案和缺少规则级 Readiness 这一最低层共同根因，再校准具体规则和报告展示。

本阶段将 FA list 纳入，是为修复 Run 43、52、54 等样本中已确认的批量误报和检查覆盖漏失，不代表 FA list 重新成为长期开发主线；K.00–K.03 的既有程序口径、规则优先级和演进方向不变。

此前 K.01 证据级 HOW 样板继续保留。本阶段进一步要求 CPA 能够直接看懂：

- 系统看了哪个 sheet。
- 看了哪个 section 或表格区域。
- 命中了哪些标题、关键词、行列位置。
- 实际读到了哪些值。
- 判断标准是什么。
- 实际结果是什么。
- 为什么触发或未触发 finding。

K.01 只是勾稽类 HOW 样板，不强行泛化到全部模块。

## 新增/修改规则准入 checklist

每新增或修改一条 rule，必须先完成以下准入检查。未通过 checklist 的规则，不得作为已实现自动规则进入 runner，也不得在 UI 或 JSON 报告中展示为已检查或已执行。

1. 是否已登记 `src/rules/registry.py`。
2. 是否明确 `data_sources` 和 `check_method`。
3. `ingest_result` 或 runner 是否能定位所需 sheet、section、range。
4. 是否声明所需字段、最低证据和规则级 Readiness 降级动作。
5. 是否声明规则类型及允许使用的 LLM 能力。
6. runner 是否接入 `execute_rule` 或等效的规则执行入口。
7. `execution_ledger` 是否能记录 `EXECUTED`、`DATA_INSUFFICIENT`、`NOT_APPLICABLE`。
8. observation 是否记录证据级 HOW；LLM 参与时是否记录能力、版本、依据和失败状态。
9. UI / JSON 是否只展示结构化结果，不自由总结或补判断。
10. 是否有测试覆盖字段正确、错列、缺列、同名字段、量纲歧义和 LLM 不可用等边界。
11. 是否不会让 `review_rules.md` / skill rules 直接进入运行链路。
12. 是否不会让 LLM 无依据覆盖确定性规则结论。

## 后续阶段

### 1. 模块化推广 HOW

K.01 样板验收后，再按规则类型推广到其他模块：

- FA list：台账完整性、唯一性、字段一致性、金额异常。
- Lead：基准信息、TE/SAD、波动、预期分析、调整事项。
- K.02：新增测试、处置测试、样本与支持性证据。
- K.03：折旧政策、使用寿命、折旧测算。

不同规则类型应设计不同 observation 模板，不能把 K.01 勾稽模板硬套到全部规则。

### 2. LLM 受控接入与验证

LLM 是识别兜底、纯 LLM 语义规则、代码 + LLM 联合规则和报告叙述的统一受控能力，不只提供事后解释。所有调用必须经统一 LLM Router，并由 Orchestrator 在正确阶段发起。

LLM 结果不得覆盖 deterministic rule 的结论，尤其不得将确定性规则的 `FAIL` 改为 `PASS`。

LLM 输出必须可追溯到输入文本、底稿摘录或识别区块。

验证至少评估：

- 是否稳定。
- 是否可复现。
- 是否存在明显漂移。
- 是否存在明显误报或漏报。
- 总开关、分能力开关和按规则开关是否真实生效。
- LLM 不可用时是否按能力安全降级且不影响无关确定性规则。

LLM 可以执行已注册的语义规则或参与联合规则；金额勾稽、唯一性、必填等确定性部分仍由代码基于已验证字段执行。

### 3. skill gap 逐步迁移

对 review_rules.md / skill rules 中尚未进入运行链路的检查点，后续按缺口逐条迁移。

每迁移一条，必须完成：

- registry 登记。
- ingest_result 或 runner 定位依据。
- rule 执行逻辑。
- execution_ledger 记录。
- observation 执行证据。
- UI / JSON 展示验证。
- 测试覆盖。

未完成上述迁移的规则，不得在 UI 或报告中展示为已执行自动规则。

## 本阶段禁止事项

本阶段治理沉淀不做以下事项：

- 不新增大量规则。
- 不删除旧结构。
- 不改变 execution_ledger 顶层结构。
- 不让 UI 自由总结 HOW。
- 不让 LLM 绕过统一 Router、registry 或 Orchestrator 直接形成正式 finding。
- 不按公司、文件名、运行编号、固定行列或单元格地址增加样本特例。
- 不用 finding 数量上限、统一放宽阈值或缺失即通过掩盖上游识别问题。
- 不让 review_rules.md / skill rules 进入运行链路。

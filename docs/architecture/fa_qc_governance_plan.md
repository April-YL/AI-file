# 固定资产质检 Agent 治理方案

## 目标

本方案用于约束固定资产质检 Agent 的规则来源、资料识别、执行记录、执行证据和展示边界，核心目标是避免系统运行成为黑箱。

当前治理重点不是让 Agent 做更多判断，而是保证每次运行后都能稳定回答：

- 系统识别到了哪些资料，在哪里，依据是什么。
- 哪些规则属于可执行规则清单，哪些规则本次实际进入执行，哪些规则未执行或不适用。
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

`ingest_result` 的识别状态应使用稳定枚举，例如：

- `FOUND`：明确识别到资料。
- `MISSING`：未识别到必要资料。
- `AMBIGUOUS`：存在多个可能位置，无法稳定确认。
- `FALLBACK_USED`：主识别路径失败，使用兜底定位结果。

rules 只能基于 `ingest_result` 或 runner 实际读取结果执行，不得绕过资料识别事实自行假设资料存在。

observation 中的 `checked_data` 必须能追溯到 `ingest_result` 或 runner 的实际定位结果。若资料不足，应记录 `missing_data`，不得伪造 location、values_read 或识别依据。

### 3. 规则真源：registry.py

`src/rules/registry.py` 是 Agent 唯一可执行规则真源。

它定义当前系统承认哪些规则、规则编号是什么、对应哪个程序或检查点、实现状态是什么。

`registry.py` 是可执行规则清单，不等于本次运行的实际执行清单。本次哪些规则实际进入执行，应由 runner 基于 `ingest_result`、当前底稿场景和资料适用性决定。

runner、execution_ledger、UI 和 JSON 报告不得直接依赖 `review_rules.md` 或 skill rules 判断规则是否已执行。

新增或修改规则时，必须以 `registry.py` 为准，并同步确认：

- 是否有实际 rule 函数。
- 是否被 runner 接入。
- 是否有 execution_ledger 记录。
- 是否有 observation 执行证据。
- 是否有测试覆盖。

### 4. 实际执行层：runner / rules

runner / rules 负责实际执行检查。

确定性规则应由代码读取已识别资料并执行，不使用 LLM 生成判断过程。

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
→ ingest_result：识别到了什么资料、在哪里、依据是什么
→ registry.py：系统承认的可执行规则真源
→ runner / rules：基于 ingest_result 和当前底稿场景决定本次实际进入哪些规则并执行
→ execution_ledger：是否执行、finding 数、未执行原因
→ observation：看了哪里、读了什么值、怎么判断、结果是什么
→ UI / JSON：只展示，不推断
```

`review_rules.md` / skill rules 不进入上述运行链路，只作为 reference / backlog。

## 当前阶段

当前阶段只做 K.01 两条规则的证据级 HOW 样板：

- Lead / TB / K.01 后推表勾稽类规则。
- FA list / K.01 后推表勾稽类规则。

本阶段目标是验证 CPA 能否直接看懂：

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
4. runner 是否接入 `execute_rule` 或等效的规则执行入口。
5. `execution_ledger` 是否能记录 `EXECUTED`、`DATA_INSUFFICIENT`、`NOT_APPLICABLE`。
6. observation 是否记录证据级 HOW。
7. UI / JSON 是否只展示结构化结果，不自由总结或补判断。
8. 是否有测试覆盖。
9. 是否不会让 `review_rules.md` / skill rules 直接进入运行链路。
10. 是否不会让 LLM 覆盖确定性规则结论。

## 后续阶段

### 1. 模块化推广 HOW

K.01 样板验收后，再按规则类型推广到其他模块：

- FA list：台账完整性、唯一性、字段一致性、金额异常。
- Lead：基准信息、TE/SAD、波动、预期分析、调整事项。
- K.02：新增测试、处置测试、样本与支持性证据。
- K.03：折旧政策、使用寿命、折旧测算。

不同规则类型应设计不同 observation 模板，不能把 K.01 勾稽模板硬套到全部规则。

### 2. LLM 初步验证

LLM 验证单独进行，不和 HOW 样板开发混在同一轮。

LLM 结果不得覆盖 deterministic rule 的结论，尤其不得将确定性规则的 `FAIL` 改为 `PASS`。

LLM 输出必须可追溯到输入文本、底稿摘录或识别区块。

初步验证只评估：

- 是否稳定。
- 是否可复现。
- 是否存在明显漂移。
- 是否存在明显误报或漏报。

LLM 适合作为语义复核或人工复核提示，不作为金额勾稽、唯一性、必填等确定性规则的替代。

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
- 不让 LLM 生成 deterministic rule 的 HOW。
- 不让 review_rules.md / skill rules 进入运行链路。

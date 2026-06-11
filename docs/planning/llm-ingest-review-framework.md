# LLM Ingest Review 项目级兜底框架

> 状态：项目级设计稿，待后续按 K.01、K.02.1、K.02.2、K.03 等程序拆分 profile。  
> 目的：在确定性 `ingest` 之外，增加 LLM 对读取结果的语义复核和漏读发现能力。  
> 边界：LLM 不替代 coding 取数、不计算金额、不改变规则结论；只提示读取风险、候选位置和人工复核重点。

---

## 一、背景与结论

固定资产底稿在实务中变化很大：sheet 命名、模板版本、合并单元格、外链、隐藏列、系统导出字段、手工 Notes 和项目组自定义结构都可能不同。现有 5 层 coding 识别结构能覆盖标准模板和已回归案例，但不能穷尽所有例外。

同时，底稿读对是后续质检规则成立的前提：

```text
如果 ingest 读错 sheet、字段、区块、金额或 Notes，
后续 rules 再精细也可能误报或漏报。
```

因此，建议在现有 coding 识别体系后增加第 6 层：

> **LLM ingest review**：作为读取结果复核员和漏读发现助手，对低置信度、结构冲突、疑似错映射、疑似漏读等场景进行语义兜底。

核心分工：

| 角色 | 职责 |
| --- | --- |
| coding / ingest | 读取事实：sheet、字段、金额、行号、单元格、锚点、置信度 |
| coding / rules | 判断确定性结论：金额勾稽、缺字段、超 SAD、样本匹配等 |
| LLM ingest review | 发现读取风险：漏读、错读、错分、错映射、Notes 归属可疑 |
| CPA / 质检人员 | 对低置信度、重大判断和 LLM 提示做最终复核 |

一句话原则：

> coding 负责事实和计算，LLM 负责结构异常和语义风险提示，CPA 负责最终判断。

---

## 二、六层识别架构

在现有 5 层识别结构上增加第 6 层：

```text
1. Sheet 名称 + 内容识别
   - 标准名称、名称变体、表头内容联合判断

2. 字段映射与防误配
   - FIELD_SYNONYMS + sheet 类型限制
   - 避免把业务单号误映射为资产编号

3. 锚点分块与区块边界
   - K.01 六区块、Lead 分块、K.02.1 模块等

4. 金额 / 明细行 / Notes 结构化读取
   - 金额口径、正负号、合计行、小计行、Notes 区域

5. 置信度与 rules 兜底
   - 低置信度、冲突、缺失区块进入 NEED_REVIEW 或摘录展示

6. LLM ingest review
   6A. 已读结果复核
   6B. 漏读发现
```

第 6 层不直接替代前 5 层，而是对前 5 层的结果做复核和补漏。

---

## 三、LLM ingest review 的两类任务

### 3.1 6A 已读结果复核

适用场景：

- coding 已识别到 sheet、字段、模块或金额，但置信度偏低。
- 存在锚点重复、区块顺序异常、表头冲突。
- 读取结果与候选预览不自洽。
- Notes 可能归属错专题，例如 K.01 表4 Notes 被用于 TB check。

示例：

```text
coding 识别：
- K.01 后推表存在
- 表1、TB 区、表4 存在
- 表3 缺失
- recognition_confidence = 0.58
- conflicts = ["duplicate_anchor:表3"]

LLM 复核：
- 候选预览中第45行出现“表2 check with 表1”
- 可能漏识别表3
- 第82行为表4折旧费用核对，不应与 TB 差异混用
```

输出方向：

- `suspicious`：建议二次 deterministic ingest 或人工核对。
- `unclear`：信息不足，建议人工核对。
- `likely_ok`：未见明显读取风险，但不改变规则结论。

### 3.2 6B 漏读发现

适用场景：

- coding 未识别到核心 sheet，但 workbook 中存在疑似候选页。
- coding 未识别到某个模块，但目标 sheet 预览中疑似出现该模块锚点。
- coding 未映射某个字段，但表头和样例行显示疑似存在。
- coding 未读到 Notes，但差异行周边文本疑似存在说明。

示例：

```text
coding 识别：
- rollforward = None

候选 sheet：
- "K01 SL-GL"
- 前几行出现“固定资产类别”“年初余额”“年末余额”“审定数”“TB-原值”“差异”

LLM 判断：
- 疑似存在 K.01 后推表
- 建议对该候选 sheet 执行二次 deterministic ingest
```

输出方向：

- `suspected_present` 可映射为项目级输出中的 `suspicious`。
- `not_found`：候选中未见目标对象明显证据。
- `unclear`：候选证据不足。

---

## 四、LLM 与 coding 的交互闭环

LLM ingest review 不直接把候选内容变成规则输入。推荐闭环如下：

```text
coding ingest
    ↓
输出结构化摘录、置信度、冲突、候选预览
    ↓
触发 LLM ingest review（仅异常或低置信度场景）
    ↓
LLM 输出候选对象、风险原因、建议动作
    ↓
coding 处理 LLM 结果：
    - 不改变已读金额
    - 不直接改 PASS/FAIL
    - 可触发二次 deterministic ingest
    ↓
二次 ingest 置信度达标
    → 进入正常 rules

二次 ingest 仍不达标
    → 输出 NEED_REVIEW + 候选位置 + 人工复核重点
```

建议采纳规则：

| LLM 输出 | coding 动作 |
| --- | --- |
| `likely_ok` | 仅记录；不提高原置信度，不改变规则结论 |
| `suspicious` 且证据明确 | 可对 candidate sheet / rows 执行二次 deterministic ingest |
| `suspicious` 但证据弱 | 输出 `NEED_REVIEW`，不二次强读 |
| `unclear` | 输出 `NEED_REVIEW` 或仅展示人工核对提示 |
| `not_found` | 保持缺失结论，可记录已复核候选 |

### 4.1 通用判断框架

项目级框架需要先定义一套通用判断方法，并在识别层覆盖所有核心程序 sheet；后续 K.01、Lead、K.02、K.03 的程序级 profile 只是在此基础上补充各自的锚点、常见变体和误读风险。

#### 4.1.1 判断对象

LLM ingest review 不直接判断“底稿是否正确”，而是判断 coding 读取结果中某个对象是否存在读取风险。

| 对象 | 含义 | 示例 |
| --- | --- | --- |
| `sheet` | 工作表是否漏读或错分 | K.01 后推表未识别，但候选页像后推 |
| `module` | sheet 内模块是否漏读或边界错误 | K.01 表3、表4、Notes 区缺失或错位 |
| `field` | 字段是否未映射或疑似误映射 | `单据编号` 被误当固定资产编号 |
| `amount_anchor` | 金额锚点是否取错区域 | 把表4折旧差异当 TB 差异 |
| `notes` | Notes 是否漏读或归属错专题 | 表4 Notes 被用于解释 TB 差异 |

#### 4.1.2 风险类型

| 风险类型 | 判断重点 | 处理方向 |
| --- | --- | --- |
| `missing` | coding 没读到，但候选内容疑似存在 | 漏读发现；建议二次 ingest 或人工核对 |
| `misclassified` | sheet 或模块被分到错误类型 | 输出读取风险提示；必要时二次分类 |
| `mis_mapped` | 字段含义与映射结果不一致 | 建议人工确认字段或当次禁用该映射 |
| `wrong_boundary` | 区块边界可能切错 | 建议核对锚点上下文或重跑区块识别 |
| `wrong_topic` | Notes / 差异归属错专题 | 输出 `NEED_REVIEW`，避免规则用错说明 |
| `low_confidence` | coding 已提示低置信度或冲突 | 提示人工核对，不直接改高置信度 |

#### 4.1.3 证据强弱分层

LLM 只能根据输入证据判断，不得凭经验泛泛报警。项目级采纳时可按证据强弱处理：

| 证据等级 | 判断口径 | 可否判 `suspicious` |
| --- | --- | --- |
| 强证据 | 名称、多个锚点、行号预览相互支持；与缺失对象高度一致 | 可以 |
| 中证据 | 名称或内容一方较强，另一方不足；或只有相邻模块支持 | 可以，但通常只输出 `NEED_REVIEW` |
| 弱证据 | 只有一个模糊词、无行号、无明确锚点 | 不建议；最多 `unclear` |
| 无证据 | 输入中没有候选内容 | `not_found` 或 `unclear` |

强证据示例：

```text
coding_result：K.01 表3缺失。
candidate_previews：第45行出现“表2 check with 表1”“差异”“Notes”。
判断：可以判 suspicious，并建议对第45行附近二次读取。
```

弱证据示例：

```text
sheet 名称含“资产”，但预览中没有固定资产类别、年初余额、年末余额、审定数等锚点。
判断：不得直接判 K.01 suspicious，最多 unclear。
```

#### 4.1.4 结论映射

| LLM 判断 | 项目级含义 | coding 采纳方式 |
| --- | --- | --- |
| `likely_ok` | 未见明显读取风险 | 不生成 issue，不提高原 coding 置信度 |
| `suspicious` + 强证据 | 存在明确读取风险 | 可触发二次 deterministic ingest |
| `suspicious` + 中证据 | 可能读取风险 | 输出 `NEED_REVIEW`，通常不自动二次强读 |
| `unclear` | 输入证据不足 | 输出人工复核提示或仅记录 |
| `not_found` | 候选中未见目标对象 | 保持原缺失结论 |

#### 4.1.5 通用采纳门槛

LLM 输出必须满足以下条件，coding 才能采纳为读取风险提示：

- `candidate_sheet` 必须在输入候选列表内。
- `candidate_rows` 必须来自 `preview_lines` 或 `anchor_hits`。
- `evidence_anchors` 必须来自输入文本，不得新增。
- `rationale` 必须引用具体证据，例如 sheet、行号、锚点或冲突。
- 不得包含输入中没有的金额、单元格坐标、凭证号、人员或外部系统信息。
- 不得要求改变 `FAIL/WARN/NEED_REVIEW/PASS`。
- 不得把 `likely_ok` 作为提高 coding 置信度或自动 PASS 的依据。

#### 4.1.6 未来 Python 通用模块职责

后续若实现项目级 Python，建议新增：

```text
src/llm/ingest_review.py
```

该模块只负责项目级通用能力：

- 统一 system prompt 与 user payload 模板。
- 校验 LLM JSON 输出枚举值。
- 校验候选 sheet、行号、锚点是否来自输入。
- 根据证据强弱决定是否采纳为 `NEED_REVIEW`。
- 生成缓存 key：`hash(prompt_version + review_type + normalized_payload)`。
- 屏蔽 LLM 输出中的金额结论、severity 覆盖建议或无证据断言。
- 把通用结果转成 report 可展示的“读取结果复核提示”。

该模块不应内置 K.01 表3、K.02 处置净值、K.03 折旧参数等程序口径；这些应由后续程序级 profile 提供。

#### 4.1.7 项目级框架与程序级 profile 分工

| 层级 | 解决什么问题 | 不解决什么问题 |
| --- | --- | --- |
| 项目级框架 | LLM 如何触发、看什么输入、输出什么 JSON、如何采纳、如何省 token | 不定义每个程序的全部锚点和业务口径 |
| 程序级 profile | 某个程序“什么才像读对”、哪些锚点强、哪些误读高风险 | 不重复定义通用 JSON、缓存、采纳规则 |

建议实现顺序：

```text
项目级判断框架
    → 项目级 Python 骨架
    → 所有核心程序 sheet 的 missing discovery 接入
    → K.01 profile 作为首个程序级增强
    → 再逐步增强 K.02.2 / K.02.1 / Lead / K.03 profile
```

---

## 五、触发条件

为节省 token 并降低噪音，只在异常或低置信度场景调用 LLM。

### 5.1 建议触发 LLM 的情形

| 场景 | 示例 |
| --- | --- |
| 核心 sheet 缺失 | 未识别 K.01、Lead、新增清单、处置清单 |
| 识别置信度低 | K.01 `recognition_confidence < 0.65` |
| 名称和内容冲突 | sheet 名像新增清单，内容像 K.01 后推 |
| 区块锚点冲突 | duplicate anchor、区块顺序异常、表头落在区块外 |
| 模块缺失但候选文本疑似存在 | 未识别表3，但预览中有 `表2 check with 表1` |
| 高风险字段未映射或疑似误映射 | `单据编号`、`业务日期`、`变动方式` |
| Notes 归属可疑 | TB Notes、表3 Notes、表4 Notes 可能混用 |
| 规则输出依赖低置信读取 | 差异超 SAD 但 Notes 来源不可靠 |

### 5.2 不建议触发 LLM 的情形

| 场景 | 原因 |
| --- | --- |
| 置信度高、结构完整、无冲突 | 浪费 token |
| 确定性规则已能明确判断 | LLM 不应重复判断金额或字段缺失 |
| 仅为了写报告摘要 | 属层 4 `llm_enrichment`，优先级低 |
| 需要外部系统数据 | LLM 无法核对 Canvas、TB 外部系统或原始凭证 |

---

## 六、候选生成规则

LLM 不应直接看整本工作簿。coding 先生成 Top 3-5 候选，再交给 LLM。

### 6.1 Sheet 候选

候选来源：

- sheet 名称相似度。
- 表头或前若干行命中特征词。
- 与缺失对象相关的锚点。
- 多期间路由后的当期候选。

示例：

| 缺失对象 | coding 粗筛候选逻辑 |
| --- | --- |
| K.01 后推 | sheet 名含 `K.01`、`GL`、`后推`、`agree`、`rollforward`；预览含 `固定资产类别`、`年初余额`、`年末余额`、`审定数`、`TB`、`差异` |
| 新增清单 | sheet 名含 `新增`、`增加`、`addition`；表头含资产编号、入账日期、原值、新增方式 |
| 处置清单 | sheet 名含 `处置`、`减少`、`报废`、`disposal`；表头含原值、累计折旧、净值、业务日期、减少方式 |
| K.02.1a 选样输出 | sheet 名含 `选样`、`抽样`、`输出`；预览含样本池、样本量、已选取样本 |

### 6.2 模块候选

当 sheet 已识别但模块缺失时，coding 只提供目标 sheet 内的候选行：

- 目标模块锚点附近行。
- 未识别模块的弱命中行。
- 已识别相邻模块前后若干行。
- 差异行和 Notes 附近行。

### 6.3 字段候选

当字段未映射或高风险字段疑似误映射时，coding 提供：

- 表头行。
- 前 3-5 条脱敏样例行。
- 当前映射结果。
- 未映射表头。
- sheet 类型。

---

## 七、Token 预算策略

原则：少给无关信息，保留关键证据。

| 档位 | 触发条件 | 输入内容 | 目标 |
| --- | --- | --- | --- |
| 低成本 | 核心 sheet 缺失 | sheet 列表 + Top 3-5 候选页前 10 行 | 判断是否疑似漏读 sheet |
| 中成本 | 模块缺失或字段可疑 | 目标 sheet 锚点附近 ±5 行 / 表头 + 样例行 | 判断是否漏读模块或错映射 |
| 高成本 | 多处冲突或规则依赖低置信读取 | 结构化结果 + 冲突 + 候选区块预览 + prior findings | 判断读取风险和人工复核重点 |

不传：

- 整本 Excel。
- 全量单元格。
- 全量 FA list 明细。
- 全部历史年度 sheet。
- 大量重复 findings。
- `.env`、API key 或任何真实密钥。

---

## 八、项目级 System Prompt

```text
你是固定资产审计底稿的资深质检 CPA，负责复核 Agent 的 ingest 读取结果是否可靠。

你的任务不是重新读取整本 Excel，也不是计算金额，而是基于 coding 已经提供的结构化读取结果、置信度、冲突信息、候选 sheet 预览和局部文本，判断是否存在以下风险：

1. 漏读：Agent 未识别到某个核心 sheet、模块、字段、Notes，但候选内容中疑似存在。
2. 错读：Agent 已读取某个 sheet、模块或金额，但读取结果与底稿预览、锚点顺序或业务结构不自洽。
3. 错分：sheet 类型、区块类型或 Notes 归属可能错误，例如把表4折旧差异当作 TB 差异。
4. 错映射：字段映射可能错误，例如把“单据编号”误当固定资产编号。
5. 低置信度：coding 已提示置信度低、锚点重复、表头冲突、区块边界异常，需要人工复核。

你必须遵守：

1. 不得编造输入中没有的 sheet、字段、金额、行号、单元格或证据。
2. 不得直接给出金额勾稽结论，不判断差异是否超过 SAD，不判断规则 PASS/FAIL。
3. 不得将低置信度读取直接改成高置信度。
4. 不得推翻 coding 规则已形成的确定性结论；只能提示“读取层可能存在风险”。
5. 如果证据不足，返回 unclear，并说明需要人工打开底稿核对。
6. 如果发现疑似漏读或错读，只提出候选 sheet、候选模块、风险原因和建议动作。
7. 最终输出必须是 JSON，不要输出 markdown。

判断口径：

- likely_ok：读取结果与候选预览、锚点、字段含义基本自洽，未见明显漏读或错读风险。
- suspicious：存在较明确的漏读、错读、错分、错映射风险，建议二次 deterministic ingest 或人工复核。
- unclear：输入信息不足，无法判断是否读对，应人工复核。
- not_found：针对漏读发现任务，候选内容中未见目标对象的明显证据。

注意：
coding 是事实取数层；你是读取结果复核层。你只能输出复核建议，不生成最终审计结论。
```

---

## 九、项目级 User Prompt 模板

```text
请复核以下固定资产底稿 ingest 读取结果。

复核目标：
{review_target}

复核类型：
{review_type}
可选值：
- read_result_review：已读结果复核
- missing_object_discovery：漏读发现
- field_mapping_review：字段映射复核
- notes_location_review：Notes 归属复核
- section_boundary_review：区块边界复核

请返回 JSON：

{
  "assessment": "likely_ok|suspicious|unclear|not_found",
  "risk_level": "high|medium|low",
  "risk_area": "sheet_classification|section_boundary|field_mapping|amount_anchor|notes_location|missing_sheet|missing_module|other",
  "suspected_object": "",
  "candidate_sheet": "",
  "candidate_rows": [],
  "evidence_anchors": [],
  "rationale": "",
  "suggested_action": "",
  "should_retry_deterministic_ingest": true,
  "manual_review_focus": ""
}

输入数据如下：

{
  "coding_result": {
    "classified_sheet": "",
    "recognized_sections": [],
    "missing_sections": [],
    "mapped_fields": [],
    "unmapped_headers": [],
    "key_amounts": [],
    "recognition_confidence": 0.0,
    "conflicts": [],
    "notes": []
  },
  "expected_object": {
    "procedure": "",
    "object_type": "sheet|module|field|notes|amount_anchor",
    "object_name": "",
    "why_expected": ""
  },
  "candidate_previews": [
    {
      "sheet_name": "",
      "name_score": 0.0,
      "content_score": 0.0,
      "preview_lines": [
        {"row": 1, "text": ""},
        {"row": 2, "text": ""}
      ],
      "anchor_hits": [
        {"row": 1, "anchors": []}
      ]
    }
  ],
  "deterministic_findings": [],
  "question": ""
}
```

---

## 十、输出采纳规则

LLM ingest review 的输出必须经过 coding 侧约束后才能进入报告。

| 输出字段 | 采纳要求 |
| --- | --- |
| `assessment` | 仅接受枚举值；异常值丢弃 |
| `candidate_sheet` | 必须存在于输入候选中 |
| `candidate_rows` | 必须来自输入 preview 或 anchor_hits |
| `evidence_anchors` | 必须来自输入 anchor_hits / preview_lines |
| `should_retry_deterministic_ingest` | 只能触发二次 coding 读取，不能直接生成规则结论 |
| `rationale` | 必须引用输入证据；泛泛而谈不采纳为 high risk |

建议 severity 映射：

| LLM assessment | 报告处理 |
| --- | --- |
| `likely_ok` | 不生成 finding；可写入 debug / metadata |
| `suspicious` | 生成 `NEED_REVIEW` 读取风险提示，或触发二次 ingest |
| `unclear` | 生成 `NEED_REVIEW`，提示人工核对 |
| `not_found` | 不生成额外 finding；保留原缺失判断 |

---

## 十一、不过度报警规则

LLM ingest review 应避免把所有非标准模板都判为可疑。

必须遵守：

1. 没有明确锚点证据，不得判 `suspicious`。
2. 只有 sheet 名相似但内容不像，最多判 `unclear`。
3. 只有一个弱词命中，不建议二次读取。
4. 标准模板以外的版式不等于错误；需要指出具体风险。
5. 低置信度不等于读错，只代表需要人工或二次读取。
6. 已有确定性规则能明确判断时，不重复生成 LLM 读取风险提示。

示例：

```text
不合格输出：
“该底稿结构复杂，建议人工复核。”

合格输出：
“coding_result 显示表3缺失，但 candidate_previews 第45行出现‘表2 check with 表1’和‘差异’，与 K.01 表3锚点一致，建议二次读取第45行附近。”
```

---

## 十二、缓存机制

为节省 token，建议对 LLM ingest review 加缓存：

```text
cache_key = hash(prompt_version + review_type + normalized_payload)
```

缓存内容：

- prompt version
- review type
- source file hash 或 workbook fingerprint
- candidate previews hash
- LLM output
- model name
- timestamp

适用场景：

- UI 反复点击同一底稿。
- 同一底稿多次导出 JSON / HTML / 标注副本。
- 同一候选 preview 未变化。

不适用场景：

- prompt 版本变更。
- candidate preview 变更。
- ingest 逻辑变更导致 coding_result 变化。

---

## 十三、评估集要求

LLM ingest review 必须像 rules 一样做回归，否则容易越来越泛、越来越吵。

建议评估集至少包含：

| 类型 | 用途 |
| --- | --- |
| 漏读 sheet | K.01、Lead、新增清单、处置清单命名变体 |
| 错分 sheet | 新增/处置清单被误分为 rollforward |
| 漏读模块 | K.01 表3、表4、Notes；K.02.1 样本表 |
| 字段误映射 | `单据编号` vs `资产编号`、`业务日期` vs `处置日期` |
| Notes 错专题 | TB Notes、表3 Notes、表4 Notes 混用 |
| 正常不报警 | 标准底稿和已稳定案例不应产生 `suspicious` |
| 低证据场景 | 只能输出 `unclear`，不得编造候选 |

评估指标：

- 漏读发现召回率：应发现的候选是否提示出来。
- 误报率：正常底稿是否被过度提示。
- 证据引用率：输出是否包含 sheet、row、anchor。
- 二次 ingest 成功率：LLM 提示候选后 coding 是否能读成。

---

## 十四、Prompt 版本管理

建议为项目级 prompt 与程序级 profile 分别维护版本。

记录字段：

| 字段 | 说明 |
| --- | --- |
| prompt_version | 如 `ingest_review_v0.1` |
| applicable_scope | project / K.01 / Lead / K.02.1 等 |
| change_reason | 修改原因 |
| affected_cases | 影响案例 |
| expected_behavior | 希望改善什么 |
| regression_result | 回归结果 |
| owner | 维护人 |

每次修改 prompt 后，至少验证：

- 正常底稿不新增噪音。
- 已知漏读案例能提示。
- LLM 不输出金额结论。
- LLM 不改规则 severity。

---

## 十五、Report 展示方式

LLM ingest review 的结果应与普通业务规则 findings 区分展示。

建议新增 report 区块：

```text
读取结果复核提示
```

展示字段：

| 字段 | 说明 |
| --- | --- |
| 风险类型 | 漏读 / 错读 / 错分 / 字段误映射 / Notes 归属 |
| 程序 | K.01、Lead、K.02.1 等 |
| 候选 sheet | LLM 指出的疑似位置 |
| 候选行 | LLM 引用的行号 |
| 锚点证据 | 命中的关键词 |
| 建议动作 | 二次读取或人工核对 |
| 是否已二次读取 | 是 / 否 / 不适用 |

建议说明：

```text
以下为读取层风险提示，不等同于业务规则 FAIL。
请质检人员先确认 Agent 是否读对底稿，再依据规则 findings 判断底稿问题。
```

---

## 十六、后续程序级 profile 设计

项目级框架只定义 LLM 如何工作；每个程序还需要补充专属 profile，定义“什么才像读对”。

建议后续文件：

| 程序 | 建议文档 |
| --- | --- |
| K.01 后推 | `docs/planning/llm-ingest-profile-k01.md` |
| K.00 Lead | `docs/planning/llm-ingest-profile-lead.md` |
| K.02.1 新增 | `docs/planning/llm-ingest-profile-k021-addition.md` |
| K.02.2 处置 | `docs/planning/llm-ingest-profile-k022-disposal.md` |
| K.03 折旧 | `docs/planning/llm-ingest-profile-k03-depreciation.md` |

程序级 profile 应包含：

- 核心 sheet / 模块。
- 关键锚点。
- 常见命名变体。
- 常见误读方式。
- 字段高风险误映射。
- Notes 归属规则。
- 漏读发现示例。
- 正常不报警示例。

---

## 十七、与现有 LLM 路线图关系

现有路线图中，LLM 主战场包括：

- ingest：字段映射 / 表头识别。
- rules：语义类质检点。
- checklist：检查点满足度。

本文建议的 LLM ingest review 是 ingest 层的进一步细化：

| 规划能力 | 本文对应 |
| --- | --- |
| `--llm-map` 表头映射 | 字段映射复核的一部分 |
| LLM 服务 ingest | 读取结果复核 + 漏读发现 |
| rules 语义复核 | 本文不替代；仍由 `summary_psp_review`、`lead_review`、`rollforward_notes_review` 等处理 |
| report 叙述 | 本文不涉及；仍为低优先级 |

建议后续实现时可命名为：

```text
src/llm/ingest_review.py
```

并提供配置开关：

```text
--llm-ingest-review
```

或并入未来 `--llm-map` 的扩展能力，但应保留“漏读发现”和“读取结果复核”的独立输出类型。

---

## 十八、本阶段不做事项

本项目级设计阶段不做：

- 不修改 `src/llm/` 代码。
- 不新增实际 LLM 调用。
- 不改变现有 prompt。
- 不改变规则 severity。
- 不把 LLM 结果作为最终金额事实。
- 不把真实底稿内容或 API key 写入文档。
- 不提交 `.env` 或任何密钥。

---

## 十九、阶段验收标准

项目级设计完成后，应满足：

1. 说明清楚为什么需要第 6 层 LLM ingest review。
2. 明确 LLM 与 coding 的职责边界。
3. 明确 6A 已读结果复核与 6B 漏读发现。
4. 给出项目级 System Prompt 与 User Prompt 模板。
5. 覆盖 9 项设计补充：
   - 候选生成规则
   - 二次读取闭环
   - 证据引用要求
   - 不过度报警规则
   - token 预算策略
   - 缓存机制
   - 评估集
   - prompt 版本管理
   - report 展示方式
6. 便于后续拆成各程序 profile。

---

## 二十、简短汇报口径

可用于对业务或项目管理汇报：

> 由于实务底稿版式无法穷尽，Agent 在确定性 ingest 识别之外，规划增加 LLM ingest review 作为第 6 层兜底。该层分为已读结果复核和漏读发现两类：前者检查低置信度或结构冲突的读取结果是否可疑，后者在核心 sheet、模块、字段或 Notes 未被识别时，从候选预览中发现可能存在的内容。LLM 不直接取数、不算金额、不改变规则结论，只输出候选位置、风险原因和人工复核建议；如证据明确，可触发 coding 二次 deterministic ingest。通过只在异常场景调用、只传候选摘要、要求证据引用和缓存结果，可以在控制 token 成本的同时提高发现读取异常的能力。


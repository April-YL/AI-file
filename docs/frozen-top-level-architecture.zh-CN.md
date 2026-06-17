# AI QC Agent 冻结顶层架构

本文档是 AI QC Agent 的中文顶层架构冻结说明，用于汇报、评审和团队阅读。

本文档与 `docs/frozen-top-level-architecture.md` 表达同一套架构原则。英文版是严格工程契约，本文档是中文解释版。本文档不引入新架构、不改变执行链、不包含重构计划。

## 一、架构定位

本架构已经冻结为目标顶层架构契约。

它回答的是：

- 系统运行时必须按什么顺序执行。
- 哪些模块拥有事实判断权。
- LLM 在系统里是什么角色。
- finding 如何成为唯一影响载体。
- report 为什么只能做展示和交付。

它不回答：

- 具体文件怎么移动。
- 哪些函数怎么重构。
- 哪些规则要新增。
- 哪些 prompt 要优化。

这些属于后续 implementation mapping 或 refactor 阶段。

## 二、系统宪法

```text
系统是单执行链，不是多流系统。
LLM 是基础设施，不是 pipeline 阶段。
Control Plane 是唯一决策中心。
Ingest = deterministic parsing + semantic enrichment。
Rules = truth source，不可被任何模块修改。
Finding Model 是唯一影响载体。
Report 是 Presentation / Delivery Layer，不反向参与判断。
```

## 三、唯一主执行链

系统只有一条 runtime pipeline：

```text
INPUT
  ↓
ORCHESTRATOR
  ↓
INGEST ENGINE
   ├─ deterministic parsing
   ├─ IDENTIFIER (semantic sub-layer)
   └─ ingest confidence
  ↓
STANDARDIZED MODEL DRAFT
  ↓
EARLY VALIDATION LOOP
  ↓
STANDARDIZED MODEL
  ↓
RULE ENGINE
  ↓
DECISION GATE
  ↓
CONTROL PLANE (SINGLETON)
  ↓
FINDING MODEL
  ↓
REPORT (Presentation / Delivery Layer)
```

这条链路是唯一执行链。数据视角、决策视角和 LLM 使用视角只能作为观察角度，不能在代码中实现成三套独立 pipeline。

## 四、LLM Router 是基础设施层

LLM Router 不属于主执行链中的一个业务阶段。

它是横切基础设施，供不同阶段在受控条件下调用：

```text
LLM ROUTER (INFRASTRUCTURE LAYER)

- used by INGEST IDENTIFIER
- used by CONTROL PLANE REASONER
- used by FALLBACK
```

LLM Router 负责：

- token control
- caching
- tracing
- budget management
- model routing
- prompt / version metadata

LLM Router 不负责：

- 业务判断
- rule conclusion
- severity
- finding 权限
- audit decision

一句话：

```text
LLM Router 管模型调用治理，不管审计结论。
```

## 五、模块职责

### 1. Orchestrator

Orchestrator 负责流程执行和运行状态推进。

职责：

- 接收输入。
- 推进唯一执行链。
- 协调各阶段执行。
- 保持运行顺序稳定。

不允许：

- 做业务判断。
- 生成 finding。
- 修改规则结果。
- 执行 LLM 推理。

### 2. Ingest Engine

Ingest Engine 负责理解底稿并生成标准化模型。

职责：

- deterministic parsing：稳定读取 workbook、sheet、field、table、row、section。
- semantic enrichment：通过 Identifier 对复杂底稿结构做语义补强。
- ingest confidence：输出读取置信度和可用性信息。
- 生成 Standardized Model Draft。

不允许：

- 生成最终 finding。
- 判断 PASS / FAIL。
- 替代 Rule Engine 做业务结论。

### 3. Identifier

Identifier 是 Ingest Engine 内部的语义子层，不是独立 pipeline 节点。

职责：

- sheet 识别。
- field 识别。
- section 识别。
- noisy table 解析辅助。
- mapping suggestion。
- missing object detection。

Identifier 可以在受控条件下通过 LLM Router 调用 LLM。

不允许：

- 生成 PASS / FAIL / WARN。
- 直接产出最终 finding。
- 修改规则结果。
- 静默修改事实数据。

### 4. Early Validation Loop

Early Validation Loop 只做 model readiness check。

职责：

- 检查标准化模型草稿是否结构完整。
- 检查关键对象是否存在。
- 检查 ingest confidence 是否足够。
- 判断模型是否可以交给 Rule Engine。

不允许：

- 生成审计结论。
- 生成 finding。
- 判定 severity。
- 执行业务规则。

一句话：

```text
Early Validation 检查模型是否准备好，不判断底稿是否通过。
```

### 5. Rule Engine

Rule Engine 是确定性 truth source。

职责：

- 执行确定性规则。
- 判断字段完整性。
- 判断金额、阈值、勾稽、抽样匹配。
- 输出 rule result。

不允许：

- 调用 LLM。
- 依赖 LLM 做确定性结论。
- 修改 ingest 数据。
- 被 Report 或 LLM 改写结果。

一句话：

```text
Rules own truth.
```

### 6. Decision Gate

Decision Gate 负责整理并锁定规则输出。

职责：

- 保留 Rule Engine 的确定性结果。
- 标记冲突、不确定性、缺失上下文。
- 将规则结果交给 Control Plane。

不允许：

- 推翻规则结果。
- 调用 LLM。
- 做展示逻辑。

### 7. Control Plane

Control Plane 是 singleton 决策中心。

职责：

- 判断是否需要 Reasoner。
- 判断是否 fallback。
- 判断是否 skip。
- 执行 ambiguity policy。
- 维护唯一 policy authority。

不允许：

- 修改 deterministic rule result。
- 修改 standardized model。
- 被其他分散 policy 旁路。

一句话：

```text
Control Plane 决定路径，不改变事实。
```

### 8. Finding Model

Finding Model 是唯一影响载体。

它承载：

- deterministic findings
- semantic findings
- ingest risks
- manual review route

所有会影响复核、报告、标注或交付的结果，都必须通过 Finding Model 表达。

不允许：

- 让 Report 直接新增影响项。
- 让 LLM 绕过 Finding Model 影响输出。
- 让多个结构并行承载 finding 权限。

### 9. Report

Report 是 Presentation / Delivery Layer。

职责：

- 格式化 finding。
- 导出报告。
- 生成标注底稿。
- 渲染 UI。
- 交付 reviewer 可读结果。

不允许：

- 修改 finding。
- 重新计算 severity。
- 反向影响系统判断。
- 执行业务规则。

一句话：

```text
Report 只交付结果，不制造结论。
```

## 六、System Principles（不可变原则）

### 1. 单执行链原则

系统只有一条主执行链。不允许把 data flow、decision flow、LLM flow 拆成三套独立 runtime pipeline。

### 2. LLM 基础设施原则

LLM 是基础设施，不是业务阶段。所有 LLM 调用都必须通过 LLM Router 治理。

### 3. Control Plane 单例原则

Control Plane 是唯一 policy authority。不允许 ingest policy、rule policy、LLM policy 各自漂移。

### 4. Ingest 语义所有权原则

Ingest 负责理解底稿。Identifier 必须归属于 Ingest Engine，不能变成规则后的补救节点。

### 5. Rules truth 原则

规则层是确定性事实来源。LLM、Report、Control Plane、Identifier 都不能修改 rule result。

### 6. Finding Model 影响载体原则

系统中所有影响 reviewer 行动或交付物的事项，必须通过 Finding Model。

### 7. Report 隔离原则

Report 只展示和交付，不参与判断，不重新计算 severity，不反向影响系统。

## 七、执行流 vs 观察视角

系统执行流只有一条。

但为了观察和解释，可以有三个视角：

```text
Data View      -> input 如何变成 standardized model
Decision View  -> rules 如何变成 finding
LLM View       -> 哪些地方调用了 LLM infrastructure
```

这三个视角只是 observability perspectives，不是工程结构。

不允许：

- 按 data / decision / LLM 三条链路拆代码。
- 让 LLM flow 变成独立系统。
- 让 debug 变成三套追踪链。

## 八、冻结规则

本架构已冻结。后续实施不得违反以下规则：

- 不新增架构层。
- 不改变主执行链。
- 不把 LLM Router 放入主 pipeline。
- 不拆分多个 Control Plane。
- 不把 Identifier 移出 Ingest Engine。
- 不让 Rules 调用 LLM。
- 不让 Report 修改 finding 或 severity。
- 不让任何模块绕过 Finding Model 影响输出。

## 九、最终定义

本架构可以概括为：

```text
Ingest owns understanding.
Rules own truth.
Control Plane owns routing.
LLM Router owns model governance.
Finding Model owns impact.
Report owns delivery.
```


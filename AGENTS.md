# 固定资产质检 Agent

## 项目目标

设计并开发一个**固定资产质检 Agent**，用于承担固定资产审计底稿中的基础复核和可结构化检查工作，帮助质检人员减少重复性核对，把更多时间投入到高风险事项识别、重大审计判断和风险管理。

1. **输入**：固定资产底稿（Excel 为主，含 K.00–K.03、FA list、新增/处置清单、折旧测试等），以及必要的辅助材料（如质检 checklist、TE/SAD 等；后续可扩展 TB、证据索引、影像等）。
2. **检查**：对照 `docs/qc-checklist.md` 与 SOP，完成基础 review 工作并识别 **findings**；能结构化判断的事项由规则自动检查，涉及审计判断、证据充分性或项目背景的事项标为 `NEED_REVIEW`，交由质检人员重点复核。
3. **输出（必交付）**：
   - **质检报告**：按程序/检查点汇总 findings、严重级别、统计与复核建议（支持 JSON、Excel 等）。
   - **底稿标注**：在**原底稿副本**上对存在问题的工作表、行或单元格添加批注/高亮等标注，便于审计人员对照修改（不强制覆盖用户原件，默认输出带标注副本）。

结论仅使用：`PASS`、`WARN`、`FAIL`、`NEED_REVIEW`。

## 必交付项

| 交付物 | 说明 | 状态 |
| --- | --- | --- |
| 质检报告 | 结构化 findings 清单 + 汇总（程序维度、资产/行维度） | 进行中（JSON 结构已通，正式报告与 Excel 待完善） |
| 底稿标注 | `*_qc_annotated.xlsx`：双 Comments 表 + 单元格批注（见 [docs/workpaper-annotation.md](docs/workpaper-annotation.md)） | **M2a 首版已通** |

## 演进方向：大模型 Agent（M3+）

终态 Agent **不是** Cursor 内置助手，而是**本地/内网独立程序** + **可配置 LLM API**（OpenAI 兼容端点，支持私有化）。

**产品优先级（2026-05-21）**：

1. **质检点执行准确**最重要：`ingest` 读对 + `rules` 逐条判对（`AUTO_FAIL`/`AUTO_WARN`/有据的 `NEED_REVIEW`）。
2. **LLM 服务全过程**：ingest 映射、**规则语义**（`--llm-rules`）、**checklist 评估**（`--llm-checklist`）——不是报告摘要为主。
3. **报告叙述**（`--llm` / `llm_enrichment`）已实现但**优先级最低**；不替代规则、不提升各检查点判定准确性。

- **M2a（当前）**：规则引擎 + 整底稿流水线（Lead/K.01 规则为 P0）。
- **M3c（高优先级）**：`src/llm/rule_review.py`、`checklist_assess.py` 等挂在具体质检点。
- **原则**：金额勾稽、唯一性、必填等由 `rules` 判定；LLM **不得**单独将 FAIL 改为 PASS。默认 `FA_QC_LLM_ENABLED=false`。

路线图：[docs/llm-agent-roadmap.md](docs/llm-agent-roadmap.md) · 决策：[docs/decisions/ADR-0002-llm-agent-evolution.md](docs/decisions/ADR-0002-llm-agent-evolution.md)

## 当前阶段：M1 已完成切片 → **M2a 进行中**

**M1（已完成的技术切片）**：ingest 诊断与字段映射、规则字典注册表、3 条资产台账类规则（`fa_list_*`，适用于标准底稿 FA list **或** 客户外挂台账）、JSON 报告骨架。

**M2a（当前 Agent P1，非「FA list 优先」）**：整本底稿流水线 + 双必交付雏形，业务规则优先 **汇总页（PSP/拒绝理由）** 与 **K.01 后推表**：

- 编排：`fa-qc-run`（底稿路径 → 多 sheet 解析 → 检查 → 报告 + 标注副本）。
- 解析：整本 Excel 多 sheet 结构化（不限于 FA list）；客户台账为可选第二输入。
- 规则：AE-003（PSP 执行/拒绝理由）、K.01 后推存在性与列完整性等（见 `docs/rule-dictionary-mapping.md`）。
- 输出：程序维度质检报告 + 底稿单元格批注（`*_qc_annotated.xlsx`）。

`fa_list_*` 规则保留复用，但 **不** 作为当前里程碑的主线。终态验收仍以「报告 + 底稿标注」为准。

## 推荐技术栈

- Python 作为第一版实现语言。
- `openpyxl` 读取/写入 Excel（含批注与样式）。
- `pandas` 可选，用于大批量表数据处理。
- `pydantic` 用于字段结构校验。
- `pytest` 用于规则单测。

## 模块边界

- `src/ingest/`：读取底稿与辅助文件、字段映射、基础清洗；不写具体质检规则。
- `src/rules/`：按 checklist 执行规则，产出统一 finding 结构；不处理文件导入导出。
- `src/report/`：汇总 findings、生成质检报告；**负责底稿标注回写**（批注/高亮/标注副本），不实现业务规则本身。
- `src/llm/`（M3）：API、脱敏；**优先**规则语义与 checklist（规划 `--llm-rules` / `--llm-checklist`）；层 4 报告叙述（`--llm`）为可选低优先级。
- `tests/fixtures/`：仅存放脱敏样例数据。
- `tests/rules/`：存放规则单元测试。

## 质检结论枚举

- `PASS`：校验通过。
- `WARN`：存在轻微风险，建议业务确认。
- `FAIL`：明确不符合规则。
- `NEED_REVIEW`：规则无法自动判断，需要人工复核。

## 数据安全约定

- 不提交真实资产编号、真实部门名称、真实人员信息、真实合同或发票信息。
- 样例资产编号使用 `FA-TEST-001` 这类脱敏编号。
- 涉及真实数据分析时，只提交规则、脚本和脱敏后的 fixture。
- **LLM API 密钥**：只放在项目根目录 **`.env`**（已在 `.gitignore`）；**禁止** `git add .env` 或在代码/文档中写真实 API 密钥。提交前运行 `python scripts/check_staged_no_secrets.py`。详见 **[docs/data-security.md](docs/data-security.md)**。

## Agent 协作约定（先答后改）

与 Agent（含 Cursor）协作的**默认方式**：

1. **先回答**问题或分析现象，不默认直接改代码。
2. **确认理解一致**（改什么、不改什么、如何验收）后，再开始修改。
3. **`git commit` / `git push` 前须单独列清单并等你确认**（即使用户说「保存并推送」亦然）；不含 `.env` 与真实 API 密钥。
4. 用户在同一条消息中已明确「请修改」且范围清楚时，可视为已确认改代码；**不**自动视为已确认提交/推送。

### 写入动作硬性确认规则

任何会修改文件或生成项目内产物的动作，执行前必须先向用户列明并等待明确确认：

- **拟修改范围**：具体文件、目录或将生成的产物。
- **修改内容**：准备改什么、为什么改、对质检结果有什么影响。
- **不修改内容**：明确哪些文件、规则、测试、输出或 git 操作不在本次范围内。
- **验收方式**：用什么命令、报告或人工检查确认结果。

用户说“保存”“沉淀”“完善”“继续推进”“开始处理”不等于已确认写入；只有用户明确表达“确认修改”“可以改”“开始改”“按这个范围执行”等，才可进行写入。只读分析、读取文件、搜索、查看测试结果可以先执行；写代码、改文档、改测试、覆盖配置、生成并保存项目内报告/标注文件，都必须先确认范围。`git add`、`git commit`、`git push` 即使已获代码修改确认，也必须再次单独确认。

每完成一个小阶段，Agent 应先用简短清单说明是否建议沉淀到 `docs/handoff/latest.md` 或相关规则文档；只有在用户明确确认后，才可写入 handoff、规则文档或其他项目记忆文件。阶段沉淀也属于写入动作，适用上述确认规则。

### Token 节约与超时停手规则

为节约 token，并避免长时间沿错误方向试错，Agent 处理问题时默认采用分阶段方式：

1. **先只读诊断，不改代码**：先阅读相关文件、定位问题范围，并给出简短判断；如果问题原因不明确，不直接进入长时间试错。
2. **写入前必须列范围并等待确认**：说明准备改哪些文件、为什么改、不改哪些内容、用户如何验收。
3. **单次执行预算**：如果一个问题预计需要超过 5 分钟，或实际连续处理超过约 5 分钟仍无明确结论，Agent 必须停止并汇报已确认的信息、卡点、可能处理方向和推荐下一步。
4. **默认不主动跑完整测试**：代码写好后，Agent 只说明建议验收命令，由用户自行测试；只有用户明确要求，或测试非常短且对确认修改必要时，才运行必要测试。
5. **禁止长时间盲目试错**：不允许连续反复改代码、跑命令、看输出超过约 5 分钟；如果没有新证据，应先停下来重新评估方法。

### 通用 Excel 读取规范

为了避免中文路径、编码和引号问题反复消耗时间，读取任何本地 Excel 文件时默认按同一套动作执行：

1. **先拿真实全路径**：先用 PowerShell 取 `FullName`，不要手写猜路径。
2. **再把路径当参数传给脚本**：让 Python/Node 通过 `argv` 接收文件路径，不把中文路径直接拼进长命令字符串。
3. **优先用固定小脚本**：复杂解析用可复用脚本或短命令，不临时堆一条很长的 `-c` 命令。
4. **先读后改**：先只读确认工作簿名称、sheet 名、维度、合并单元格和关键锚点，再决定是否修改代码或文档。

推荐模板：

```powershell
$p = (Get-ChildItem -LiteralPath 'E:\AI file\固定资产质检agent\资料库' | Where-Object Name -eq 'K1 SWP 固定资产 202YMMDD XYZ公司.xlsx').FullName
& '.\.venv\Scripts\python.exe' .\scripts\inspect_workbook.py --path $p
```

如果没有现成脚本，再临时用 Python 读取，但仍然要把路径作为参数传入，避免中文路径被命令行转义弄乱。

### 沟通语言要求（面向审计人员）

默认把用户当作**有审计专业背景、只有少量 IT 基础**的协作者来解释问题：

- 先用一句话说清楚**结论/建议**，再补充原因。
- 少用工程黑话；必须使用时同时解释，例如：`ingest` = 读取底稿并整理字段，`rules` = 自动检查规则，`report` = 输出报告和标注。
- 说明修改方案时，按「改什么、为什么改、对质检结果有什么影响、怎么验收」来写。
- 验收命令要说明用途，例如 `pytest tests/rules -q` 是“跑规则测试，确认自动检查没有被改坏”。
- 复杂任务优先用 2–5 条短句，不堆长段技术说明。

全文：[docs/agent-collaboration.md](docs/agent-collaboration.md)

## 开发约定

- 开发新规则前，先查看 `docs/domain-glossary.md`、`docs/qc-checklist.md` 和 `docs/handoff/latest.md`。
- 修改 `src/rules/` 时，必须同步增加或更新 `tests/rules/`。
- 规则含义、错误码或严重级别发生变化时，更新 `docs/architecture.md` 或 `docs/decisions/`。
- 每天收工前更新 `docs/handoff/latest.md`，说明已完成、进行中、下一步和风险。

## 新会话启动提示

建议在 Cursor 新会话第一条消息中使用：

```text
继续固定资产质检 Agent 开发。
请先阅读 AGENTS.md、docs/agent-collaboration.md、docs/handoff/latest.md、docs/ONBOARDING.md 和 docs/PROJECT_STRUCTURE.md。
协作方式：先回答/给方案；改代码、git commit、git push 前都先列清单等我确认（见 agent-collaboration.md）。
当前任务是：<写清楚具体任务、分支、涉及文件和验收标准>。
验收标准：<可验证的结果>。
终态验收须包含：质检报告 + 底稿标注（若本次未涉及标注，请说明）。
```

## Repair Queue frozen 规则

进入“问题审计 + P0–P3 分级 + 修复队列生成”阶段时，必须按 `docs/repair-queue-system.md` 执行。该文件为 Repair Queue System Prompt v1.2（Frozen），只用于问题审计、分级和修复队列生成；不得借此新增分类、层级、架构解释或扩展 Control Plane。

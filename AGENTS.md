# 固定资产质检 Agent

## 项目目标

建设一个**固定资产质检 Agent**，模拟质检人员对审计底稿的复核过程：

1. **输入**：固定资产底稿（Excel 为主，含 K.00–K.03、FA list、新增/处置清单、折旧测试等），以及必要的辅助材料（如质检 checklist、TE/SAD 等；后续可扩展 TB、证据索引、影像等）。
2. **检查**：对照 `docs/qc-checklist.md` 与 SOP，逐项检查底稿是否存在 **findings**；能结构化的自动判断，需审计判断的标为 `NEED_REVIEW`，不强行下结论。
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

## 开发约定

- 开发新规则前，先查看 `docs/domain-glossary.md`、`docs/qc-checklist.md` 和 `docs/handoff/latest.md`。
- 修改 `src/rules/` 时，必须同步增加或更新 `tests/rules/`。
- 规则含义、错误码或严重级别发生变化时，更新 `docs/architecture.md` 或 `docs/decisions/`。
- 每天收工前更新 `docs/handoff/latest.md`，说明已完成、进行中、下一步和风险。

## 新会话启动提示

建议在 Cursor 新会话第一条消息中使用：

```text
继续固定资产质检 Agent 开发。
请先阅读 AGENTS.md、docs/handoff/latest.md、docs/ONBOARDING.md 和 docs/PROJECT_STRUCTURE.md。
当前任务是：<写清楚具体任务、分支、涉及文件和验收标准>。
终态验收须包含：质检报告 + 底稿标注（若本次未涉及标注，请说明）。
```

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
| 底稿标注 | 将 findings 回写至底稿对应位置（批注、高亮或专用标注 sheet） | **未开始** |

## 当前阶段：M1（通向终态的基础设施）

当前实现的是终态中的**底层能力切片**，不是完整 Agent：

- 读取与诊断：`src/ingest/`（sheet 分类、字段映射、`fa-qc-diagnose`）。
- 首批 FA list 规则：`fa_list_required_fields`、`unique_asset_id`、`asset_value_consistency`。
- 报告骨架：`src/report/`（JSON 汇总；**尚无底稿回写**）。

M1 完成后应能：对脱敏样例/案例底稿跑通「读取 → 规则 → JSON 报告」；**终态验收**仍以「报告 + 底稿标注」双交付为准。

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

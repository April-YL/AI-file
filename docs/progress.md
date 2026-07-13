# 项目进度

本文给阅读仓库的开发者提供阶段性能力概览。当前接手事项见 [`handoff/latest.md`](handoff/latest.md)，具体可执行规则以 `src/rules/registry.py` 为准。

## 里程碑

| 里程碑 | 目标 | 当前状态 |
| --- | --- | --- |
| M0–M1 | 项目骨架、资料沉淀、工作簿读取、规则注册表和报告骨架 | 已完成 |
| M2a | 整本底稿流水线、汇总页、K.00 Lead、K.01、报告与标注首版 | 已完成首版并持续校准 |
| M2b | K.02 新增与处置的读取、勾稽、选样和详细测试规则 | 已接入主流程，持续校准真实版式 |
| M2c | K.03 路径识别、SAP/TOD/政策规则及执行台账 | 已接入主流程；SAP 阶段 2 已完成 |
| M3a | 可配置 LLM 客户端、脱敏和报告叙述增强 | 已实现，可选且默认关闭 |
| M3c | LLM 参与规则语义和 checklist 逐点辅助复核 | 规划中，不能替代确定性规则 |
| M4 | 影像、合同、发票等非结构化材料 | 未开始 |

## 当前可运行成品

- `fa-qc-run`：从底稿输入到 JSON/HTML 报告和标注副本的整本流水线。
- `fa-qc-ui`：本地 Streamlit 复核界面，展示 findings、执行台账、取数证据和交付物。
- `src/ingest/`：汇总页、Lead、K.01、K.02、K.03、FA list 等工作表识别和结构化读取。
- `src/rules/`：汇总页、Lead、K.01、K.02 新增/处置、K.03 SAP/TOD/政策和 FA list 规则。
- `src/report/`：结构化报告、HTML、UI 和 `*_qc_annotated.xlsx` 标注副本。
- `src/llm/`：可选的 OpenAI 兼容接口与脱敏/辅助复核能力。

## 2026-07-13 基线

- K.03 已使用工作簿级 `K03ExecutionProfile` 识别并分派 SAP 中精度、SAP 高精度、TOD by-item、TOD 抽样和折旧政策复核路径。
- SAP 策略选择、SAP TE 与 Lead TE 一致性、高精度 SAP CRA 与 Lead V/M CRA 一致性已进入规则和执行台账。
- 多张实际执行的 SAP 程序页分别检查并保留取数证据；缺少必要参数时记录 `DATA_INSUFFICIENT`，不适用路径记录 `NOT_APPLICABLE`。
- 最近 K.03 SAP、runner、registry 和执行覆盖聚焦测试结果为 `32 passed`；这不是全仓测试结论。

## 主要剩余事项

1. 按真实底稿版式持续校准 K.00–K.03 的读取准确性和规则误报/漏报。
2. 完善正式 Excel 质检报告；当前结构化 JSON、HTML、UI 与标注副本已可用。
3. 继续补齐 checklist 中仍为 `manual_only`、`planned` 或证据不足的检查点。
4. K.03 的特别风险、实体类型选择和复杂证据充分性继续由人工复核，未作为已自动完成展示。
5. LLM 规则语义和 checklist 辅助能力仍处规划阶段，确定性规则保持最终自动判定权。

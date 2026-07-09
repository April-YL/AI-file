# K.03 MVP 开发计划

## 目标

K.03 MVP 的目标不是一次性完成 K.03 全路径，而是先形成可展示、可回归、边界清楚的最小闭环：

1. 优先完成折旧测试中的 TOD-by item ingest + rules；
2. 紧接完成折旧政策复核 ingest + 最小 rules；
3. SAP 中精确度、SAP 高精确度、TOD-抽样、SAP + TOD-抽样组合先以“路径识别 + 部分确定性规则 + 人工复核边界”的方式纳入第一阶段，不一次性判断全部证据充分性。

> 2026-07-09 更新：本文原先的 1A–1F 是早期 MVP 计划。当前实际进度已经完成 K.03 第一阶段扩展：SAP 中/高精度、TOD 抽样、TOD by-item、折旧政策复核均已接入主 runner、registry、execution ledger 和 checklist 映射 v0.5。下文保留原阶段结构，但早期“仅保留 SAP / TOD-抽样路径识别”的旧口径已不再代表当前状态。

## A. K.03 业务结构

K.03 包含两个重要测试：

1. 折旧测试；
2. 折旧政策复核。

折旧测试包含四种执行路径：

1. SAP 中精确度；
2. SAP 高精确度；
3. TOD-抽样；
4. TOD-by item。

必要时，折旧测试可以是 SAP + TOD-抽样组合。

## B. 当前 MVP 范围

当前为了满足整体进度展示，MVP 不追求一次性完成 K.03 全路径。早期优先完成：

1. TOD-by item 折旧测试；
2. 折旧政策复核。

早期 MVP 暂不展开：

1. SAP 中精确度详细规则；
2. SAP 高精确度详细规则；
3. TOD-抽样详细规则；
4. SAP + TOD-抽样组合充分性判断。

当前第一阶段已补充展开：

1. SAP 中精确度 / 高精确度路径识别、精确度选择与差异处理提示；
2. TOD-抽样主测试页与 `K.03.2a` 选样输出识别、抽样过程与差异处理提示；
3. TOD-by item 明细读取、重算差异和 K.01 折旧勾稽；
4. 折旧政策复核轻量读取、基础完整性和明显异常提示。

仍不自动覆盖的边界：

1. SAP + TOD-抽样组合是否足以支持整体审计结论；
2. 抽样证据、解释和支持性文件是否充分；
3. 折旧政策合理性的复杂语义判断；
4. 涉及项目背景、重大判断或非标准底稿结构的人工复核事项。

## C. 已完成阶段

阶段 1A 已完成：

1. K.03 dataset schema；
2. K.03 两个分支识别；
3. 折旧测试 execution_path 识别；
4. TOD-by item 详细 ingest；
5. 折旧政策复核 lightweight ingest；
6. SAP / TOD-抽样 later-phase marker；
7. 大表 deterministic 全量 ingest、LLM/report 轻量 context；
8. K.03 ingest 不产生 finding 的护栏。

阶段 1B–1F 当前状态：

1. TOD-by item deterministic rules 已接入；
2. 折旧政策复核最小 rules 已接入；
3. SAP 中/高精度第一阶段规则已接入；
4. TOD-抽样第一阶段规则已接入；
5. K.03 report / execution ledger 已随主流程输出；
6. checklist 映射已同步至 `规则映射v0.5_K03更新` 和 `当前规则能力目录_v2`。

阶段 1A checkpoint：

```text
069e3bb feat: add phase 1A K03 ingest dataset
```

## D. 后续阶段规划

### 阶段 1B：TOD-by item 折旧测试 deterministic rules

目标：

1. 基于阶段 1A ingest dataset 输出最小 finding；
2. 优先覆盖高频实际底稿；
3. 不依赖 LLM；
4. 本阶段原计划仅覆盖 TOD-by item；当前已由 2026-07-09 第一阶段扩展补齐 SAP / TOD-抽样部分自动规则。

建议规则：

1. 明细区/表头识别失败；
2. 关键字段缺失 warning；
3. 管理层折旧 vs 审计重算折旧差异；
4. 差异列/重算差异异常；
5. 合计行勾稽；
6. 有重大差异但结论区为空或无解释；
7. 非关键字段缺失不直接 FAIL。

### 阶段 1C：折旧政策复核 ingest + 最小 rules

目标：

1. 折旧政策复核作为 K.03 的重要测试分支；
2. 不做复杂语义判断；
3. 先做完整性和明显异常检查；
4. 准备 LLM candidate context，但 LLM 不覆盖 deterministic rules。

建议规则：

1. 折旧政策复核 sheet 缺失；
2. 政策描述/管理层说明/审计判断/结论区缺失；
3. 结论区为空；
4. 出现 TBD、待补、占位符、未完成痕迹；
5. N/A 但无说明；
6. 文本区进入 llm_candidate_context，后续再做语义判断。

### 阶段 1D：K.03 report section 接入

目标：

1. 报告中展示 K.03 折旧测试和折旧政策复核结果；
2. 展示 summary / finding / warnings / sheet-row-cell 定位；
3. 不输出全量明细表；
4. 不把 full detail rows 传入 LLM/report。

### 阶段 1E：K.03 MVP 回归测试与误报防护

目标：

1. TOD-by item 正常底稿不误报；
2. 有差异底稿能报；
3. 折旧政策复核完整时不误报；
4. 折旧政策复核空白/待补能报；
5. K.01 / K.02 阶段 0 护栏仍通过；
6. 大表不截断；
7. LLM context 保持轻量。

### 阶段 1F：后续完善

后续完善包括：

1. SAP 中精确度详细证据充分性判断；
2. SAP 高精确度详细证据充分性判断；
3. TOD-抽样样本证据充分性和支持性文件判断；
4. SAP + TOD-抽样组合判断；
5. 更细的 LLM semantic checks。

## E. 数据分层原则

1. FA list、新增清单、处置清单、K.03 TOD-by item 明细表属于核心明细表，deterministic ingest 不应受 max_rows 截断。
2. max_rows 只能用于 sheet preview / classification / unknown sheet / LLM preview，不应用于已识别核心明细表的 deterministic data。
3. LLM/report/context 不应默认携带全量明细。
4. context 只暴露 row_count、column_count、table_range、raw_columns、normalized_column_map、warnings、summary、preview_rows、finding refs。
5. full detail rows 只能用于 deterministic rules，不进入 LLM candidate context。
6. 后续 deterministic rules 如需全量数据，应通过 detail_table_ref / table store 回读 full table，而不是从 LLM context 读取。

## F. 阶段边界

1. 当前主线不是完整 K.03 全路径，而是 K.03 第一阶段闭环。
2. 当前已覆盖 TOD-by item、折旧政策复核、SAP 中/高精度和 TOD-抽样的部分自动规则。
3. SAP / TOD-抽样已经纳入第一阶段，但复杂证据充分性和组合结论仍是后续完善项。
4. 不允许 LLM 覆盖 deterministic rules。
5. 不允许因为非关键字段缺失直接 FAIL。
6. 不允许将全量明细塞入 report 或 LLM context。

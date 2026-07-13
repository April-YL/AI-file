# 架构说明

固定资产质检 Agent 第一版采用清晰的三段式架构：数据接入、规则质检、报告输出。每个模块保持边界清楚，便于后续接入更多数据源和规则。

业务流程和底稿口径以 `docs/audit-workflow.md`、`docs/qc-checklist.md`、`docs/workpaper-fields.md` 和 `docs/rule-dictionary-mapping.md` 为准。

业务规则需求以脱敏规则字典（`tests/fixtures/rule_dictionary_sanitized.csv`）为准；代码注册表见 `src/rules/registry.py`。

规则真源、资料识别事实、执行台账、执行证据和 UI 展示边界见 [fa_qc_governance_plan.md](architecture/fa_qc_governance_plan.md)。

## 数据流

### 当前（M1 / M2a）

```text
固定资产标准底稿/台账/样例数据
        |
        v
src/ingest/      读取、字段映射、基础清洗
        |
        v
src/rules/       执行质检规则，产生结构化问题
        |
        v
src/report/      汇总结果，输出报告或人工复核清单
```

### 目标（M3+ 大模型 Agent）

```text
底稿/台账
    → ingest ──(+ 可选 llm-map)──→ 结构化数据
    → rules  ──→ findings（severity 仅由此判定）
              ↘
               llm-rules / llm-checklist（可选，语义项 + 逐条 checklist）
              ↗
    → report → JSON + HTML + 标注副本
              ↘
               llm 层 4 叙述（可选，低优先级；不改变 severity）
```

**产品优先级**：质检点准确 = **rules + ingest**；LLM 主战场为 **规则语义 + checklist**，非报告摘要。详见 [llm-agent-roadmap.md](llm-agent-roadmap.md) § 产品优先级。

编排入口仍为 **`fa-qc-run`（本地 CLI）**；不依赖 Cursor。

## 模块职责

### `src/ingest/`

- 读取 Excel、CSV 或后续 API 输入。
- 将原始列名映射为标准字段名。
- 执行轻量清洗，例如去除空格、标准化日期格式。
- 识别来源工作表，例如 `FA list`、`新增清单`、`处置清单`、`K.03.2 折旧测试TOD`。
- 不实现业务质检规则。

### `src/rules/`

- 每条规则独立实现，便于单测和维护。
- 规则输入为标准化资产记录（或汇总页等结构化数据集）。
- 规则输出统一的质检问题结构。
- 规则设计优先参考 `docs/qc-checklist.md` 中的 `AUTO_FAIL` 和 `AUTO_WARN` 项。
- **不实现 ingest 与全本扫表**；除编排层**显式传入** workbook 路径与表名列表时的轻量级勾稽外（如 AE-003 `psp_completion` 与工作表名称/浅层内容密度），规则模块不自行解析整本底稿，也不负责报告导出。

### `src/report/`

- 汇总每条资产的质检结果。
- 生成错误明细、资产级结论和统计摘要。
- 区分自动化失败、预警和人工复核项。
- **底稿标注**：`export_annotated_workbook.py` → `*_qc_annotated.xlsx`（`Comments【归档前删除】` 主汇总 + `Comments【FA list】` 明细；见 [workpaper-annotation.md](workpaper-annotation.md)）。
- **UI**：`ui_app.py` / `fa-qc-ui`；**精简 HTML**：`export_review_html.py`。
- JSON 报告、`manual_review_sections`（AE-001/002 人工核对摘录）。

### `src/llm/`（M3，部分实现）

| 能力 | 状态 | 优先级 |
| --- | --- | --- |
| `config` / `client` / `redact` | 已实现 | 基础设施 |
| `rule_review`（`--llm-rules`） | **待做** | **P1** |
| `checklist_assess`（`--llm-checklist`） | **待做** | **P1** |
| `map_headers`（`--llm-map`） | 待做 | P2 |
| `review` + `workbook_payload`（`--llm`，层 4 叙述） | 已实现 | **P3（低）** |

- 调用可配置 **LLM API**（OpenAI 兼容）；脱敏后仅传结构化摘录 + findings。
- **不**替代 `rules` 中 `AUTO_FAIL` / `AUTO_WARN`；**不**将 FAIL 改为 PASS。
- 默认关闭（`FA_QC_LLM_ENABLED=false`）。

## 质检问题结构

MVP 阶段建议每个问题包含以下字段：

```json
{
  "asset_id": "FA-TEST-001",
  "procedure_code": "FA_LIST",
  "source_sheet": "FA list",
  "rule_id": "fa_list_required_fields",
  "dict_rule_code": "FA-RC-001",
  "rule_name": "FA list 必需字段完整",
  "field": "asset_name",
  "severity": "FAIL",
  "automation_level": "AUTO_FAIL",
  "problem_category": "基础程序",
  "reviewer_role": "preparer",
  "message": "资产名称不能为空",
  "suggestion": "补充资产名称后重新提交质检"
}
```

## 错误码命名

- 规则 ID 使用小写蛇形命名，例如 `required_fields`。
- 字段级问题写入 `field`。
- 跨字段问题可将 `field` 设为 `null` 或组合字段名，例如 `original_value/net_value`。

## 规则实现阶段

| 阶段 | 说明 |
| --- | --- |
| **M1（已完成）** | 3 条 `fa_list_*` + `run_fa_list_qc`；适用于 FA list sheet 或客户外挂台账（统一 `AssetRecord`） |
| **M2a（Agent P1）** | `fa-qc-run` 编排；整本底稿解析；**汇总页 PSP（AE-003）**、**K.01 后推（`rollforward_*`）**；报告 + 底稿批注 |
| **M2b** | K.02、折旧、qc-checklist 其余 `AUTO_*` 项 |
| **M3（大模型 Agent）** | `src/llm/` + API 配置；`--llm` 增强 NEED_REVIEW；详见 [llm-agent-roadmap.md](llm-agent-roadmap.md) |
| **M4** | 内网 Web/API 产品化 |

`docs/qc-checklist.md` 与 `docs/rule-dictionary-mapping.md` 为规则全集索引；实现顺序以 **M2a 流水线 + 汇总/K.01** 为准，而非 FA list 规则数量。

涉及 Canvas、CRA、TE/SAD 外部一致性、证据充分性等事项，优先 `NEED_REVIEW`，不阻塞 M2a。

## 当前不做

- 不接入真实生产系统。
- 不提交真实资产数据。
- 不实现影像 OCR。
- 不实现复杂工作流审批。
- 不引入数据库，先以文件和内存数据结构完成 MVP。

## 后续演进

### K.03 SAP 策略与参数规则

K.03 先识别程序页的实际执行状态，再进入规则判断。每个组成页使用 `EXECUTED`、`TEMPLATE_ONLY`、`INCOMPLETE`、`AMBIGUOUS` 四种状态；结论栏未填写不影响“已执行”识别，项目参数、计算痕迹、明细或抽样记录才是主要证据。工作簿同时执行多种折旧测试时，runner 对所有实际执行路径分别检查，不以 `primary_depreciation_path` 排除其他路径。

折旧测试通常四选一：SAP 中精度、SAP 高精度、TOD by-item、TOD 抽样。SOP 和 J 案例同时执行多条路径，不代表实务底稿必须执行全部路径。K.03.3 折旧政策复核是独立必要程序，不属于上述四选一；“本期计提”工作表仅作为辅助信息，不构成程序执行证据。

- `sap_precision_selection` 依据工作簿级 `K03ExecutionProfile` 已关联的 Lead 计价/计量（V/M）CRA 判断中、高精度策略；中精度模板预设的 `Minimal` 不作为 Lead CRA。
- `sap_te_consistency` 独立检查 SAP 使用的 TE 与 Lead TE；`sap_high_cra_consistency` 仅适用于高精度 SAP，独立检查页内 CRA 与 Lead V/M CRA。
- SAP 路径适用但必要参数无法可靠读取时，规则在 `execution_ledger` 记录 `DATA_INSUFFICIENT`；非对应路径记录 `NOT_APPLICABLE`，不得默认为已执行或通过。
- `sap_special_risk_tod_required` 在特别风险、控制依赖和控制有效性形成可靠结构化来源前，不进入可执行 registry。

- **大模型 Agent（已规划）**：规则 + LLM API 混合；见 ADR-0002。
- 增加资产类别枚举和折旧年限规则。
- 接入影像、合同、发票等非结构化材料。
- 增加人工复核状态流转。
- 提供内网 API 服务或 Web 页面（与 Cursor 解耦）。

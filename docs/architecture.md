# 架构说明

固定资产质检 Agent 第一版采用数据接入、规则质检、报告输出三段式架构。Pilot 两批测试后，目标架构进一步明确为：在保留模块边界的基础上，由统一 Orchestrator 组织唯一正式执行链，由统一 LLM Router 管理贯穿识别、规则和报告的 LLM 能力。

业务流程和底稿口径以 `docs/audit-workflow.md`、`docs/qc-checklist.md`、`docs/workpaper-fields.md` 和 `docs/rule-dictionary-mapping.md` 为准。

业务规则需求以脱敏规则字典（`tests/fixtures/rule_dictionary_sanitized.csv`）为准；代码注册表见 `src/rules/registry.py`。

规则真源、资料识别事实、规则级 Readiness、执行台账、执行证据和 UI 展示边界见 [fa_qc_governance_plan.md](architecture/fa_qc_governance_plan.md)。统一编排与 LLM 治理的当前正式决策见 [ADR-0003](decisions/ADR-0003-unified-orchestrator-and-llm-governance.md)。

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

### 当前目标（Pilot 准确性修复 + M3）

```text
输入底稿
  → Orchestrator（唯一正式执行链）
      → ingest：确定性识别、候选与证据
      → LLM Router / identification（歧义时可选兜底）
      → 系统验证 + 规则级 Readiness
      → rules
          ├─ 纯代码规则
          ├─ 纯 LLM 语义规则
          └─ 代码 + LLM 联合规则
      → finding / execution_ledger / observation
      → report：JSON + HTML + 标注副本 + 可选 narrative
```

**产品优先级**：质检点准确优先于 finding 数量和报告叙述。先修复工作表/字段识别和规则级准入这一最低层共同根因，再校准具体规则和输出。LLM 是识别兜底、语义规则、联合规则和报告叙述的统一受控能力，不只是报告增强。

产品入口仍包括 **`fa-qc-run`（本地 CLI）**和 Streamlit UI；二者必须进入同一个 Orchestrator 和同一套 LLM 配置，不依赖 Cursor。

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
| 统一 LLM Router | 待统一 | **基础设施** |
| `identification`（识别兜底） | 部分复核能力已存在，尚未进入规则前闭环 | **P1** |
| `rule_review` / `hybrid_rule` | 部分模块已存在，尚未统一治理 | **P1** |
| `review` + `workbook_payload`（`--llm`，层 4 叙述） | 已实现 | **P3（低）** |

- 所有 LLM 调用最终必须经统一 LLM Router，使用总开关、分能力开关和按规则控制；默认总开关关闭。
- LLM 可以参与识别、纯 LLM 语义规则和代码 + LLM 联合规则，但不得绕过 registry 和 Orchestrator 直接形成正式 finding。
- 金额勾稽、唯一性、必填等确定性部分仍由代码基于已验证字段执行；LLM 不得无依据将确定性 `FAIL` 改为 `PASS`。
- 调用可配置 OpenAI 兼容 API；传输遵守脱敏和最小必要原则。

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

### K.03 TOD 抽样动态识别

TOD 抽样主测试表和选样输出使用语义锚点、表头字段组合、数据行形态和区块边界动态识别。sheet 名仅作为辅助证据，不得覆盖内容证据；生产逻辑禁止固定行号、列号、单元格地址和固定 sheet 顺序。多个候选表格或必要字段不可读时记录 `AMBIGUOUS` / `DATA_INSUFFICIENT`，不得猜测或默认通过。

选样输出中的关键项和代表性样本构成默认应测试集合；替换样本属于候补池，只有实际进入主测试时才提示人工复核替换依据。总体与 K.01 的差异判断只使用底稿可追溯的 SAD，SAD 缺失时不得构造替代审计阈值。

- **大模型 Agent（已规划）**：规则 + LLM API 混合；见 ADR-0002。
- 增加资产类别枚举和折旧年限规则。
- 接入影像、合同、发票等非结构化材料。
- 增加人工复核状态流转。
- 提供内网 API 服务或 Web 页面（与 Cursor 解耦）。

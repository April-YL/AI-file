# 大模型 Agent 演进路线图

本文描述固定资产质检项目从**规则引擎**演进为**大模型 Agent** 的路径。决策记录见 [decisions/ADR-0002-llm-agent-evolution.md](decisions/ADR-0002-llm-agent-evolution.md)。

## 终态：大模型 Agent 是什么

在本项目中，「大模型 Agent」指：

- **本地/内网运行的编排程序**（`fa-qc-run` 及后续服务），不依赖 Cursor；
- **调用可配置 LLM API**（OpenAI 兼容），对无法仅靠表格规则判断的事项做语义复核；
- **输出仍为结构化 findings + 质检报告 + 底稿标注**，结论枚举不变；
- **规则引擎始终存在**，作为可信、可回归测试的底座。

不是：把整本 Excel 丢给聊天窗口人工问答。

LLM 增强覆盖**三层业务链路**（不仅是报告叙述）：

1. **ingest** — 字段映射 / 表头识别（公司底稿差异大时）
2. **rules** — 对 `REVIEW` 类规则的语义辅助（如拒绝理由是否充分）
3. **checklist** — 对照 K1 checklist 判断检查点是否满足、缺何证据

第四层 **report** 叙述（`llm_enrichment`）已实现骨架；与上述三层并列，默认均可关闭。

## 目标架构

```text
                         fa-qc-run / fa-qc-ui
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
   ingest (+LLM 映射)      rules (+LLM 语义)      checklist (+LLM 评估)
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                          统一 findings (QcIssue)
                                 │
                                 ▼
                    report (+LLM 叙述，可选)
                                 │
                                 ▼
                    JSON / HTML / Excel / 标注副本

         各层 LLM 均经 src/llm/client.py（OpenAI 兼容）→ 可配置 API
         不传整本底稿；经 redact；生产默认全关
```

## 三层 LLM 分工（M3c 目标）

### 层 1：字段映射（ingest）

| 项 | 说明 |
| --- | --- |
| **触发** | `fa-qc-diagnose` 大量 `unmapped_headers`；或规则映射失败 |
| **规划模块** | `src/llm/map_headers.py` |
| **输入** | sheet 名、`SheetKind`、表头列表、1～3 行脱敏样例；`docs/workpaper-fields.md` 标准字段摘要 |
| **输出 JSON** | `mappings[]`（`source_header`, `standard_field`, `confidence`）、`unresolved[]`、`notes` |
| **落地** | 高置信且与规则映射不冲突 → 仅当次运行；稳定后写入 `ingest/constants.FIELD_SYNONYMS` + 单测 |
| **finding** | 低置信 → `ingest_header_mapping_review` / `NEED_REVIEW` |
| **CLI（规划）** | `--llm-map` |

**原则**：LLM **不替代** `field_mapping.py` 的确定性匹配；只补歧义与长尾表头。

### 层 2：质检规则语义（rules）

| 项 | 说明 |
| --- | --- |
| **触发** | 规则已产出 `NEED_REVIEW`（或配置的 `rule_id` 白名单） |
| **规划模块** | `src/llm/rule_review.py` |
| **典型场景** | AE-003 拒绝执行理由是否充分；证据充分性（AT-002/DT-002）；异常波动/预期分析自由文本 |
| **输入** | 单条或批量 issue（脱敏）+ 相关单元格/行摘录（ingest 已结构化部分） |
| **输出** | `llm_rationale`、`suggested_action`；可选 `llm_assessment`（见下） |
| **CLI（规划）** | `--llm-rules` |

**原则**：`severity`（PASS/WARN/FAIL/NEED_REVIEW）**仅由 `rules` 判定**；LLM 不得将 FAIL 改为 PASS。

**仍仅 rules、不接 LLM**：编号唯一、金额勾稽、非负、残值率区间等 `AUTO_FAIL` / `AUTO_WARN`。

### 层 3：Checklist 满足度（checklist）

| 项 | 说明 |
| --- | --- |
| **主数据** | `src/rules/registry.py`、`tests/fixtures/rule_dictionary_sanitized.csv`、`docs/qc-checklist.md` |
| **规划模块** | `src/llm/checklist_assess.py` |
| **流程** | 对每个已注册检查点收集结构化证据（ingest 摘录 + rules findings）→ LLM 对照 checklist 条文 |
| **输出 JSON** | 每检查点：`dict_rule_code`、`assessment`（`satisfied` / `not_satisfied` / `insufficient_evidence` / `not_evaluated`）、`rationale`、`missing_evidence[]` |
| **报告段（规划）** | `checklist_assessments[]`（与 `issues` 并列或挂到对应 issue） |
| **CLI（规划）** | `--llm-checklist` |

**原则**：无结构化证据的检查点标 `not_evaluated`，禁止模型硬判 PASS。

### 层 4：报告叙述（report，M3a 已实现）

| 项 | 说明 |
| --- | --- |
| **模块** | `src/llm/review.py`、`prompts.py` |
| **触发** | `--llm` / UI「启用大模型增强」 |
| **输入** | 脱敏后全部 issues + 可选汇总程序表 |
| **输出** | `llm_enrichment`（`executive_summary`、`need_review_notes`） |

### 编排与扩展字段（规划）

| 路径 | 作用 |
| --- | --- |
| `src/llm/orchestrate.py` 或 `src/agent/` | 按 CLI 开关调用各层 LLM，合并进 `QcReport` |
| `src/llm/prompts/` | 版本化 prompt（映射 / 规则 / checklist 分文件） |

`QcIssue` / 报告扩展字段（规划，不改动现有 severity 语义）：

| 字段 | 含义 |
| --- | --- |
| `llm_assessment` | `satisfied` / `not_satisfied` / `insufficient_evidence` |
| `llm_confidence` | 0–1 |
| `llm_rationale` | 短文本，供报告与人工复核 |

## 规则 vs 大模型：分工表

| 检查类型 | 示例 | 负责模块 | LLM 层 |
| --- | --- | --- | --- |
| `AUTO_FAIL` / `AUTO_WARN` | 必填字段、编号唯一、金额勾稽 | `rules` only | 无 |
| 表头 / 列映射歧义 | 「卡片编码」「使用年限(年)」 | `ingest` + 同义词表 | **层 1 映射** |
| 结构化但复杂 | K.01 列完整性、后推异常金额 | `rules` 优先 | 边界 case 可层 2 补充说明 |
| `REVIEW` | PSP 拒绝理由、证据充分性 | `rules` → `NEED_REVIEW` | **层 2 规则语义** |
| Checklist 满足度 | K1 第 N 条是否满足 | registry + 证据摘录 | **层 3 checklist** |
| 报告叙述 | 程序维度汇总、优先关注项 | `report` | **层 4 叙述**（已实现） |

**总原则**：LLM **不能**单独把 FAIL 改成 PASS；只能补充映射建议、`llm_rationale`、checklist 对照说明，或将 `NEED_REVIEW` 细化为「建议关注项」。

## CLI 开关（规划）

与「一层开关打满 token」解耦；生产建议按需开启。

| 开关 | 默认 | LLM 层 |
| --- | --- | --- |
| （无） | — | 纯规则，零 API |
| `--llm` | off | 层 4：报告 `llm_enrichment`（**已实现**） |
| `--llm-map` | off | 层 1：表头映射建议 |
| `--llm-rules` | off | 层 2：`NEED_REVIEW` 语义辅助 |
| `--llm-checklist` | off | 层 3：检查点满足度 |
| `--llm-all` | — | 上述全开（演示/专项客户） |

环境变量 `FA_QC_LLM_ENABLED` 仍作总闸；细分开关可在 M3c 以 `FA_QC_LLM_MAP` 等扩展，或全部由 CLI 传入 `load_llm_config` 子标志。

UI 侧（规划）：与 CLI 对齐，勾选「映射增强 / 规则语义 / Checklist 评估 / 报告增强」。

## 分阶段交付

### M2a（当前，规则 Agent）

- [x] `fa-qc-run` + FA list 规则 + JSON 报告  
- [x] 汇总页（AE-003）、Lead 摘录（AE-001/002）、整本 `run_workbook_qc`  
- [x] Streamlit UI（`fa-qc-ui`）、HTML 人工核对页  
- [ ] 字段映射准确性（案例库回归，**无 LLM**）  
- [ ] K.01 后推 ingest + `rollforward_*` 规则  
- [ ] Excel 质检报告、底稿批注 `*_qc_annotated.xlsx`  

### M3a — LLM 基础设施（已实现骨架）

| 项 | 说明 |
| --- | --- |
| `src/llm/config.py` | 环境变量加载 |
| `src/llm/client.py` | OpenAI 兼容 chat completions（httpx） |
| `src/llm/redact.py` | 资产编号等脱敏 |
| `fa-qc-run --llm` | 默认 off；`--no-llm` 强制关闭 |
| 单测 | `tests/llm/`，mock HTTP |
| 配置模板 | 根目录 `.env.example` |

### M3b — 汇总页 + AE-003（规则已实现，LLM 上下文已接入）

| 任务 | 字典编号 | 状态 |
| --- | --- | --- |
| 汇总页解析 | ingest `summary_sheet.py` | ✅ |
| PSP 执行/拒绝理由（规则） | AE-003 `psp_completion` | ✅ FAIL/WARN/NEED_REVIEW |
| Excel 整本流水线 | `report/pipeline.py` | ✅ |
| LLM 汇总上下文 | `llm/review.py` + prompts | ✅ `--llm` 时附带程序表 |
| LLM 专属 PSP 语义判定 | AE-003 | 待加强（**M3c 层 2**） |

### M3c — 三层 LLM + Agent 编排

**目标**：LLM 贯穿 ingest / rules / checklist，而非仅报告叙述。任务清单以 `docs/handoff/latest.md` M3c 节为准。

| 序号 | 任务 | 层 | 验收 |
| --- | --- | --- | --- |
| C1 | `src/llm/map_headers.py` + prompt | 1 | mock 测试；输入表头 JSON → 输出 `mappings`；低置信不写入 constants |
| C2 | ingest 挂钩：`unmapped_headers` 超阈值时可选调用；finding `ingest_header_mapping_review` | 1 | fixture 表头；`--llm-map` 可开关 |
| C3 | `src/llm/rule_review.py` + prompt | 2 | 对 AE-003 `NEED_REVIEW`/拒绝理由 issue 附加 `llm_rationale` |
| C4 | `src/llm/checklist_assess.py` + prompt | 3 | 对已 `IMPLEMENTED` 规则码输出 `checklist_assessments[]` |
| C5 | `src/llm/orchestrate.py`：串联 C1–C4 + 现有 `review.py` | 编排 | `fa-qc-run` 支持 `--llm-map` / `--llm-rules` / `--llm-checklist` / `--llm-all` |
| C6 | 报告 schema：`checklist_assessments`、`QcIssue` 扩展字段（可选） | 报告 | JSON/HTML 可展示；**不改变** rules severity |
| C7 | Tools（多步）：`get_sheet_summary`, `list_findings`, `get_checklist_item` | 编排 | 减少单次 prompt；审计日志记录 tool 调用 |
| C8 | UI：细粒度 LLM 勾选 | UI | 与 CLI 开关一致 |
| C9 | `tests/llm/` 扩充 + 文档 | 质量 | 无网络单测全绿；ADR-0002 一致 |

**实施顺序建议**：C1→C2（映射，配合 M2a 字段工作）→ C3（AE-003）→ C4→C6（checklist）→ C5/C7/C8（编排与产品化）。

**与多人分工**：

| 角色 | M3c 相关 |
| --- | --- |
| 接入 | C1–C2；审核 LLM 映射建议后沉淀 `constants.py` |
| 规则 | C3；定义哪些 `rule_id` 触发层 2 |
| 业务/checklist | C4；维护检查点预期与 `assessment` 口径 |
| 报告/UI | C6、C8 |

### M4 — 产品化

- 内网 Web：上传 → 质检 → 下载报告/标注副本  
- 与 IAM/审计日志对接（谁、何时、哪份底稿）  

## 数据安全清单

1. 生产默认 `FA_QC_LLM_ENABLED=false`。  
2. 禁止将案例库/真实底稿提交到 Git 或 Cursor 聊天。  
3. 调用 API 前经 `redact`；日志不落真实编号。  
4. 涉密项目仅配置内网 `BASE_URL`。  
5. 保留「纯规则模式」供监管或离线场景。  

## 技术选型（建议）

| 组件 | 建议 |
| --- | --- |
| HTTP 客户端 | `httpx` 或官方 `openai` SDK（`base_url` 可改） |
| Prompt | 版本化放在 `src/llm/prompts/`，禁止在代码里散落长字符串 |
| 结构化输出 | JSON mode / function calling，解析失败 → `NEED_REVIEW` |
| 开发期 IDE | Cursor 可选；**运行时与 Cursor 无关** |

## 验收标准（M3a）

- `pytest` 全绿，含 `tests/llm/` mock 测试。  
- `fa-qc-run sample.csv --llm on` 在配置 API 后，报告含 `llm_enrichment` 段（可为空）。  
- 未配置 API 时 `--llm on` 明确报错，不静默失败。  
- 文档与 ADR-0002 一致。

## 相关命令

```powershell
# 纯规则（默认，最安全；团队验收基线）
fa-qc-run 底稿.xlsx

# 层 4：报告叙述增强（已实现）
$env:FA_QC_LLM_API_KEY="***"
fa-qc-run 底稿.xlsx --llm on

# 以下 M3c 规划，尚未实现
# fa-qc-run 底稿.xlsx --llm-map
# fa-qc-run 底稿.xlsx --llm-rules
# fa-qc-run 底稿.xlsx --llm-checklist
# fa-qc-run 底稿.xlsx --llm-all
```

配置见 `.env.example`（`FA_QC_LLM_BASE_URL`、`FA_QC_LLM_MODEL` 等）。

---

维护：阶段切换时更新 `docs/handoff/latest.md` 与 `docs/progress.md`。

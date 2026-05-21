# 大模型 Agent 演进路线图

本文描述固定资产质检项目从**规则引擎**演进为**大模型 Agent** 的路径。决策记录见 [decisions/ADR-0002-llm-agent-evolution.md](decisions/ADR-0002-llm-agent-evolution.md)。

## 产品优先级（2026-05-21 确认）

**团队共识**：

1. **最重要**：每一个质检点是否执行准确（`rules` + `ingest` 读对；该 FAIL/WARN/NEED_REVIEW 有据可依）。
2. **LLM 应服务全过程**：ingest 映射、规则语义（`REVIEW` 项）、checklist 满足度——**不是**以报告摘要为主战场。
3. **层 4 报告叙述**（`llm_enrichment` / `--llm`）已实现，但**优先级最低**；不提升「质检点判定」本身，默认建议关闭，待 M3c 层 1–3 落地后再作为可选阅读辅助。

| 优先级 | 工作 | 提升「质检点准确」 |
| --- | --- | --- |
| **P0** | M2a 确定性规则：Lead（`lead_*`）、K.01（`rollforward_*`）、AE-003 等 | **是（核心）** |
| **P0** | ingest 稳定、案例库回归 | **是（前提）** |
| **P1** | M3c 层 2 `--llm-rules`（语义质检点挂 `llm_rationale`） | **辅助语义项** |
| **P1** | M3c 层 3 `--llm-checklist`（逐条检查点评估） | **防漏项** |
| **P2** | M3c 层 1 `--llm-map`（表头映射） | **减少误读** |
| **P3** | 层 4 `--llm` 报告叙述 | **否（可读性）** |

**研发顺序**：先 P0 规则 → 再 C3/C4（llm-rules + checklist）→ C1/C2 → 层 4 维持、不加大投入。

---

## 终态：大模型 Agent 是什么

在本项目中，「大模型 Agent」指：

- **本地/内网运行的编排程序**（`fa-qc-run` 及后续服务），不依赖 Cursor；
- **调用可配置 LLM API**（OpenAI 兼容），在**无法仅靠表格规则判定**的检查点上做语义辅助与 checklist 对照；
- **输出仍为结构化 findings + 质检报告 + 底稿标注**，结论枚举不变；
- **规则引擎始终存在**，作为可信、可回归测试的底座。

不是：把整本 Excel 丢给聊天窗口人工问答；也不是用 LLM 生成一段摘要代替规则跑数。

**LLM 主战场（三层）**：

1. **ingest** — 字段映射 / 表头识别（公司底稿差异大时）
2. **rules** — 对 `REVIEW` / `NEED_REVIEW` 类检查点的语义辅助（拒绝理由、预期、波动说明等）
3. **checklist** — 对照 K1 checklist 判断检查点是否满足、缺何证据

**层 4 report 叙述**（`llm_enrichment`）：可选、低优先级；**不改变** `severity`。

---

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
                                 │  severity 仅由 rules 判定
                                 ▼
                    report（findings 汇总 + 标注副本）
                                 │
                                 ▼
              可选：层 4 叙述（llm_enrichment，默认关）

         各层 LLM 经 src/llm/client.py；脱敏；不传整本 Excel 原文
```

---

## 三层 LLM 分工（M3c 目标，高优先级）

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

### 层 2：质检规则语义（rules）— **产品主战场**

| 项 | 说明 |
| --- | --- |
| **触发** | 规则已产出 `NEED_REVIEW`（或配置的 `rule_id` 白名单） |
| **规划模块** | `src/llm/rule_review.py` |
| **典型场景** | AE-003 拒绝理由；Lead 预期 vs 实际；波动说明充分性；调整汇总闭环；证据充分性 |
| **输入** | 单条/批量 issue（脱敏）+ ingest 结构化摘录（Lead 块、汇总程序、后推合计等） |
| **输出** | 挂到 issue 或报告：`llm_assessment`、`llm_rationale`、`suggested_action` |
| **CLI（规划）** | `--llm-rules`（**建议作为「启用 LLM」时的默认语义**） |

**原则**：`severity` **仅由 `rules` 判定**；LLM 不得将 FAIL 改为 PASS。

**仍仅 rules、不接 LLM**：编号唯一、金额勾稽、非负、必填、超门槛未调查、GAM 区间、Lead↔后推数值勾稽等 `AUTO_FAIL` / `AUTO_WARN`。

### 层 3：Checklist 满足度（checklist）— **产品主战场**

| 项 | 说明 |
| --- | --- |
| **主数据** | `src/rules/registry.py`、`tests/fixtures/rule_dictionary_sanitized.csv`、`docs/qc-checklist.md` |
| **规划模块** | `src/llm/checklist_assess.py` |
| **流程** | 对每个已注册检查点收集结构化证据（ingest + rules findings）→ LLM 对照 checklist 条文 |
| **输出 JSON** | `checklist_assessments[]`：`assessment`（`satisfied` / `not_satisfied` / `insufficient_evidence` / `not_evaluated`）、`rationale`、`missing_evidence[]` |
| **CLI（规划）** | `--llm-checklist` |

**原则**：无结构化证据的检查点标 `not_evaluated`，禁止模型硬判 PASS。

### 层 4：报告叙述（report）— **低优先级，已实现**

| 项 | 说明 |
| --- | --- |
| **模块** | `src/llm/review.py`、`prompts.py`、`workbook_payload.py` |
| **触发** | `--llm` / UI「启用大模型增强」 |
| **作用** | 规则跑完后的执行摘要与 NEED_REVIEW 话术；**不替代**各质检点规则执行 |
| **输出** | `llm_enrichment`（`executive_summary`、`need_review_notes` 等） |
| **状态** | 已实现；**不建议**作为「全流程 LLM」的验收标准 |

### 编排与扩展字段（规划）

| 路径 | 作用 |
| --- | --- |
| `src/llm/orchestrate.py` | 按开关调用层 1–3（优先）与可选层 4 |
| `src/llm/prompts/` | 映射 / 规则 / checklist 分文件 |

`QcIssue` / 报告扩展字段（规划）：

| 字段 | 含义 |
| --- | --- |
| `llm_assessment` | `satisfied` / `not_satisfied` / `insufficient_evidence` |
| `llm_confidence` | 0–1 |
| `llm_rationale` | 短文本，供报告与人工复核 |

---

## 规则 vs 大模型：分工表

| 检查类型 | 示例 | 负责模块 | LLM 层 |
| --- | --- | --- | --- |
| `AUTO_FAIL` / `AUTO_WARN` | 必填、编号唯一、金额勾稽、超门槛未调查 | **`rules` only** | **无** |
| 表头 / 列映射歧义 | 「卡片编码」「使用年限(年)」 | `ingest` + 同义词表 | 层 1 |
| 结构化复杂项 | K.01 列完整性、后推异常金额 | `rules` 优先 | 层 2 可补充说明 |
| `REVIEW` | PSP 拒绝理由、预期/波动说明 | `rules` → severity | **层 2（优先）** |
| Checklist 满足度 | K1 第 N 条 | registry + 证据 | **层 3（优先）** |
| 报告可读性 | 程序维度汇总 | `report` | 层 4（可选，低） |

**总原则**：稳健来自 **rules 判对 + ingest 读对**；LLM 补语义盲区，不推翻 FAIL。

---

## CLI 开关（规划 vs 现状）

| 开关 | 默认 | 优先级 | 状态 |
| --- | --- | --- | --- |
| （无） | — | — | 纯规则 |
| `--llm-rules` | off | **P1** | 待做（M3c C3） |
| `--llm-checklist` | off | **P1** | 待做（M3c C4） |
| `--llm-map` | off | P2 | 待做（M3c C1–C2） |
| `--llm` | off | **P3** | 已实现（层 4） |
| `--llm-all` | — | 演示 | 规划 |

**终态 UI**：默认勾选「规则语义 + Checklist」；「报告叙述」单独可选、默认关。

环境变量 `FA_QC_LLM_ENABLED` 为总闸；细分开关规划为 `FA_QC_LLM_RULES` 等。

---

## 分阶段交付

### M2a（当前，规则 Agent — **准确度主战场**）

- [x] `fa-qc-run` + FA list 规则 + JSON 报告  
- [x] 汇总页（AE-003）、Lead ingest、整本 `run_workbook_qc`  
- [x] Streamlit UI、HTML 人工核对页  
- [ ] **Lead 确定性规则**（`lead_required_fields`、AE-004 子集、GAM、Lead↔K.01 等，见 `docs/planning/lead-qc-rules.md`）  
- [ ] K.01 `rollforward_*` 规则  
- [ ] 字段映射案例库回归（无 LLM）  
- [ ] Excel 报告、底稿批注 `*_qc_annotated.xlsx`  

### M3a — LLM 基础设施（已实现）

| 项 | 说明 |
| --- | --- |
| `src/llm/config.py`、`client.py`、`redact.py` | API、脱敏 |
| `workbook_payload.py` | 整底稿摘录（主要为层 4 服务） |
| `fa-qc-run --llm` | 层 4；**非**全流程语义质检 |
| `tests/llm/` | mock 单测 |

### M3b — 规则层（确定性，优先于 LLM 叙述）

| 任务 | 状态 |
| --- | --- |
| AE-003 `psp_completion` + sheet 匹配 | ✅ |
| Lead AE-001/002 摘录 | ✅ |
| Lead / K.01 **自动 FAIL/WARN 规则** | 待做（**P0**） |

### M3c — 三层 LLM（**产品主战场**）

**目标**：LLM 挂在 ingest / 每条语义质检点 / checklist，而非仅报告末尾。

| 序号 | 任务 | 层 | 优先级 |
| --- | --- | --- | --- |
| C3 | `rule_review.py` + `--llm-rules` | 2 | **P1** |
| C4 | `checklist_assess.py` + `--llm-checklist` | 3 | **P1** |
| C1–C2 | `map_headers.py` + ingest 挂钩 | 1 | P2 |
| C5–C8 | `orchestrate.py`、schema、UI 细分开关 | 编排 | P1 后 |
| C9 | `tests/llm/` 扩充 | 质量 | 持续 |

**实施顺序**：**M2a Lead/K.01 规则（P0）** → C3 → C4 → C6 → C1/C2 → C5/C7/C8；层 4 不阻塞。

任务明细见 `docs/handoff/latest.md` M3c 节。

### M4 — 产品化

- 内网 Web、IAM/审计日志  

---

## 数据安全清单

1. 生产默认不调用 LLM，或仅开 `--llm-rules` / `--llm-checklist`。  
2. 禁止将案例库/真实底稿提交 Git。  
3. API 前 `redact`；日志不落真实编号。  
4. 涉密项目仅内网 `BASE_URL`。  
5. 保留纯规则模式。  

---

## 相关命令

```powershell
# 团队验收基线：纯规则（默认）
fa-qc-run 底稿.xlsx

# 层 4 报告叙述（可选，低优先级；已实现）
# $env:FA_QC_LLM_API_KEY="***"
# fa-qc-run 底稿.xlsx --llm

# M3c 规划（质检点语义 + checklist，高优先级）
# fa-qc-run 底稿.xlsx --llm-rules
# fa-qc-run 底稿.xlsx --llm-checklist
# fa-qc-run 底稿.xlsx --llm-map
```

配置见 `.env.example`。

---

维护：阶段或产品优先级变更时同步 `docs/handoff/latest.md`、`docs/progress.md`、`AGENTS.md`。

# `src/llm/` — 大模型层

## 产品定位（必读）

**质检点判对**由 `src/rules/` + `src/ingest/` 负责（P0）。  
本目录的**主战场**（规划 M3c）：

| 模块（规划） | CLI | 作用 |
| --- | --- | --- |
| `rule_review.py` | `--llm-rules` | 语义类质检点：`llm_rationale` 挂到 issue |
| `checklist_assess.py` | `--llm-checklist` | 对照 K1 checklist 逐条评估 |
| `map_headers.py` | `--llm-map` | 表头映射建议 |

**低优先级（已实现）**：`review.py` + `workbook_payload.py` → `--llm` 层 4 报告叙述（`llm_enrichment`），**不改变** `severity`。

详见 [docs/llm-agent-roadmap.md](../../docs/llm-agent-roadmap.md)。

## 已实现

- `config.py` — `FA_QC_LLM_*` 环境变量
- `client.py` — OpenAI 兼容 chat/completions
- `redact.py` — 脱敏（含 `redact_value_tree`）
- `review.py` — 层 4 增强（可选）
- `workbook_payload.py` — 整底稿结构化摘录（主要为层 4 服务）

## 配置

见项目根目录 `.env.example`。

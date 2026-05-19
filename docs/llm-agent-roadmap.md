# 大模型 Agent 演进路线图

本文描述固定资产质检项目从**规则引擎**演进为**大模型 Agent** 的路径。决策记录见 [decisions/ADR-0002-llm-agent-evolution.md](decisions/ADR-0002-llm-agent-evolution.md)。

## 终态：大模型 Agent 是什么

在本项目中，「大模型 Agent」指：

- **本地/内网运行的编排程序**（`fa-qc-run` 及后续服务），不依赖 Cursor；
- **调用可配置 LLM API**（OpenAI 兼容），对无法仅靠表格规则判断的事项做语义复核；
- **输出仍为结构化 findings + 质检报告 + 底稿标注**，结论枚举不变；
- **规则引擎始终存在**，作为可信、可回归测试的底座。

不是：把整本 Excel 丢给聊天窗口人工问答。

## 目标架构

```text
                    ┌─────────────────────────────────┐
                    │  fa-qc-run（编排 / Agent 入口）    │
                    └───────────────┬─────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
   │   ingest    │          │    rules    │          │  report     │
   │  (本地解析)  │          │ (确定性QC)   │          │ (汇总/标注)  │
   └──────┬──────┘          └──────┬──────┘          └──────▲──────┘
          │                        │                         │
          │                        │  findings               │
          │                        ▼                         │
          │                 ┌─────────────┐                  │
          └────────────────►│  llm/agent  │──────────────────┘
                            │ (API 语义层) │
                            └──────┬──────┘
                                   │
                                   ▼
                            LLM API（可配置）
                            公网 / Azure / 内网网关 / Ollama
```

## 规则 vs 大模型：分工表

| 检查类型 | 示例 | 负责模块 |
| --- | --- | --- |
| `AUTO_FAIL` / `AUTO_WARN` | 必填字段、编号唯一、金额勾稽 | `rules` only |
| 结构化但复杂 | K.01 列完整性、后推异常金额 | `rules` 优先；边界 case 可 LLM 补充说明 |
| `REVIEW` | PSP 拒绝理由是否充分、证据充分性 | `rules` 标 `NEED_REVIEW` → `llm` 给意见 |
| 报告叙述 | 程序维度汇总、给 preparer 的建议 | `llm` 基于 findings 摘要生成 |

**原则**：LLM **不能**单独把 FAIL 改成 PASS；只能补充 `suggestion`、`llm_rationale`，或把 `NEED_REVIEW` 细化为「建议关注项」。

## 分阶段交付

### M2a（当前，规则 Agent）

- [x] `fa-qc-run` + FA list 规则 + JSON 报告  
- [ ] 汇总页、K.01、底稿批注  
- [ ] 整本多 sheet 一次运行  

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
| LLM 专属 PSP 语义判定 | AE-003 | 待加强（M3c） |

### M3c — Agent 编排（Tool Use）

- 定义 tools：`get_sheet_summary`, `list_findings`, `get_checklist_item`  
- LLM 多步调用，减少单次 prompt 体积  
- 审计日志：记录调用了哪些 tool、未传原始底稿全文  

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

## 相关命令（规划）

```powershell
# 纯规则（默认，最安全）
fa-qc-run 底稿.xlsx

# 启用大模型增强
$env:FA_QC_LLM_ENABLED="true"
$env:FA_QC_LLM_BASE_URL="https://your-endpoint/v1"
$env:FA_QC_LLM_API_KEY="***"
fa-qc-run 底稿.xlsx --llm on
```

---

维护：阶段切换时更新 `docs/handoff/latest.md` 与 `docs/progress.md`。

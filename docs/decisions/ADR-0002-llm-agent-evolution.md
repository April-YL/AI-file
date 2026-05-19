# ADR-0002：演进为大模型 Agent（混合架构）

## 状态

已采纳（规划）。

## 背景

项目终态是模拟质检人员复核固定资产底稿。当前 M1/M2a 以**确定性规则引擎**为主（`ingest` → `rules` → `report`），适合 `AUTO_FAIL` / `AUTO_WARN`。

大量检查点（PSP 执行充分性、证据完整性、CRA/Canvas 一致性等）在 `docs/qc-checklist.md` 中标记为 `REVIEW`，需要审计判断。团队明确：**后续需开发为大模型 Agent**，通过可配置的 **LLM API** 完成语义复核，而非依赖 Cursor 等 IDE 内置 Agent。

同时须满足数据安全：程序本地运行、密钥不进 Git、外传数据最小化，支持内网/私有化 OpenAI 兼容端点。

## 决策

采用 **「规则引擎 + 大模型 Agent」混合架构**，分阶段演进：

1. **规则层（长期保留）**  
   所有可结构化、可单测的检查必须由 `src/rules/` 产出 findings；结论枚举仍为 `PASS` / `WARN` / `FAIL` / `NEED_REVIEW`。

2. **大模型层（M3 起）**  
   新增 `src/llm/`（或 `src/agent/`），通过 **OpenAI 兼容 HTTP API** 调用模型；**不**绑定 Cursor、不绑定单一云厂商。

3. **编排层**  
   `fa-qc-run` 扩展为流水线编排器：先跑规则 → 再按需调用 LLM 增强 `NEED_REVIEW` / `REVIEW` 类检查点 → 合并进报告。

4. **默认安全**  
   - `FA_QC_LLM_ENABLED` 默认 `false`（与现网行为一致）。  
   - 禁止默认上传整本底稿；仅传规则 findings 摘要 + 经脱敏的局部上下文。  
   - API Key 仅来自环境变量或本地配置，不入库。

5. **部署形态**  
   - 独立本地 CLI / 内网服务（见 ADR-0001 不引入 DB 的约束在 M3 仍适用）。  
   - Cursor 仅作开发工具，**不是**生产运行时。

## 非目标（M3 之前不做）

- 用 LLM 替代金额勾稽、唯一性等确定性规则。  
- 将真实底稿默认发往公网 API。  
- 在 M2a 未完成前阻塞汇总/K.01 规则与底稿标注。

## 分阶段路线图

| 阶段 | 目标 | 交付 |
| --- | --- | --- |
| **M2a（当前）** | 整底稿流水线 + 规则为主 | `fa-qc-run`、汇总/K.01 规则、批注副本 |
| **M3a** | LLM 基础设施 | `src/llm/`、配置、脱敏、mock 单测、`--llm on/off` |
| **M3b** | 语义复核 | AE-003 PSP/拒绝理由、NEED_REVIEW 项复核建议 |
| **M3c** | Agent 编排 | 多步 tool calling：查 sheet 摘要 → 对照 checklist → 写报告段落 |
| **M4** | 产品化 | 内网 Web UI / API；可选仅内网模型 |

## 模块边界（规划）

```text
src/ingest/     # 不变：解析与映射
src/rules/      # 不变：确定性 findings
src/llm/        # 新增：API 客户端、prompt、脱敏、review 任务
src/agent/      # 可选：编排（plan → tools → merge），调用 rules + llm
src/report/     # 扩展：合并 llm_notes、agent_summary
```

## 配置约定（规划）

| 变量 | 含义 |
| --- | --- |
| `FA_QC_LLM_ENABLED` | 是否调用 LLM，默认 `false` |
| `FA_QC_LLM_BASE_URL` | OpenAI 兼容根 URL（含私有化/Ollama） |
| `FA_QC_LLM_API_KEY` | API 密钥 |
| `FA_QC_LLM_MODEL` | 模型 ID |
| `FA_QC_LLM_MAX_TOKENS` | 单次上限（可选） |

## 影响

- `docs/architecture.md` 增加目标数据流与 M3 模块说明。  
- `AGENTS.md` 增加大模型 Agent 终态描述。  
- `pyproject.toml` 将增加 optional dependency `llm`（`httpx` / `openai`）。  
- 规则单测保持无网络；LLM 单测使用 mock。

## 相关文档

- [architecture.md](../architecture.md)
- [qc-checklist.md](../qc-checklist.md) — `REVIEW` 项为 LLM 主要候选
- [rule-dictionary-mapping.md](../rule-dictionary-mapping.md)

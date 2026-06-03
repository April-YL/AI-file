# K.00 调整汇总表 — LLM 复核设计（M3c）

> **状态**：设计已定稿；实现骨架见 `src/llm/lead_adjustment_review.py`、`src/ingest/lead_adjustment_grid.py`。  
> **关联**：`docs/planning/lead-qc-rules.md` 模块 6、字典 MT-003、`lead_adjustment_internal_consistency`（LEAD-017）。

## 1. 背景与约束

| 约束 | 说明 |
| --- | --- |
| 版式差异大 | 中英文表头、单列带符号 vs 借贷两列、合并单元格；**不宜**用固定列规则覆盖全案例库 |
| 金额方向 | 借正贷负、或与引导表符号相反但绝对值一致；**仅比绝对值会误报** |
| 跨科目 | 调整可能记在费用、往来等科目，对 PPE 为**间接影响**；不能与引导表「原值/累计折旧」逐行硬对 |
| SOP【04】 | 须原因、过程、Refer A5/程序；其他科目调整仅索引、未写清对 PPE 影响为易错点 |
| 产品优先级 | P0=rules+ingest；本能力=P1 **层 2 语义**（`--llm-rules`）；**不**用 LLM 将 FAIL 改为 PASS |

**原则**：调整汇总表质检 = **摘录 + 分档检查清单 + 高置信 direct 金额勾稽**；默认 **`NEED_REVIEW`**，跨科目 **flag_not_fail**。

---

## 2. 目标与非目标

### 目标

1. 从调整汇总块 **grid** 识别版式（layout）与行级字段（含 `signed_amount`、`ppe_impact`）。
2. 对 **direct** PPE 行，在符号口径明确时与引导主表 `book_adjustment` / `audit_adjustment` 比对。
3. 对 **indirect** 行，检查叙述与索引闭环（MT-003），输出可操作的 `cross_account_flags`。
4. 与 LEAD-017 协同：低置信版式时 **不** 强化合计 FAIL/WARN。

### 非目标（M3c 本阶段不做）

- 全 TB / A3A5 科目映射与自动 FAIL
- 替代 `lead_adjustment_internal_consistency` 的确定性合计（仅加 **门控**）
- 三 pass 全部强制上线（默认 **单 pass 合并**，见 §5）

---

## 3. 架构

```text
LeadBlock(adjustment_summary) + grid 摘录
        │
        ├─► [可选] LEAD-017 合计勾稽（仅 layout_confidence≥medium 且 direct 行占主导时）
        │
        └─► lead_adjustment_llm_review（本设计）
                 │
                 ├─ Pass A: layout（表头、单列/双列、符号约定）
                 ├─ Pass B: row_extract（类型、编号、科目、signed_amount、ppe_impact）
                 └─ Pass C: adequacy（direct 比对 + indirect 闭环 + cross_account_flags）
                        │
                        ▼
                 QcIssue(s)  severity 仅 WARN / NEED_REVIEW
                 rule_id: lead_adjustment_layout_review | lead_adjustment_semantic
```

### 规则 ID

| rule_id | dict_code | 自动化 | 默认 severity | 说明 |
| --- | --- | --- | --- | --- |
| `lead_adjustment_layout_review` | LEAD-018 | REVIEW | NEED_REVIEW | 版式未知或 confidence=low |
| `lead_adjustment_semantic` | LEAD-019 | REVIEW | WARN / NEED_REVIEW | MT-003 恰当性、跨科目、direct 金额不一致 |
| `lead_adjustment_internal_consistency` | LEAD-017 | AUTO_WARN | WARN | 保留；受 `should_run_strict_total_check()` 门控 |

---

## 4. 数据模型（LLM JSON）

### 4.1 Layout（Pass A）

```json
{
  "amount_layout": "single_signed_column | debit_credit_two_columns | unknown",
  "sign_convention": "debit_positive_credit_negative | credit_positive_debit_negative | absolute_only | unknown",
  "columns": [{"role": "adjustment_type", "source_header": "调整类型", "col_index": 1}],
  "confidence": "high | medium | low",
  "layout_notes": ""
}
```

### 4.2 行抽取（Pass B）

```json
{
  "rows": [{
    "source_row": 68,
    "adjustment_category": "未更正审计调整 | 已更正审计调整 | 管理层账表调整 | 无调整说明 | unknown",
    "adjustment_ref": "AA2",
    "account_label": "原值",
    "signed_amount": "500000",
    "amount_basis": "Dr 500000 Cr 0",
    "ppe_impact": "direct | indirect | unclear",
    "linked_ppe_accounts": ["原值"],
    "evidence_refs": ["A5-1"],
    "description": "",
    "confidence": "high | medium | low"
  }]
}
```

**`ppe_impact` 判定**（写入 system prompt）：

- **direct**：科目 ∈ `PPE_DIRECT_ACCOUNT_ALIASES`（原值、累计折旧、减值、净值及中英文别名）
- **indirect**：非 PPE 科目，但文本/索引表明影响固定资产
- **unclear**：无法判断

### 4.3 复核结论（Pass C）

```json
{
  "assessment": "sufficient | insufficient | unclear",
  "layout_confidence": "high",
  "direct_amount_checks": [{
    "account_label": "原值",
    "guidance_role": "audit_adjustment",
    "summary_signed": "500000",
    "guidance_signed": "-500000",
    "match": true,
    "match_reason": "符号口径相反，绝对值一致"
  }],
  "cross_account_flags": [{
    "adjustment_ref": "AA3",
    "issue": "indirect_adjustment_without_ppe_link_narrative",
    "source_rows": [70]
  }],
  "rationale": "",
  "suggested_action": ""
}
```

**severity 映射**（代码侧，非 LLM）：

| assessment | 条件 | severity |
| --- | --- | --- |
| insufficient | 存在 direct mismatch 或声明无调整但有金额 | WARN |
| insufficient | 仅 indirect 叙述不足 | NEED_REVIEW |
| unclear | layout/行 confidence 低 | NEED_REVIEW |
| sufficient | — | 不产出 issue |

---

## 5. LLM 调用策略

| 模式 | 环境变量 | 说明 |
| --- | --- | --- |
| **合并（默认）** | `FA_QC_LLM_ADJUSTMENT_PASSES=1` | 一次调用输出 layout + rows + assessment |
| **分步** | `FA_QC_LLM_ADJUSTMENT_PASSES=3` | A→B→C 三次调用，成本高、可调试 |

触发条件（`should_review_adjustments(lead)`）：

- 存在 `LeadBlockKind.ADJUSTMENT_SUMMARY` 且（`adjustment_rows` 非空 **或** grid 非空）
- 或引导主表 `book_adjustment` / `audit_adjustment` 任一非零

无调整块且无调整列 → 跳过。

---

## 6. Payload 输入（`build_adjustment_review_payload`）

```json
{
  "source_sheet": "K.00 Lead Sheet",
  "adjustment_block": {"anchor_row": 64, "start_row": 64, "end_row": 85, "anchor_text": "..."},
  "adjustment_grid": [["调整类型", "..."], ["审计调整", "..."]],
  "ingest_adjustment_rows": [{"adjustment_type": "...", "raw_cells": [], "source_row": 66}],
  "guidance_adjustments": [{
    "account_label": "原值",
    "book_adjustment": null,
    "audit_adjustment": "500000",
    "source_row": 49
  }],
  "guidance_sign_hint": "引导表列：账表调整→book_adjustment；审计调整→audit_adjustment；正数含义以底稿列标题为准",
  "ppe_direct_aliases": ["原值", "累计折旧", "..."],
  "deterministic_hints": [{"rule_id": "lead_adjustment_internal_consistency", "severity": "WARN", "message": "..."}],
  "cross_account_policy": "flag_not_fail",
  "workbook_context": {}
}
```

`adjustment_grid`：块内最多 **35 行 × 14 列**，单元格转字符串（与 ingest 一致）。

---

## 7. LEAD-017 门控

函数 `should_run_strict_total_check(lead, layout_result?)`：

| 条件 | 严格合计检查 |
| --- | --- |
| 无 adjustment 块 | 否 |
| layout `confidence=low` 或 `amount_layout=unknown` | 否 |
| 抽取行中存在 `ppe_impact=indirect` 且不存在 `direct` | 否 |
| 否则 | 是（保持现有 WARN/NEED_REVIEW 逻辑） |

门控未满足时 LEAD-017 **不运行合计比对**；可由 LEAD-019 提示「版式/跨科目，请人工勾稽」。

---

## 8. 模块与文件

| 路径 | 职责 |
| --- | --- |
| `src/ingest/lead_adjustment_grid.py` | 从 workbook 读取 Lead 行并生成 `adjustment_grid` |
| `src/llm/lead_adjustment_review.py` | prompts、payload、issue 构建、流水线入口 |
| `src/rules/lead_adjustment_gating.py` | LEAD-017 门控（纯函数，可单测） |
| `tests/llm/test_lead_adjustment_payload.py` | payload / 门控单测（无 API） |
| `tests/fixtures/` | 后续：脱敏「双列英文」「跨科目 AA#」样例 |

流水线：`report/pipeline.py` 在 `build_lead_semantic_issues` 之后调用 `build_lead_adjustment_issues`。

---

## 9. 验收标准

1. `pytest tests/llm/test_lead_adjustment_payload.py -q` 通过。
2. 无 LLM API 时：有调整块但不调 API → 不报错、无 adjustment LLM issues。
3. 启用 LLM + fixture grid：payload 含 `guidance_adjustments` 与 `ppe_direct_aliases`。
4. 文档：`lead-qc-rules.md` 模块 6 指向本文；registry LEAD-018/019 为 IMPLEMENTED（语义）或 PLANNED（分 pass）。

---

## 10. 迭代路线

| 阶段 | 内容 |
| --- | --- |
| **M3c-a（当前）** | 设计文档 + grid 摘录 + 合并 pass + pipeline 挂钩 + 门控 |
| **M3c-b** | 脱敏 fixture 回归；`FA_QC_LLM_ADJUSTMENT_PASSES=3` |
| **M3c-c** | `lead_sheet_report` 展示 `adjustment_llm_excerpt`；checklist MT-003 挂层 3 |

---

## 11. 参考

- SOP K1.00【04】：`artifacts/_k00_sop_guidance.txt`（其他科目调整易错点）
- 既有语义：`src/llm/lead_review.py`（预期/波动）
- 路线图：`docs/llm-agent-roadmap.md` 层 2

# K.01 LLM Ingest Review Profile

> 状态：程序级设计稿，作为 `LLM ingest review` 的首个程序级增强 profile。项目级识别层应覆盖所有核心程序 sheet，K.01 profile 只补充 K.01 的专属锚点、区块和错分风险。  
> 关联项目级框架：[llm-ingest-review-framework.md](./llm-ingest-review-framework.md)。  
> 关联 K.01 文档：[k01-qc-rules.md](./k01-qc-rules.md)、[k01-six-block-qc-matrix.md](./k01-six-block-qc-matrix.md)、[k01-workpaper-layouts.md](./k01-workpaper-layouts.md)。  
> 目标：定义 K.01 后推表在 LLM ingest 兜底中“什么才像读对、什么才像漏读或错读”，供后续 Python 最小实现和案例回归使用。

---

## 一、适用范围与边界

本 profile 只服务于 **K.01 Agree SL to GL / 后推明细表** 的读取层复核，不直接判断底稿编制是否正确。

LLM 可以辅助判断：

- K.01 sheet 是否可能漏读。
- K.01 六区块是否可能漏识别或边界错位。
- TB check、表3 check、表4差异是否可能错分专题。
- Notes 是否可能漏读或归属错专题。
- 字段 / 金额锚点是否可能取错区域。

LLM 不得判断：

- 金额是否勾稽一致。
- 差异是否超过 SAD / TE。
- 表3 check 是否应 PASS。
- TB 差异是否应 FAIL。
- 规则 `FAIL/WARN/NEED_REVIEW/PASS` 是否应被修改。

一句话边界：

> K.01 LLM ingest review 只提示“读数层风险”，不输出 K.01 质检结论。

---

## 二、K.01 核心对象

K.01 的 LLM ingest review 围绕六个物理区块展开。

| 区块 ID | 名称 | 业务作用 | 当前 coding 字段 |
| --- | --- | --- | --- |
| `b1_bkd_main_table` | 表1 BKD 主矩阵 | 后推主表，按类别与交易行填列原值、累折、减值、净值 | `section_presence`、`section_regions`、`amount_column_bindings`、`opening_totals`、`ending_totals` |
| `b2_movement_tb_reconciliation` | 变动 / TB / 差异区 | 与 TB / 试算表核对，读取差异 | `tb_reconciliation_detected`、`tb_reconciliation_confidence`、`tb_difference_values` |
| `b3_table2_fa_summary` | 表2 FA list 分类汇总 | FA list 分类汇总，辅助表3 | `table2_*`、表2锚点 |
| `b4_table3_check_with_table1` | 表3 表2↔表1 check | GL-002 主检查来源 | `table3_check_values`、`table3_notes_text` |
| `b5_table4_depreciation_pl` | 表4 折旧费用与利润表核对 | GL-004 主检查来源 | `table4_pl_total`、`table4_difference`、`table4_notes_text` |
| `b6_notes_investigation_routing` | Notes / SAD / TE / 程序路由 | 差异调查与 K.02/K.03 路由 | `notes`、`tb_notes_text`、`table3_notes_text`、`table4_notes_text` |

---

## 三、K.01 版式 profile 与识别重点

K.01 可能出现多种合法版式。LLM 不应把非标准版式直接判异常，应判断是否存在具体读取风险。

| Layout Profile | 特征 | LLM 关注点 |
| --- | --- | --- |
| `sop_bkd_matrix` | 标准 SOP 表1矩阵，另有表2、表3、表4 | 六区块是否齐全；表3/表4/Notes 是否错专题 |
| `hybrid` | 上部变动/TB区 + 下部类别两期对比，案例库 B–G 常见 | 表1、TB、表2/表3位置可能并排或分段；防止重复加总和错分表4 |
| `category_dual_period` | 类别两期对比为主，TB 区可能弱 | 不能因缺完整 SOP 矩阵就直接判 suspicious |
| `unrecognized` | 锚点不足或仅有说明文字 | 可触发 LLM 漏读发现或人工复核提示 |

---

## 四、关键锚点与证据强弱

### 4.1 区块锚点

| 区块 | 强锚点 | 中等锚点 | 弱锚点 / 注意事项 |
| --- | --- | --- | --- |
| 表1 BKD | `表1` + `固定资产类别`；或 `固定资产类别` + `年初余额` + `年末余额` | `账面数`、`审定数`、`购置`、`处置`、`计提折旧` | 单独出现“固定资产”不够 |
| 变动/TB | `TB-原值`、`TB-累计折旧`、`试算表` + `差异` | `原值变动金额`、`累计折旧变动金额` | 只有“变动金额”不应认定可靠 TB check |
| 表2 | `表2` + `固定资产清单` / `分类汇总` | `FA list`、`SUMIF`、分类汇总金额 | 仅有“固定资产清单”可能是普通 FA list |
| 表3 | `表3`；`表2 check with 表1` | `check with` + `差异` | 表3常与表2并排，不能只按行号固定 |
| 表4 | `表4`；`折旧费用与利润表科目核对` | `利润表金额`、`折旧费用` | 不得把表4差异用于 TB check |
| Notes | `Notes` + 差异主题附近说明 | `SAD`、`TE`、`调查`、`拒绝执行原因` | Notes 必须归属对应专题，不能跨专题混用 |

### 4.2 强证据标准

可判断为 K.01 读取风险 `suspicious` 的强证据通常需要同时满足：

- 目标对象缺失或低置信度。
- 候选 preview 中出现明确锚点。
- 锚点所在行号可引用。
- 锚点与目标对象的业务语义一致。

示例：

```text
coding_result.missing_sections 包含 b4_table3_check_with_table1。
candidate_previews 第45行出现“表2 check with 表1”“差异”“Notes”。
→ 强证据：疑似漏读表3。
```

### 4.3 中证据标准

中证据通常只应输出 `NEED_REVIEW` 或建议人工核对，不建议自动二次强读：

- 名称像 K.01，但 preview 锚点不完整。
- 有 `check with` 但未见 `表2`、`表1` 或差异列。
- 有 `Notes`，但无法判断属于 TB、表3还是表4。

### 4.4 弱证据标准

弱证据不得直接判 `suspicious`：

- 只有“固定资产”或“资产类别”等泛词。
- 只有 sheet 名像 K.01，但内容没有后推结构。
- 只有一个“差异”词，没有 TB / 表3 / 表4上下文。

---

## 五、触发 LLM 的 K.01 场景

### 5.1 Sheet 级触发

| 触发 | 说明 | LLM 任务 |
| --- | --- | --- |
| `rollforward is None` |    | `missing_object_discovery` |
| 多个 K.01 候选 | 例如 `K.01` 与 `K.01-24` 并存 | `sheet_classification` / 多期路由复核 |
| sheet 名与内容冲突 | 名称像 K.01，但内容像清单或说明页 | `read_result_review` |

### 5.2 区块级触发

| 触发 | 说明 | LLM 任务 |
| --- | --- | --- |
| `recognition_confidence < 0.65` | K.01 整页识别低置信度 | `read_result_review` |
| `section_conflicts` 非空 | 锚点重复、表头越界、区块顺序异常 | `section_boundary_review` |
| 表3缺失但 preview 有 `表2 check with 表1` | 疑似漏读表3 | `missing_object_discovery` |
| 表4缺失但 preview 有 `折旧费用与利润表` | 疑似漏读表4 | `missing_object_discovery` |
| TB check 低置信度 | 有 TB 或差异之一，但证据不完整 | `amount_anchor_review` |

### 5.3 Notes 级触发

| 触发 | 说明 | LLM 任务 |
| --- | --- | --- |
| TB 差异有 Notes，但 Notes 来源靠近表4 | 可能错专题 | `notes_location_review` |
| 表3差异有 Notes，但 notes_text 来源不在表3区域 | 可能错用其他 Notes | `notes_location_review` |
| 表4差异有 Notes，但内容像 TB/表3说明 | 可能专题混用 | `notes_location_review` |

---

## 六、常见漏读、错读、错分场景

| 场景 | 风险 | LLM 判断重点 |
| --- | --- | --- |
| K.01 sheet 名称变体 | 整页漏读 | sheet 名和 preview 是否出现后推锚点 |
| 表2/表3 横向并排 | 表3漏读或表2表3混淆 | 同行或相邻行是否同时出现 `表2`、`表3`、`check with` |
| TB 区与表4相邻 | 表4差异被当 TB 差异 | `折旧费用与利润表` 锚点是否在差异附近 |
| Notes 区较远 | Notes 未读或归属错 | Notes 行是否位于对应区块附近 |
| 多期 sheet | 读到上年 K.01 | sheet 名后缀、当期优先、汇总页引用 |
| 说明文字含“差异” | 错把说明区当金额差异 | 是否有 TB/表3/表4上下文和数值 |
| 仅有变动金额 | 错认 TB check | 是否同时有 TB / 试算表口径和差异标签 |

---

## 七、Notes 归属判断

K.01 Notes 是最容易错专题的区域。LLM 可以判断 Notes 是否可能归属错，但不能判断金额本身。

### 7.1 专题隔离原则

| 专题 | 可使用的 Notes | 不可使用的 Notes |
| --- | --- | --- |
| TB check | TB/试算表核对区附近 Notes | 表3 Notes、表4折旧 Notes |
| 表3 check | 表3 check with 表1 附近 Notes | TB Notes、表4 Notes |
| 表4 折旧核对 | 表4折旧费用与利润表核对附近 Notes | TB Notes、表3 Notes |

### 7.2 LLM 应提示的风险

- Notes 文本内容明显讲折旧费用，却被 coding 用于 TB check。
- Notes 行号远离对应差异区，且更靠近其他专题。
- Notes 仅写“见 NB”但 preview 中无法判断 NB 对应哪个专题。
- 表3差异与表4差异均存在，但 coding 只读到一段 Notes。

### 7.3 LLM 不应提示的情况

- Notes 虽然简短，但明确位于对应专题附近；充分性应由 `rollforward_notes_review` 或人工复核判断。
- 无 material 差异，Notes 归属不影响规则。
- coding 已有确定性规则明确报“无 Notes”，LLM 不应编造周边说明。

---

## 八、二次 deterministic ingest 采纳条件

LLM 只能建议候选，是否采纳由 coding 二次读取决定。

### 8.1 可触发二次读取的情况

| 情况 | 条件 |
| --- | --- |
| 漏读 K.01 sheet | 候选 sheet 名或 preview 中出现多个 K.01 强锚点 |
| 漏读表3 | preview 中出现 `表2 check with 表1` 或 `表3` + `差异` |
| 漏读表4 | preview 中出现 `折旧费用与利润表` 或 `表4` + 折旧差异 |
| 错分 TB / 表4 | 差异行附近同时出现 TB 与表4锚点，需按区块重切 |

### 8.2 不应自动二次读取的情况

- 只有弱词命中。
- candidate row 不在输入 preview 中。
- LLM 无法引用具体行号。
- LLM 输出的 candidate sheet 不在输入候选列表。
- LLM 试图提供金额结论或改规则 severity。

---

## 九、不应报警的正常场景

为避免 LLM 过度保守，以下场景不应自动生成 `suspicious`：

| 场景 | 原因 |
| --- | --- |
| `category_dual_period` / `hybrid` 缺完整 SOP 矩阵 | 案例库常见合法简表，不能直接判异常 |
| 表2/表3并排但 coding 已读到 table3_check_values | 已读到核心 check，不重复提示 |
| TB check 未识别，但 sheet 本身没有 TB/试算表锚点 | 不是漏读，可能底稿无该模块或另册 |
| Notes 不充分 | 属语义质检 `rollforward_notes_review`，不是 ingest 读取风险 |
| 金额差异大 | 属 rules 判断，不是 LLM ingest review 判断 |
| 表4分摊合理性 | 属审计判断 / LLM rules，不是读取层判断 |

---

## 十、K.01 项目级 Prompt 补充语句

项目级 system prompt 不重复写 K.01 细节；K.01 profile 可在 user prompt 的 `program_profile_hint` 中补充：

```text
K.01 后推表通常包含六个物理区块：
1) 表1 BKD 主矩阵；
2) 变动 / TB / 差异区；
3) 表2 FA list 分类汇总；
4) 表3 表2 check with 表1；
5) 表4 折旧费用与利润表核对；
6) Notes / SAD / TE / 程序路由。

请特别注意：
- 表3 check、TB check、表4折旧核对是不同专题，Notes 不得混用。
- 仅有“变动金额”不等于可靠 TB check；可靠 TB check 通常需要 TB/试算表口径和“差异”标签同时出现。
- 表4折旧费用与利润表核对的差异不得被当作 TB 差异。
- hybrid / category_dual_period 是案例库常见合法版式，不得仅因不符合 SOP 标准矩阵而判 suspicious。
- 如果发现疑似漏读，只提出候选 sheet、候选行、锚点证据和建议动作，不计算金额、不判断是否超过 SAD。
```

---

## 十一、输入 payload 示例

### 11.1 表3漏读发现

```json
{
  "review_target": "K.01 表3 check with 表1 漏读发现",
  "review_type": "missing_object_discovery",
  "program_profile_hint": "K.01 后推表含表1、TB区、表2、表3、表4、Notes；表3 check 与 TB check、表4差异不得混用。",
  "coding_result": {
    "classified_sheet": "K.01 Agree SL to GL",
    "recognized_sections": ["b1_bkd_main_table", "b2_movement_tb_reconciliation", "b5_table4_depreciation_pl"],
    "missing_sections": ["b4_table3_check_with_table1"],
    "recognition_confidence": 0.58,
    "conflicts": ["duplicate_anchor:b4_table3_check_with_table1"],
    "notes": ["k01_recognition_needs_review"]
  },
  "expected_object": {
    "procedure": "K.01",
    "object_type": "module",
    "object_name": "b4_table3_check_with_table1",
    "why_expected": "K.01 后推表通常包含表3，用于表2 FA list 汇总与表1核对。"
  },
  "candidate_previews": [
    {
      "sheet_name": "K.01 Agree SL to GL",
      "preview_lines": [
        {"row": 38, "text": "表2 固定资产清单分类汇总"},
        {"row": 45, "text": "表2 check with 表1 差异 Notes"},
        {"row": 82, "text": "表4 折旧费用与利润表科目核对 差异"}
      ],
      "anchor_hits": [
        {"row": 45, "anchors": ["表2 check with 表1", "差异"]},
        {"row": 82, "anchors": ["表4", "折旧费用与利润表"]}
      ]
    }
  ],
  "question": "请判断 coding 是否可能漏识别 K.01 表3。"
}
```

### 11.2 TB / 表4错专题复核

```json
{
  "review_target": "K.01 TB check 与表4折旧核对错专题复核",
  "review_type": "notes_location_review",
  "program_profile_hint": "TB check、表3 check、表4折旧核对是不同专题，Notes 不得混用。",
  "coding_result": {
    "classified_sheet": "K.01 Agree SL to GL",
    "recognized_sections": ["b2_movement_tb_reconciliation", "b5_table4_depreciation_pl", "b6_notes_investigation_routing"],
    "tb_notes_row": 85,
    "table4_difference_row": 83,
    "tb_reconciliation_confidence": 0.62,
    "conflicts": ["tb_check_needs_review:0.62"]
  },
  "expected_object": {
    "procedure": "K.01",
    "object_type": "notes",
    "object_name": "tb_notes_text",
    "why_expected": "TB 差异超过 SAD 时需对应专题 Notes。"
  },
  "candidate_previews": [
    {
      "sheet_name": "K.01 Agree SL to GL",
      "preview_lines": [
        {"row": 42, "text": "TB-原值 差异"},
        {"row": 83, "text": "表4 折旧费用与利润表科目核对 差异"},
        {"row": 85, "text": "Notes：折旧费用差异系利润表科目分类导致"}
      ],
      "anchor_hits": [
        {"row": 42, "anchors": ["TB-原值", "差异"]},
        {"row": 83, "anchors": ["表4", "折旧费用与利润表"]},
        {"row": 85, "anchors": ["Notes"]}
      ]
    }
  ],
  "question": "请判断 coding 是否可能把表4 Notes 错用于 TB check。"
}
```

---

## 十二、期望输出示例

### 12.1 表3漏读

```json
{
  "assessment": "suspicious",
  "risk_level": "high",
  "risk_area": "missing_module",
  "suspected_object": "b4_table3_check_with_table1",
  "candidate_sheet": "K.01 Agree SL to GL",
  "candidate_rows": [45],
  "evidence_anchors": ["表2 check with 表1", "差异"],
  "rationale": "coding_result 显示表3缺失，但候选预览第45行出现“表2 check with 表1”和“差异”，符合 K.01 表3核对区特征；第82行为表4，不应与表3混用。",
  "suggested_action": "建议对第45行附近重新执行 K.01 表3 deterministic ingest，并人工确认表3差异及对应 Notes。",
  "should_retry_deterministic_ingest": true,
  "manual_review_focus": "打开 K.01 第45行附近，确认是否为表3 check with 表1。"
}
```

### 12.2 表4 Notes 错用于 TB

```json
{
  "assessment": "suspicious",
  "risk_level": "medium",
  "risk_area": "notes_location",
  "suspected_object": "tb_notes_text",
  "candidate_sheet": "K.01 Agree SL to GL",
  "candidate_rows": [83, 85],
  "evidence_anchors": ["表4", "折旧费用与利润表", "Notes"],
  "rationale": "coding_result 将第85行作为 TB Notes，但候选预览显示第83行是表4折旧费用与利润表核对，第85行 Notes 文本也在说明折旧费用差异，可能不应作为 TB 差异说明。",
  "suggested_action": "建议人工核对 TB 差异是否另有 Notes；若无，应避免用表4 Notes 解释 TB check。",
  "should_retry_deterministic_ingest": false,
  "manual_review_focus": "区分第42行 TB 差异与第83行表4折旧差异，确认各自 Notes 归属。"
}
```

### 12.3 正常不报警

```json
{
  "assessment": "likely_ok",
  "risk_level": "low",
  "risk_area": "section_boundary",
  "suspected_object": "",
  "candidate_sheet": "K.01 Agree SL to GL",
  "candidate_rows": [],
  "evidence_anchors": [],
  "rationale": "coding_result 已识别表1、TB区、表2、表3、表4和Notes，且候选预览未显示区块错位或专题混用证据。",
  "suggested_action": "",
  "should_retry_deterministic_ingest": false,
  "manual_review_focus": ""
}
```

---

## 十三、回归用例清单

后续实现 K.01 LLM ingest review 前，建议至少准备以下 mock payload 回归：

| 用例 | 期望 |
| --- | --- |
| 表3缺失但 preview 有 `表2 check with 表1` | `suspicious`，建议二次 ingest |
| 表4差异被当 TB Notes | `suspicious`，风险区 `notes_location` |
| 只有“差异”单词，无 TB/表3/表4上下文 | `unclear`，不得 `suspicious` |
| hybrid 版式 6/6 区块已识别 | `likely_ok` |
| 未识别 K.01 sheet，但候选 sheet 有多个后推锚点 | `suspicious`，候选 sheet 有效 |
| 候选 sheet 只名称像 K.01，内容无后推锚点 | `unclear` 或 `not_found` |
| LLM 输出不存在于候选列表的 sheet | coding 丢弃 |
| LLM 输出输入中没有的行号 | coding 丢弃 |

---

## 十四、后续 Python 最小试点建议

在项目级 LLM ingest review 已覆盖核心程序 sheet 的基础上，本 profile 用于增强 K.01 专项识别：

1. 新增 `src/llm/ingest_review.py` 项目级通用模块。
2. K.01 profile 增强以下专项触发：
   - `rollforward is None`
   - `recognition_confidence < 0.65`
   - `section_conflicts` 非空
   - 表3 / 表4缺失但候选 preview 有强锚点
3. 输出先只进入 report 的“读取结果复核提示”，不影响 `run_rollforward_rules`。
4. 使用 mock LLM 单测，不真实调用 API。
5. 案例库复测时重点看是否减少漏读、错专题，而不是增加噪音。

---

## 十五、阶段验收标准

本 profile 完成后，应满足：

- 能说明 K.01 六区块哪些属于 LLM ingest review 的复核对象。
- 能区分表3、TB check、表4、Notes 的专题边界。
- 能定义强 / 中 / 弱证据。
- 能说明哪些情况触发二次 deterministic ingest。
- 能说明哪些情况不应报警。
- 能提供 payload 与输出示例，供后续 Python mock 测试使用。


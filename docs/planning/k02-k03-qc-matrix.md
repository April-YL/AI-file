# K.02 / K.03 — 质检覆盖矩阵（规划）

> **状态**：**M2b+ 起步**；K.02 程序包完整性、新增清单字段完整性与新增方式同质性提示已接入。  
> **Checklist 来源**：[qc-checklist.md](../qc-checklist.md) §五–§九  
> **索引**：[program-qc-coverage-index.md](./program-qc-coverage-index.md)

---

## K.02 新增与处置

### 工作表 / 输入

|  sheet / 数据 | 说明 |
| --- | --- |
| `K.02.1 新增测试` | 详细测试底稿 |
| `K.02.1a 新增选样输出` | 新增测试抽样/选样输出结果 |
| `新增清单` | 当期新增资产 |
| `K.02.2 处置测试` | 处置/报废测试 |
| `K.02.2a 处置选样输出` | 处置测试抽样/选样输出结果 |
| `处置清单` | 当期处置资产 |

### 逻辑模块（建议）

| 模块 | 内容 | ingest 规划 | 规则规划 |
| --- | --- | --- | --- |
| **K2-A 新增清单** | 字段完整、与后推购置勾稽 | `addition_list` ingest ✅，已保留 `addition_method` | `addition_required_fields` ✅；后推勾稽待做 |
| **K2-B 处置清单** | 字段完整、与后推处置勾稽 | `disposal_list` ingest ✅ 部分 | `disposal_required_fields` 等 |
| **K2-C 交叉 K.01** | 清单合计 vs 后推变动行 | ⏳ | `addition_rollforward_reconciliation`、`disposal_rollforward_reconciliation` |
| **K2-D 样本/TOD** | 程序包完整、同质性、截止、证据 | 三表程序包名称变体识别 ✅ | `addition_test_package_complete` ✅、`disposal_test_package_complete` ✅、`addition_population_homogeneity` ✅；样本一致性/证据充分性待做 |

### Checklist 对照（摘要）

| 检查点 | rule_id | 自动化 | 状态 |
| --- | --- | --- | --- |
| 新增/处置三表程序包完整 | `addition_test_package_complete` / `disposal_test_package_complete` | AUTO_WARN | ✅ |
| 新增清单字段完整 | `addition_required_fields` | AUTO_FAIL | ✅ |
| 新增总体同质性提示 | `addition_population_homogeneity` | REVIEW | ✅ |
| 新增 vs 后推购置 | `addition_rollforward_reconciliation` | AUTO_WARN | ❌ |
| 差异 >SAD | `addition_difference_over_sad` | AUTO_WARN | ❌ |
| 处置清单字段完整 | `disposal_required_fields` | AUTO_FAIL | ❌ |
| 处置 vs 后推 | `disposal_rollforward_reconciliation` | AUTO_WARN | ❌ |
| 同质性 / 证据 | `addition_*` / `disposal_*` REVIEW | REVIEW | ❌ |

**前置依赖**：K.01 P0 稳定 + K.01 区块6 TE 路由（`rollforward_te_program_routing`）判断 K.02 是否必须执行。

---

## K.03 折旧

### 工作表 / 输入

| sheet | 说明 |
| --- | --- |
| `K.03.1 SAP` | 实质性分析程序 |
| `K.03.2 折旧测试TOD` / By item | 详细折旧测试 |
| `K.03.3 折旧政策复核` | 政策合理性 |

### 逻辑模块（建议）

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| **K3-A SAP** | CRA 与 Lead 一致、精确度选择 | ❌ REVIEW |
| **K3-B TOD 清单** | 字段完整、重算差异 | ❌ |
| **K3-C vs K.01** | 本期折旧 vs 后推计提 / 表4 | ❌ 依赖 K.01 区块5 |
| **K3-D 政策** | 三要素、变更理由 | ❌ REVIEW / LLM |

### Checklist 对照（摘要）

| 检查点 | rule_id | 状态 |
| --- | --- | --- |
| 折旧清单字段完整 | `depreciation_required_fields` | ❌ |
| vs 后推折旧 | `depreciation_rollforward_reconciliation` | ❌ |
| 重算差异 | `depreciation_recalculation_difference` | ❌ |
| SAP CRA/精确度 | `sap_*` | ❌ |
| 政策复核 | `depreciation_policy_*` | ❌ |

---

## 开发顺序建议

1. K.01 M2b（FA list、SAD、TE 路由）  
2. K.02 清单 **ingest + 必填 + vs 后推**  
3. K.03 TOD **字段 + vs 后推**  
4. SAP / 政策 → `NEED_REVIEW` + LLM

新建详细矩阵时：可复制 [k01-six-block-qc-matrix.md](./k01-six-block-qc-matrix.md) 表头，按上表「逻辑模块」拆区块逐条填「风险点 / 规则 / 状态」。

# 最新交接

> 更新时间：2026-07-13。本文只保留当前可执行基线、已知边界和下一步；历史阶段记录见 [`archive/through-2026-07-13.md`](archive/through-2026-07-13.md)。

## 当前基线

- 分支基线：`main`，提交 `5915d63 Complete K03 SAP rule routing and parameter checks`。
- 产品形态：本地 Python 程序 + Streamlit UI + 可选 OpenAI 兼容 LLM API。
- 必交付：结构化质检报告和 `*_qc_annotated.xlsx` 底稿标注副本均已有可运行首版。
- 规则真源：`src/rules/registry.py`；UI/JSON 只能展示 runner 和 `execution_ledger` 记录的本次运行事实。
- 自动结论仅使用 `PASS`、`WARN`、`FAIL`、`NEED_REVIEW`；LLM 不得单独把规则 `FAIL` 改为 `PASS`。

## 当前覆盖

| 模块 | 当前能力 | 重要边界 |
| --- | --- | --- |
| 汇总页 / PSP | 程序执行、拒绝理由和工作表引用等检查 | 复杂豁免理由仍可能需要人工判断 |
| K.00 Lead | 基础信息、CRA/TT、预期分析、变动说明、调整汇总等读取与规则 | 项目背景和重大判断不自动替代 |
| K.01 后推 | 六区块识别、列/金额勾稽、FA list 和折旧费用等规则 | 仍有个别版式和 notes 分类边界 |
| K.02 新增/处置 | 清单、总体勾稽、选样输出和详细测试规则已接入 | 真实底稿锚点与证据充分性需持续回归 |
| K.03 折旧 | SAP/TOD/政策路径识别、runner 分派、关键参数和差异规则 | 特别风险、实体类型、复杂政策合理性仍需人工复核 |
| 报告与标注 | JSON、HTML、UI、执行台账、Comments 表和单元格批注 | 正式 Excel 汇总报告仍待完善 |
| LLM | 客户端、配置、脱敏及可选辅助复核 | 默认关闭；`--llm-rules` / `--llm-checklist` 尚未形成正式能力 |

## K.03 最新事实

- `K03ExecutionProfile` 是 K.03 工作簿级识别真源；rules 不得重新猜测程序路径。
- SAP 中精度、SAP 高精度、TOD by-item、TOD 抽样按实际执行路径分别进入 runner；K.03.3 折旧政策复核保持独立必要程序。
- `sap_precision_selection` 使用 Lead 计价/计量（V/M）CRA；中精度 SAP 在 CRA 不低于 Low 时需结合实际执行的 TOD 补充程序复核。
- `sap_te_consistency` 比较 SAP TE 与 Lead TE；`sap_high_cra_consistency` 只适用于高精度 SAP，并比较 Lead V/M CRA。
- 适用但参数不可可靠读取时记录 `DATA_INSUFFICIENT`；非对应路径记录 `NOT_APPLICABLE`，不得默认通过。
- 多张已执行 SAP 页分别检查并保留 observation。最近聚焦验收为 `32 passed`，不是全仓测试结论。

## 已知风险

1. checklist 尚未全部自动化；不得把 registry 外的规划项展示为已执行。
2. K.01 table4 notes 分类、table3 重大差异与说明位置仍是已知校准点。
3. K.02/K.03 对真实底稿变体的识别和单元格锚点仍需持续回归。
4. LLM 只可提供辅助解释；金额勾稽、唯一性、必填和一致性继续由规则判定。
5. 仓库中标准资料可供阅读；真实案例库、`.env` 和本地质检输出不得提交。

## 推荐下一步

1. 用脱敏真实版式继续验证 K.03 SAP/TOD/政策路径，优先检查误路由和参数取数证据。
2. 对 K.00–K.03 高价值确定性规则逐条补齐 observation 和边界测试。
3. 完善正式 Excel 质检报告，同时保持报告与底稿标注 findings 一致。
4. 拓展其他科目前，先建立独立领域词典、checklist 映射和治理准入清单，不直接复制固定资产结论。

## 接手阅读顺序

1. [`../../README.md`](../../README.md)
2. [`../ONBOARDING.md`](../ONBOARDING.md)
3. [`../architecture/fa_qc_governance_plan.md`](../architecture/fa_qc_governance_plan.md)
4. [`../qc-checklist.md`](../qc-checklist.md)
5. [`../planning/program-qc-coverage-index.md`](../planning/program-qc-coverage-index.md)

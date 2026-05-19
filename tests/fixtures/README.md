# 测试样例数据

`tests/fixtures/` 存放脱敏后的固定资产样例数据。

## 存放内容

- 小规模 Excel/CSV/JSON fixture。
- 覆盖正常记录、缺失字段、重复编码、金额错误和日期异常的样例。
- 与测试用例配套的输入文件。

## 数据安全

- 不提交真实资产编号。
- 不提交真实部门、真实人员、真实供应商、合同号或发票号。
- 资产编号使用 `FA-TEST-001`、`FA-TEST-002` 等格式。

## 规则字典（脱敏）

| 文件 | 说明 |
| --- | --- |
| `rule_dictionary_sanitized.csv` | 35 条质检规则主表（由桌面规则字典导出，示例数值已脱敏） |
| `rule_dictionary_priority_sanitized.csv` | 人工实施优先级（P1/P2/P3） |

映射与 Agent 排期见 [rule-dictionary-mapping.md](../docs/rule-dictionary-mapping.md)。

## FA list 样例

| 文件 | 说明 |
| --- | --- |
| `fa_list_mixed.csv` | 混合 PASS/WARN/FAIL，规则集成测试主 fixture |
| `fa_list_mixed.xlsx` | 同上内容的 Excel（`FA list` sheet），供 `fa-qc-run` Demo |
| `workbook_psp_demo.xlsx` | FA list + `汇总` 页（含 PSP 不执行缺理由样例），整本流水线 Demo |
| `fa_list_valid.csv` | 基本通过样例 |
| `fa_list_no_asset_id.csv` | 无资产编号列，触发 NEED_REVIEW |

## 后续建议文件

- `basic_assets.csv`：基础正常样例。
- `invalid_required_fields.csv`：缺失必填字段样例。
- `invalid_amounts.csv`：金额关系异常样例。

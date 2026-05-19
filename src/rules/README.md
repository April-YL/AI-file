# 质检规则模块

`src/rules/` 存放固定资产质检规则和规则执行相关代码。

## 存放内容

- 必填字段校验。
- 资产编码唯一性校验。
- 金额关系校验。
- 日期合理性校验。
- 规则注册和规则执行器。

## 规则输出

规则应输出统一的质检问题结构：

```json
{
  "asset_id": "FA-TEST-001",
  "rule_id": "required_fields",
  "field": "asset_name",
  "severity": "FAIL",
  "message": "资产名称不能为空",
  "suggestion": "补充资产名称后重新提交质检"
}
```

## 已实现文件

- `models.py`：`QcIssue`、`Severity`、`AutomationLevel`
- `parsing.py`：金额解析、空行跳过、相对允差
- `registry.py`：规则字典 → `RuleSpec` 注册表
- FA list：`fa_list_required_fields`、`unique_asset_id`、`asset_value_consistency`、`asset_amount_non_negative`、`useful_life_positive`、`salvage_rate_range`
- 汇总页：`psp_completion`（AE-003）
- `runner.py`：`run_fa_list_rules`（执行后自动 `attach_rule_metadata`）

## 后续建议文件

- `asset_start_date_reasonable.py`（FA-RC-007）、K.01 `rollforward_*` 等

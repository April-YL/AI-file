# 固定资产质检参考

## 质检问题结构

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

## 规则 ID 命名

- 使用小写蛇形命名。
- 示例：`required_fields`、`unique_asset_id`、`value_consistency`。
- 同一规则 ID 不应表达多个业务含义。

## 严重级别

- `PASS`：无问题。
- `WARN`：轻微风险或建议确认。
- `FAIL`：明确不合规。
- `NEED_REVIEW`：需要人工判断。

## 样例数据约定

- 使用 `FA-TEST-001`、`FA-TEST-002` 等脱敏资产编号。
- 不出现真实公司、部门、人员、供应商、合同号或发票号。
- 每个 fixture 文件应在文件名中表达用途，例如 `basic_assets.csv`、`invalid_amounts.csv`。

## MVP 推荐测试场景

- 完整资产记录应通过基础校验。
- 缺少资产编码应返回 `FAIL`。
- 重复资产编码应返回 `FAIL`。
- 原值小于累计折旧应返回 `FAIL`。
- 启用日期晚于质检日期应返回 `WARN`。

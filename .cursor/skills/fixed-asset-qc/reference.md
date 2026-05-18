# 固定资产质检参考

## 质检问题结构

```json
{
  "source_file": "K1 SWP 固定资产 202YMMDD XYZ公司.xlsx",
  "source_sheet": "FA list",
  "procedure_code": "FA_LIST",
  "asset_id": "FA-TEST-001",
  "rule_id": "fa_list_required_fields",
  "field": "asset_name",
  "severity": "FAIL",
  "message": "资产名称不能为空",
  "suggestion": "补充资产名称后重新提交质检"
}
```

## 规则 ID 命名

- 使用小写蛇形命名。
- 示例：`fa_list_required_fields`、`unique_asset_id`、`asset_value_consistency`。
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
- 原值、累计折旧、减值准备、净值关系异常应返回 `FAIL`。
- 启用日期晚于质检日期应返回 `WARN`。
- 使用寿命（月）非正数应返回 `FAIL`。
- 残值率小于 0 或大于 1 应返回 `FAIL`。
- 新增清单、处置清单、折旧清单缺少必需字段应返回 `FAIL`。

## 关键文档

- SOP 与程序流程：`docs/audit-workflow.md`
- 质检检查点：`docs/qc-checklist.md`
- 底稿字段映射：`docs/workpaper-fields.md`
- 资料读取摘要：`docs/source-materials-reading-notes.md`

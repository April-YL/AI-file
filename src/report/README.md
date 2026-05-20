# 质检报告模块

`src/report/` 存放固定资产质检结果汇总和导出代码。

## 存放内容

- 资产级质检结论汇总。
- 问题明细列表生成。
- 规则维度统计。
- 后续 Excel、JSON 或人工复核清单导出。

## 不存放内容

- 原始台账读取。
- 业务规则判断。
- 真实业务数据。

## 已实现（节选）

- `summary.py`：`QcReport`、`build_report`（含 `summary_sheet_section` 可选块）
- `summary_sheet_report.py`：汇总页解析摘要 + AE-003 结论，写入 JSON/HTML/UI
- `export_json.py`、`export_review_html.py`、`cli.py`、`pipeline.py`、`ui_app.py`

## 后续建议文件

- `export_excel.py`：导出 Excel 报告

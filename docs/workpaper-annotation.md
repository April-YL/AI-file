# 底稿标注交付说明（M2a）

> 面向质检人员的**主交付物**：带标注的 Excel 底稿副本。案例库参考：`Comments【归档前删除】`（B 医疗等 SWP 底稿）。

## 输出文件

| 文件 | 说明 |
| --- | --- |
| `<底稿名>_qc_annotated.xlsx` | 原底稿副本 + 质检标注，**不覆盖**用户原件 |
| `<底稿名>_qc_report.json` | 结构化 findings（技术明细，可选） |
| `<底稿名>_qc_review.html` | 精简 Findings 浏览器预览（可选） |

生成方式：

```powershell
fa-qc-run path\to\workbook.xlsx
fa-qc-ui   # 界面下载「带标注底稿」
```

实现：`src/report/export_annotated_workbook.py`。

## 两张 Comments 表

| 顺序 | Sheet 名 | 列（与案例库一致） | 填写规则 |
| --- | --- | --- | --- |
| 1 | `Comments【归档前删除】` | EY Ref. / Tab Ref. / Cell Ref. / Question/Comment / Answer/Comment / Closed? | **其他程序**（汇总、Lead、K.01 等）：**一条 finding 一行**；**FA list**：仅 **共性问题合并行**（按 `rule_id + field + severity` 合并，注明条数并指向附表） |
| 2 | `Comments【FA list】` | 同上 | **FA list** 全部 findings **逐条明细** |

**不**将 PM/TE/SAD、CRA 摘录写入 Comments 表；人工核对见 JSON `manual_review_sections` 与 UI「人工复核摘录」。

## 单元格批注

- 对有 `source_row` 的 finding，在对应 **Tab Ref.** 工作表的 B 列（可配置默认列）写入 Excel **批注** + 浅色高亮（FAIL 红 / WARN 黄 / NEED_REVIEW 蓝）。
- 无行号的 sheet 级问题仅出现在 Comments 表中。

## Streamlit UI（`fa-qc-ui`）

| 页签 | 用途 |
| --- | --- |
| Findings（分程序） | 按汇总 / Lead / FA list / K.01 等分块；FA list 条数多时常折叠 |
| 人工复核摘录 | 基准信息 + AE-001（PM/TE/SAD）+ AE-002（CRA/TT），**须人工与 Canvas 核对** |
| 质检摘要 | Lead / AE-003 整体结论 |
| HTML 预览 | 精简 findings 表 |

## 案例库 Lead 回归

- 脚本：`python scripts/run_case_lead_regression.py`
- 产物：`artifacts/case_lead_regression.md` / `.json`
- 跳过：>20MB 或文件名含 `A有限公司` / `A公司`（见 `src/ingest/case_library.py`）

## 密钥与安全

- API 密钥仅写在本地 `.env`（见 [data-security.md](data-security.md)），**禁止**提交 Git。
- 提交前：`python scripts/check_staged_no_secrets.py`

## 相关文档

- [AGENTS.md](../AGENTS.md) — 必交付项
- [architecture.md](architecture.md) — `src/report/` 模块边界
- [ONBOARDING.md](ONBOARDING.md) — 上手与命令

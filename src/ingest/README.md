# 数据接入模块

`src/ingest/` 存放固定资产数据接入代码。

## 存放内容

- Excel/CSV/API 输入读取逻辑。
- 原始字段名到标准字段名的映射。
- 基础数据清洗，例如去空格、日期格式标准化、金额类型转换。
- 输入数据的轻量结构检查。

## 不存放内容

- 业务质检规则。
- 报告导出逻辑。
- 真实资产数据。

## 已实现

| 模块 | 作用 |
| --- | --- |
| `models.py` | 工作表类型、分类结果、诊断结构 |
| `constants.py` | 字段同义词、语义必需列、内容特征签名 |
| `field_mapping.py` | 表头→标准字段；FA list 语义必需列检查 |
| `header_detection.py` | 多行表头扫描 |
| `sheet_classifier.py` | **名称 + 内容** 综合识别 sheet 类型 |
| `rollforward_sheet.py` | K.01 后推：`RollforwardSheetDataset`、期初/期末列绑定、合计行提取 |
| `workbook_reader.py` | 读取整本底稿并输出诊断；`list_workbook_sheet_titles`（read_only，仅表名列表，供汇总页与工作表勾稽） |
| `cli.py` | 命令行诊断入口 |

## 使用方式

```powershell
cd "D:\AI file"
$env:PYTHONPATH = "src"
python -m ingest.cli
python -m ingest.cli "固定资产质检agent\案例库\某文件.xlsx"
python -m ingest.cli --max-mb 50 --json
```

识别策略见 `docs/sheet-classification.md`。

## 汇总页（单主表）

- `summary_sheet.py`：在前 50 行内打分选取 **程序 +（是否执行 或 不执行原因）** 表头行，可跳过表题；主表在遇到 **连续 3 个空行** 后结束，避免吞掉表下说明。
- 输出 `column_bindings`（`procedure` / `sheet_ref` / `execution_status` / `waiver_reason` / `notes`）、`last_data_row`、`notes`。
- 表头匹配时 **忽略空列**，避免 `"" in "程序"` 误命中。
- `load_assets.py`：对外统一加载 FA list / 清单。

## K.00 Lead Sheet（锚点分块）

- `lead_sheet_blocks.py`：按**标签锚点**识别 6 块（基础信息、CRA/TT、预期分析、两期引导主表、波动说明、调整汇总），**不依赖固定行号**。
- `lead_sheet.py`：输出 `LeadSheetDataset`（`blocks`、`basic_info_fields`、`cra_rows`、`expectations`、`movement_rows` 等）；`load_lead_from_workbook` 默认读前 200 行。

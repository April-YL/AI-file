# 最新交接

> 每次收工前更新本文。新成员接手先读 `docs/ONBOARDING.md`，再读 `AGENTS.md` 和本文。

## 项目终态（对齐）

固定资产质检 Agent 的完整目标是：

- **输入**：固定资产底稿 + 必要辅助文件（checklist、TE/SAD 等）。
- **过程**：按 `docs/qc-checklist.md` 检查是否存在 findings，模拟质检人员复核底稿。
- **必交付**：
  1. **质检报告**（findings 清单、严重级别、程序/资产维度汇总、复核建议）。
  2. **底稿标注**（在原底稿副本上批注/高亮问题位置，与 findings 一一对应）。

当前代码完成的是 M1 切片（ingest + 少量 FA list 规则 + JSON 报告骨架），**底稿标注尚未实现**。

## 当前状态

- Git 仓库已初始化并关联 GitHub 远程。
- 资料库与案例库诊断、SOP/checklist/字段映射文档已沉淀。
- `src/ingest/`：sheet 分类、字段映射、底稿诊断 CLI、FA list CSV/行解析。
- `src/rules/` + `src/report/`：首批 3 条 FA list 规则 + JSON 报告最小闭环。
- **距终态差距**：全 checklist 覆盖、正式质检报告导出、**底稿标注回写**、多 sheet Excel 端到端、一键 CLI。

## 已完成

- 项目长期上下文：`AGENTS.md`（已按终态目标与必交付项更新）
- 项目结构说明：`docs/PROJECT_STRUCTURE.md`
- 领域词典、架构、任务与进度文档
- 质检 checklist：`docs/qc-checklist.md`
- 底稿字段映射：`docs/workpaper-fields.md`
- 案例库底稿读取诊断（6 份小型底稿）
- `src/ingest/`（含 `fa-qc-diagnose`）、`tests/ingest/`
- M1 首批规则与单测：`fa_list_required_fields`、`unique_asset_id`、`asset_value_consistency`
- `src/report/`：`run_fa_list_qc`、JSON 报告结构
- 脱敏 fixture：`tests/fixtures/fa_list_*.csv`

## 进行中

- M1：扩展 FA list / 相关表规则，Excel 行级解析与案例库回归。
- 报告：在 JSON 骨架上定型正式质检报告字段（程序编码、检查点、finding 关联）。

## 下一步（按终态优先级）

1. **质检报告（必交付）**：定型报告 schema（程序 + 检查点 + finding）；支持 JSON 导出，后续 Excel 报告模板。
2. **底稿标注（必交付）**：`src/report/` 增加标注模块——根据 finding 的 `source_sheet` / `source_row` / `field` 在底稿副本写入批注或高亮；默认输出 `*_qc_annotated.xlsx`，不覆盖原件。
3. 扩展 checklist 规则（见 `docs/qc-checklist.md` 优先级）并接入多 sheet 读取。
4. `fa-qc-run` CLI：底稿路径 → 检查 → **报告 + 标注副本**。
5. 6 份案例底稿端到端回归；大文件（A 公司 ~42MB）性能优化后纳入。

## 已知问题

- **底稿标注**：未实现，为终态硬缺口。
- 质检报告尚无面向业务人员的 Excel 版；当前以 JSON 结构为主。
- PDF 程序指引未抽取正文，可能需 OCR。
- A 公司底稿约 42MB 已跳过，需读取性能优化。
- 处置清单等场景：`单据编号` 不得误映射为 `asset_id`。
- `ingest/records.py` 以 CSV/行解析为主，Excel FA list 需与 `workbook_reader` 合并。

## 相关文件

- `AGENTS.md` — 终态目标与必交付项
- `docs/qc-checklist.md` — findings 检查来源
- `docs/workpaper-fields.md`、`docs/architecture.md`
- `src/ingest/`、`src/rules/`、`src/report/`
- `tests/rules/`、`tests/fixtures/`
- `docs/ONBOARDING.md`

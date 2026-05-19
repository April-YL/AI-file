# 最新交接

> 每次收工前更新本文。新成员接手先读 `docs/ONBOARDING.md`，再读 `AGENTS.md` 和本文。

## 项目终态（对齐）

固定资产质检 Agent 的完整目标是：

- **输入**：固定资产底稿 + 必要辅助文件（checklist、TE/SAD 等）。
- **过程**：按 `docs/qc-checklist.md` 检查是否存在 findings，模拟质检人员复核底稿。
- **必交付**：
  1. **质检报告**（findings 清单、严重级别、程序/资产维度汇总、复核建议）。
  2. **底稿标注**（在原底稿副本上批注/高亮问题位置，与 findings 一一对应）。

当前代码完成 **M1 切片**（ingest + 规则字典映射 + 3 条 `fa_list_*` 规则 + JSON 报告）；**Agent P1 已调整为 M2a**（整底稿流水线，汇总/K.01 规则优先），**底稿标注尚未实现**。

## 当前状态

- Git 仓库已初始化并关联 GitHub 远程。
- 资料库与案例库诊断、SOP/checklist/字段映射文档已沉淀。
- `src/ingest/`：sheet 分类、字段映射、底稿诊断 CLI、FA list CSV/行解析。
- `src/rules/` + `src/report/`：首批 3 条 FA list 规则 + JSON 报告最小闭环。
- 规则字典映射：`docs/rule-dictionary-mapping.md`、`src/rules/registry.py`、`tests/fixtures/rule_dictionary_*.csv`
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

## 进行中（M2a = Agent P1）

- **流水线**：`fa-qc-run` 编排；整本 Excel 多 sheet 解析（不限于 FA list）。
- **规则优先**：汇总页 PSP/拒绝理由（AE-003）、K.01 后推表结构与异常金额（`rollforward_*`）；客户台账作可选输入，复用 `fa_list_*` 作一致性核对。
- **必交付雏形**：程序维度报告 schema；底稿批注 v0（`*_qc_annotated.xlsx`）。

## 下一步（M2a 验收导向）

1. `fa-qc-run`：底稿路径 → 解析 → 检查 → **报告 JSON + 标注副本**。
2. ingest：汇总 sheet + K.01 后推表数据对象（语义字段，不写死单元格）。
3. rules：AE-003、`rollforward_exists` / `rollforward_columns_complete`（及与台账核对时的 `fa_list_*` 复用）。
4. report：按 `dict_rule_code` / 程序汇总；openpyxl 批注回写。
5. 案例库 1～2 份小型底稿端到端回归。

**暂缓为主战场**：单独扩展 FA list 规则条数；TE/Canvas、证据充分性等标 NEED_REVIEW。

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

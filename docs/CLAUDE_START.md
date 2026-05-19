# Claude 会话快速上手

在 Claude 中继续开发前，**先让 Claude 阅读本仓库文件**（上传或 `@` 引用），再粘贴文末「开场白」。

## 5 分钟阅读顺序

| 顺序 | 文件 | 用途 |
| --- | --- | --- |
| 1 | [AGENTS.md](../AGENTS.md) | 终态目标、必交付项、模块边界 |
| 2 | [handoff/latest.md](handoff/latest.md) | **最新进度**（以 Git 为准） |
| 3 | [rule-dictionary-mapping.md](rule-dictionary-mapping.md) | 35 条规则字典 ↔ `rule_id`；**M2a = Agent P1** |
| 4 | [architecture.md](architecture.md) | ingest → rules → report 数据流 |
| 5 | [ONBOARDING.md](ONBOARDING.md) | 命令、目录、里程碑 |

按需查阅：`docs/qc-checklist.md`、`docs/workpaper-fields.md`、`docs/audit-workflow.md`。

## 当前进度（摘要，详见过 handoff）

| 项 | 状态 |
| --- | --- |
| 远程仓库 | https://github.com/April-YL/AI-file.git ，分支 `main` |
| M1 | 已完成：ingest 诊断、`fa_list_*` 三条规则、JSON 报告、规则字典 registry |
| **M2a（Agent P1）** | **进行中**：`fa-qc-run`、整本 Excel、**汇总 + K.01** 优先、报告 + 批注 |
| 必交付缺口 | 底稿标注未实现；无 `fa-qc-run` 入口 |
| Demo 最快路径 | `fa-qc-run` + Excel 读 FA list + `qc_report.json`（见下） |

**不要**把「扩展 FA list 规则条数」当作 P1 主线；客户台账与 FA list 共用 `fa_list_*`，作 K.01 核对输入。

## 代码入口（Claude 改代码时先看）

| 模块 | 路径 | 说明 |
| --- | --- | --- |
| 接入 | `src/ingest/` | `diagnose_workbook`、`records.load_fa_list_csv` |
| 规则 | `src/rules/` | `registry.py`、`runner.run_fa_list_rules` |
| 报告 | `src/report/` | `run_fa_list_qc`、`export_report_json` |
| 测试 | `pytest tests/ingest tests/rules -q` | |
| 诊断 CLI | `fa-qc-diagnose` | 已有，仅诊断 sheet |

## 建议 Claude 下一任务（Demo / M2a）

1. 新增 `fa-qc-run`（`pyproject.toml` 入口）。
2. `ingest/records.py`：`load_fa_list_from_workbook`（从 Excel 找 FA list sheet）。
3. 报告落盘 + 终端摘要；可选 `report/annotate.py` 批注 v0。

验收：一条命令对案例库小型 xlsx 或 `tests/fixtures/fa_list_mixed.csv` 输出含 `dict_rule_code` 的 JSON 报告。

## 数据安全

- 不提交真实资产编号、部门、人员、合同、密钥。
- 案例库/资料库在 `.gitignore`，本地路径：`固定资产质检agent/案例库`。

---

## 复制到 Claude 第一条消息（开场白）

```text
继续开发固定资产质检 Agent。仓库：https://github.com/April-YL/AI-file.git

请先阅读（按顺序）：
1. AGENTS.md
2. docs/handoff/latest.md
3. docs/CLAUDE_START.md
4. docs/rule-dictionary-mapping.md
5. docs/architecture.md

背景摘要：
- 终态：输入固定资产底稿 → 按 checklist 出 findings → 必交付「质检报告 + 底稿标注副本」。
- M1 已完成：ingest 诊断、规则字典 registry、fa_list_* 三条规则、JSON 报告。
- 当前 M2a（Agent P1）：整底稿流水线，优先汇总页 PSP（AE-003）与 K.01 后推，不是 FA list 规则扩张。
- 代码边界：ingest 只解析/映射；rules 只校验；report 只汇总与标注。

本次任务：<写具体任务，例如实现 fa-qc-run + Excel FA list 读取 + 输出 qc_report.json>

验收标准：
- pytest tests/ingest tests/rules 通过
- 能对样例或案例库底稿输出 JSON 报告（含 dict_rule_code、severity）
- 收工更新 docs/handoff/latest.md

约束：不提交真实业务数据；修改 src/rules/ 须同步 tests/rules/。
```

将 `<写具体任务>` 换成你在 Claude 里要做的具体项（如 Demo 路径 B）。

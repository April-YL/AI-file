# 数据安全与密钥管理

> **全局强制约定**：LLM API 密钥、`.env` 本地配置 **永不进入 Git**。AI 助手与开发者在提交、推送前必须遵守本文。

## 1. 密钥存放位置

| 允许 | 禁止 |
| --- | --- |
| 项目根目录 **`.env`**（本地，已忽略） | 将 `FA_QC_LLM_API_KEY` 写入任何将提交的文件 |
| 操作系统/用户环境变量（可选） | 在 `tests/`、`docs/`、脚本注释中粘贴真实 API 密钥 |
| 仓库内 **`.env.example`**（仅占位符，无真实密钥） | `git add .env` 或 `git add -f .env` |

配置步骤见 [ONBOARDING.md](ONBOARDING.md) § 大模型 API。

## 2. Git 忽略规则（`.gitignore`）

以下路径**不得**从忽略列表中移除：

```gitignore
.env
.env.local
.env.*.local
!.env.example
```

说明：

- `.env`：你的真实 `FA_QC_LLM_API_KEY`、`BASE_URL`、`MODEL`。
- `.env.example`：**可以**提交，仅含空密钥与示例 URL，供团队复制为 `.env`。

## 3. 提交 / 推送前自检（必做）

在项目根目录执行：

```powershell
python scripts/check_staged_no_secrets.py
```

若退出码非 0，**禁止提交**，先从暂存区移除敏感文件：

```powershell
git restore --staged .env
git status
```

### 禁止出现的暂存内容

- 文件路径：`.env`、`.env.local` 等（除 `.env.example` 外）
- 文件内容：含真实 `FA_QC_LLM_API_KEY` 赋值、Bearer 令牌、任何明文 API 密钥
- 误把案例库/资料库底稿 `git add` 进仓库（见 `.gitignore` 中 `固定资产质检agent/`）

## 4. 大模型相关环境变量

| 变量 | 是否可提交到 Git |
| --- | --- |
| `FA_QC_LLM_API_KEY` | **否** |
| `FA_QC_LLM_BASE_URL` | 仅示例可出现在 `.env.example` |
| `FA_QC_LLM_MODEL` | 仅示例可出现在 `.env.example` |
| `FA_QC_LLM_ENABLED` | 示例可为 `false` |

程序通过 `src/llm/env_loader.py` 加载根目录 `.env`；**不要**把密钥写进 `config.py` 或测试代码。

## 5. 若密钥已误提交

1. 立即在 API 网关**轮换/作废**该密钥。
2. 不要只改 `.env` 后再次提交——需从历史中移除（联系仓库管理员或使用 `git filter-repo`，本仓库当前历史未包含 `.env`）。
3. 更新本地 `.env`，重新运行 `python scripts/test_llm_connection.py` 验证。

## 6. 关联文档

- [AGENTS.md](../AGENTS.md) — 数据安全约定
- [ADR-0002](decisions/ADR-0002-llm-agent-evolution.md) — 密钥不进 Git、私有化端点
- [llm-agent-roadmap.md](llm-agent-roadmap.md) — LLM 配置说明

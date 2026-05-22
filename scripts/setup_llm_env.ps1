# 交互式生成/更新项目根目录 .env（不提交 Git）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env"
$Example = Join-Path $Root ".env.example"

Write-Host "固定资产质检 Agent — 大模型 API 配置" -ForegroundColor Cyan
Write-Host "目标文件: $EnvFile`n"

if (-not (Test-Path $EnvFile) -and (Test-Path $Example)) {
    Copy-Item $Example $EnvFile
    Write-Host "已从 .env.example 复制生成 .env"
}

$base = Read-Host "BASE_URL [默认: https://your-api-host/v1]"
if ([string]::IsNullOrWhiteSpace($base)) { $base = "https://your-api-host/v1" }

$model = Read-Host "MODEL [默认: your-model-id]"
if ([string]::IsNullOrWhiteSpace($model)) { $model = "your-model-id" }

$keySecure = Read-Host "API_KEY（输入时可见，勿在录屏环境使用）" -AsSecureString
$keyBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($keySecure)
$key = [Runtime.InteropServices.Marshal]::PtrToStringAuto($keyBstr)

$lines = @(
    "# 由 scripts/setup_llm_env.ps1 生成/更新",
    "FA_QC_LLM_ENABLED=true",
    "FA_QC_LLM_BASE_URL=$base",
    "FA_QC_LLM_MODEL=$model",
    "FA_QC_LLM_API_KEY=$key",
    "FA_QC_LLM_TIMEOUT=120",
    "FA_QC_LLM_MAX_TOKENS=4096"
)
Set-Content -Path $EnvFile -Value ($lines -join "`n") -Encoding UTF8
Write-Host "`n已写入 .env。正在测试连通性…" -ForegroundColor Green
Set-Location $Root
python scripts/test_llm_connection.py

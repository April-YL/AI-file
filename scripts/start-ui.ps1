# 固定资产质检 — 启动本地界面（使用项目虚拟环境，避免全局 Python 文件占用）
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "正在创建虚拟环境并安装依赖（首次约 1～3 分钟）..."
    python -m venv .venv
    & .\.venv\Scripts\pip install -e ".[ui]"
}

Write-Host "启动界面：浏览器将打开 http://localhost:8501"
Write-Host "关闭请在本窗口按 Ctrl+C"
& .\.venv\Scripts\python.exe -m streamlit run src\report\ui_app.py --server.headless true --browser.gatherUsageStats false

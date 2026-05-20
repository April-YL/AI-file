@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo ========================================
echo   固定资产质检 Agent - 本地界面
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/2] 首次运行：创建虚拟环境并安装依赖，请稍候...
    python -m venv .venv
    if errorlevel 1 (
        echo 错误：无法创建虚拟环境，请确认已安装 Python 3.10+
        pause
        exit /b 1
    )
    call .venv\Scripts\pip install -e ".[ui]"
    if errorlevel 1 (
        echo 错误：依赖安装失败
        pause
        exit /b 1
    )
    echo 安装完成。
    echo.
)

echo [2/2] 启动界面，浏览器将打开 http://localhost:8501
echo 关闭本窗口请按 Ctrl+C
echo.

.venv\Scripts\python.exe -m streamlit run src\report\ui_app.py --server.headless true --browser.gatherUsageStats false

pause

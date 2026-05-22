"""控制台入口 ``fa-qc-ui``：直接启动 Streamlit，不依赖已安装的 ``report`` 包。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    src = Path(__file__).resolve().parent
    app = src / "report" / "ui_app.py"
    if not app.is_file():
        print(f"未找到界面脚本: {app}", file=sys.stderr)
        raise SystemExit(1)
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    raise SystemExit(subprocess.call(cmd))

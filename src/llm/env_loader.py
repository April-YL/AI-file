"""加载项目根目录 ``.env``（可选依赖 python-dotenv）。"""

from __future__ import annotations

from pathlib import Path


def load_project_dotenv() -> bool:
    """若存在 ``.env`` 则加载；返回是否成功调用 load_dotenv。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
        return True
    load_dotenv(override=False)
    return True

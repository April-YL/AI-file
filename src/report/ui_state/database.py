# [阶段一] SQLite 数据库 — 连接管理 + 表结构
# 仅存元数据，产物走 artifacts/ 文件目录
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — SQLite 持久化（元数据 only）。"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def _resolve_data_dir() -> Path:
    """Resolve local persistence outside source-controlled project data."""
    configured = os.getenv("FA_QC_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "local_data" / "fixed_asset_qc"


DATA_DIR = _resolve_data_dir()
DB_PATH = DATA_DIR / "history.db"
ARTIFACTS_DIR = DATA_DIR / "artifacts"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    client_name     TEXT    NOT NULL DEFAULT '',
    canvas_id       TEXT    NOT NULL DEFAULT '',
    engagement_code TEXT    NOT NULL DEFAULT '',
    engagement_name TEXT    NOT NULL DEFAULT '',
    period_end      TEXT    NOT NULL DEFAULT '',
    subject_code    TEXT    NOT NULL DEFAULT 'FA_K1',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    archived        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS qc_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER NOT NULL,
    source_filename   TEXT    NOT NULL,
    started_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    completed_at      TEXT    NOT NULL DEFAULT '',
    overall_severity  TEXT    NOT NULL DEFAULT 'PASS',
    finding_count     INTEGER NOT NULL DEFAULT 0,
    fail_count        INTEGER NOT NULL DEFAULT 0,
    warn_count        INTEGER NOT NULL DEFAULT 0,
    need_review_count INTEGER NOT NULL DEFAULT 0,
    llm_enabled       INTEGER NOT NULL DEFAULT 0,
    delivery_stage    TEXT    NOT NULL DEFAULT 'none',
    duration_seconds  REAL    NOT NULL DEFAULT 0.0,
    subject_code      TEXT    NOT NULL DEFAULT 'FA_K1',
    artifact_dir      TEXT    NOT NULL DEFAULT '',
    agent_version     TEXT    NOT NULL DEFAULT '',
    pilot_build       TEXT    NOT NULL DEFAULT '',
    source_revision   TEXT    NOT NULL DEFAULT '',
    lock_status       TEXT    NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
"""

_QC_RUN_VERSION_COLUMNS = {
    "agent_version": "TEXT NOT NULL DEFAULT ''",
    "pilot_build": "TEXT NOT NULL DEFAULT ''",
    "source_revision": "TEXT NOT NULL DEFAULT ''",
    "lock_status": "TEXT NOT NULL DEFAULT ''",
}


def ensure_data_dir() -> None:
    """确保数据目录和产物目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """初始化数据库和表结构（幂等）。"""
    ensure_data_dir()
    with _get_conn() as conn:
        conn.executescript(_SCHEMA)
        _ensure_qc_run_version_columns(conn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")


def _ensure_qc_run_version_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(qc_runs)")}
    for name, definition in _QC_RUN_VERSION_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE qc_runs ADD COLUMN {name} {definition}")


@contextmanager
def _get_conn():
    """获取数据库连接（WAL 模式，短事务）。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_db():
    """公共上下文管理器：自动初始化 + 连接。"""
    init_db()
    with _get_conn() as conn:
        yield conn


def run_artifact_dir(run_id: int) -> Path:
    """返回指定 run 的产物目录路径。"""
    return ARTIFACTS_DIR / str(run_id)

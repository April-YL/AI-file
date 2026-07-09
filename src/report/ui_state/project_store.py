# [阶段一] 项目管理存储 — 创建/查询/列表
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — 项目（Entity）存取。"""

from __future__ import annotations

from report.ui_state.database import get_db


def ensure_default_project() -> int:
    """首次启动时自动创建默认项目，返回 project_id。"""
    with get_db() as db:
        row = db.execute("SELECT id FROM projects LIMIT 1").fetchone()
        if row:
            return row["id"]
        db.execute(
            "INSERT INTO projects (name, client_name, subject_code) VALUES (?, ?, ?)",
            ("默认项目", "未指定客户", "FA_K1"),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def create_project(
    name: str,
    client_name: str = "",
    period_end: str = "",
    engagement_code: str = "",
    engagement_name: str = "",
    canvas_id: str = "",
) -> int:
    """创建新的审计主体（Entity），返回 project_id。"""
    with get_db() as db:
        db.execute(
            "INSERT INTO projects (name, client_name, period_end, engagement_code, engagement_name, canvas_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, client_name, period_end, engagement_code, engagement_name, canvas_id),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_project(project_id: int) -> dict | None:
    """获取单个项目信息。"""
    with get_db() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None


def list_projects() -> list[dict]:
    """列出所有未归档项目，按 engagement_name 分组排序。"""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM projects WHERE archived = 0 "
            "ORDER BY engagement_name, name"
        ).fetchall()
        return [dict(r) for r in rows]


def list_engagements() -> list[str]:
    """去重后的 engagement 列表。"""
    with get_db() as db:
        rows = db.execute(
            "SELECT DISTINCT engagement_name FROM projects "
            "WHERE archived = 0 AND engagement_name != '' "
            "ORDER BY engagement_name"
        ).fetchall()
        return [r["engagement_name"] for r in rows]


def archive_project(project_id: int) -> None:
    """归档项目。"""
    with get_db() as db:
        db.execute("UPDATE projects SET archived = 1 WHERE id = ?", (project_id,))


def set_current_project(project_id: int) -> None:
    """（阶段二）设置当前活跃项目，暂存于 session_state。"""
    pass

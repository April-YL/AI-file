# [阶段一] 运行结果存储 — save / get_latest / get
# 产物走文件路径，不存 SQLite blob
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — QC 运行结果存取。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from report.ui_state.database import ARTIFACTS_DIR, get_db, run_artifact_dir


def save_run(
    project_id: int,
    filename: str,
    data: dict,
    json_bytes: bytes,
    html_bytes: bytes,
    annotated_bytes: bytes | None = None,
) -> int:
    """保存一次运行结果：元数据入 SQLite，产物写入 artifacts/<run_id>/ 目录。

    Args:
        project_id: 所属 Entity ID
        filename: 源文件名
        data: QcReport.to_dict() 的完整 dict
        json_bytes: JSON 报告字节
        html_bytes: HTML 预览字节
        annotated_bytes: 标注底稿字节（可选）

    Returns:
        run_id
    """
    summary = data.get("summary") or {}
    timings = data.get("runtime_timings") or {}

    with get_db() as db:
        db.execute(
            "INSERT INTO qc_runs "
            "(project_id, source_filename, completed_at, overall_severity, "
            "finding_count, fail_count, warn_count, need_review_count, "
            "llm_enabled, delivery_stage, duration_seconds, subject_code) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                filename,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                summary.get("overall_severity", "PASS"),
                _finding_count(data),
                summary.get("fail_count", 0),
                summary.get("warn_count", 0),
                summary.get("need_review_count", 0),
                1 if timings.get("llm_enabled") else 0,
                data.get("delivery_stage", "none"),
                round(float(timings.get("total_seconds", 0.0)), 2),
                data.get("subject_code", "FA_K1"),
            ),
        )
        run_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 写产物文件
        artifact_dir = run_artifact_dir(run_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        (artifact_dir / "report.json").write_bytes(json_bytes)
        (artifact_dir / "review.html").write_bytes(html_bytes)
        if annotated_bytes:
            (artifact_dir / "annotated.xlsx").write_bytes(annotated_bytes)

        # 记录产物路径
        db.execute(
            "UPDATE qc_runs SET artifact_dir = ? WHERE id = ?",
            (str(run_id), run_id),
        )

        return run_id


def get_latest_run(project_id: int | None = None) -> dict | None:
    """获取最近一次运行的完整数据（含产物路径）。

    Args:
        project_id: 可选，限定项目

    Returns:
        dict with keys: id, project_id, source_filename, overall_severity,
        finding_count, fail_count, warn_count, need_review_count,
        llm_enabled, delivery_stage, duration_seconds,
        artifact_dir, data (完整 QcReport dict)
    """
    with get_db() as db:
        if project_id is not None:
            row = db.execute(
                "SELECT * FROM qc_runs WHERE project_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM qc_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()

        if not row:
            return None

        result = dict(row)
        # 读取 JSON 产物恢复完整 data
        artifact_dir = result.get("artifact_dir")
        if artifact_dir:
            json_path = ARTIFACTS_DIR / artifact_dir / "report.json"
            if json_path.exists():
                result["data"] = json.loads(json_path.read_text(encoding="utf-8"))
        return result


def get_run(run_id: int) -> dict | None:
    """获取指定运行记录。"""
    with get_db() as db:
        row = db.execute("SELECT * FROM qc_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        artifact_dir = result.get("artifact_dir")
        if artifact_dir:
            json_path = ARTIFACTS_DIR / artifact_dir / "report.json"
            if json_path.exists():
                result["data"] = json.loads(json_path.read_text(encoding="utf-8"))
        return result


def list_runs(project_id: int | None = None, limit: int = 50) -> list[dict]:
    """[阶段二] 列出运行历史。阶段一暂时不调用。"""
    with get_db() as db:
        if project_id is not None:
            rows = db.execute(
                "SELECT * FROM qc_runs WHERE project_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM qc_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def delete_run(run_id: int) -> None:
    """[阶段二] 删除运行记录及产物文件。"""
    with get_db() as db:
        row = db.execute("SELECT artifact_dir FROM qc_runs WHERE id = ?", (run_id,)).fetchone()
        if row and row["artifact_dir"]:
            artifact_path = ARTIFACTS_DIR / row["artifact_dir"]
            if artifact_path.exists():
                shutil.rmtree(artifact_path)
        db.execute("DELETE FROM qc_runs WHERE id = ?", (run_id,))


# ---- helpers ----

def _finding_count(data: dict) -> int:
    issues = data.get("issues", [])
    return sum(1 for i in issues if i.get("severity") != "PASS")

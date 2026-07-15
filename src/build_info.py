"""Single source of truth for the running Agent build identity."""

from __future__ import annotations

import os
import subprocess
import tomllib
from importlib import metadata
from pathlib import Path
from typing import TypedDict


PILOT_BUILD = "PILOT-20260715.01"
_DISTRIBUTION_NAME = "fixed-asset-qc-agent"
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BuildInfo(TypedDict):
    agent_version: str
    pilot_build: str
    source_revision: str
    lock_status: str


def get_build_info() -> BuildInfo:
    """Return a snapshot that can be persisted with one QC run."""
    revision, is_dirty = _source_state()
    locked = bool(revision) and is_dirty is False
    return {
        "agent_version": _agent_version(),
        "pilot_build": PILOT_BUILD,
        "source_revision": revision or "未记录",
        "lock_status": "LOCKED" if locked else "UNLOCKED",
    }


def _agent_version() -> str:
    configured = os.getenv("FA_QC_AGENT_VERSION", "").strip()
    if configured:
        return configured
    try:
        return metadata.version(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        pass

    pyproject = _PROJECT_ROOT / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return "未记录"


def _source_state() -> tuple[str, bool | None]:
    configured_revision = os.getenv("FA_QC_SOURCE_REVISION", "").strip()
    if configured_revision:
        configured_lock = os.getenv("FA_QC_BUILD_LOCKED", "").strip().lower()
        if configured_lock in {"1", "true", "yes", "locked"}:
            return configured_revision, False
        return configured_revision, None

    revision = _run_git("rev-parse", "--short=8", "HEAD")
    if not revision:
        return "", None
    status = _run_git(
        "status",
        "--porcelain",
        "--",
        "src",
        "pyproject.toml",
    )
    if status is None:
        return revision, None
    return revision, bool(status)


def _run_git(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return (completed.stdout or "").strip()

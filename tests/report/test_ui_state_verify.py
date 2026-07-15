"""Persistence checks isolated from the user's real run history."""

from __future__ import annotations

import json

from report.ui_state import database, run_store
from report.ui_state.project_store import ensure_default_project


def _use_temporary_store(monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "fixed_asset_qc"
    artifacts_dir = data_dir / "artifacts"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "history.db")
    monkeypatch.setattr(database, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(run_store, "ARTIFACTS_DIR", artifacts_dir)


def test_run_version_round_trip(monkeypatch, tmp_path) -> None:
    _use_temporary_store(monkeypatch, tmp_path)
    project_id = ensure_default_project()
    build_info = {
        "agent_version": "0.1.0",
        "pilot_build": "PILOT-TEST.01",
        "source_revision": "abc12345",
        "lock_status": "LOCKED",
    }
    data = {
        "summary": {
            "overall_severity": "WARN",
            "fail_count": 0,
            "warn_count": 1,
            "need_review_count": 0,
        },
        "issues": [{"severity": "WARN", "rule_id": "test_rule"}],
        "runtime_timings": {"total_seconds": 1.25, "llm_enabled": False},
        "subject_code": "FA_K1",
        "build_info": build_info,
    }
    json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")

    run_id = run_store.save_run(
        project_id,
        "test_workbook.xlsx",
        data,
        json_bytes,
        b"<html></html>",
    )
    saved = run_store.get_run(run_id)

    assert saved is not None
    assert saved["agent_version"] == "0.1.0"
    assert saved["pilot_build"] == "PILOT-TEST.01"
    assert saved["source_revision"] == "abc12345"
    assert saved["lock_status"] == "LOCKED"
    assert saved["data"]["build_info"] == build_info
    assert (database.ARTIFACTS_DIR / str(run_id) / "report.json").exists()

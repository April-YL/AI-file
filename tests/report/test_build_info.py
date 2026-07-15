from __future__ import annotations

import build_info as build_info_module
from build_info import PILOT_BUILD, get_build_info
from report.summary import ReportSummary, QcReport
from rules.models import Severity


def test_build_info_uses_explicit_locked_revision(monkeypatch) -> None:
    monkeypatch.setenv("FA_QC_AGENT_VERSION", "9.8.7")
    monkeypatch.setenv("FA_QC_SOURCE_REVISION", "abc12345")
    monkeypatch.setenv("FA_QC_BUILD_LOCKED", "true")

    info = get_build_info()

    assert info == {
        "agent_version": "9.8.7",
        "pilot_build": PILOT_BUILD,
        "source_revision": "abc12345",
        "lock_status": "LOCKED",
    }


def test_qc_report_serializes_build_snapshot() -> None:
    build_info = {
        "agent_version": "0.1.0",
        "pilot_build": "PILOT-TEST.01",
        "source_revision": "deadbeef",
        "lock_status": "UNLOCKED",
    }
    report = QcReport(
        source_file="test.xlsx",
        source_sheet="workbook",
        procedure_code="WORKBOOK",
        rule_ids=[],
        issues=[],
        asset_results=[],
        summary=ReportSummary(0, 0, 0, 0, 0, Severity.PASS),
        build_info=build_info,
    )

    assert report.to_dict()["build_info"] == build_info


def test_source_state_checks_only_runtime_source_scope(monkeypatch) -> None:
    monkeypatch.delenv("FA_QC_SOURCE_REVISION", raising=False)
    calls: list[tuple[str, ...]] = []

    def fake_run_git(*args: str) -> str:
        calls.append(args)
        return "abc12345" if args[0] == "rev-parse" else ""

    monkeypatch.setattr(build_info_module, "_run_git", fake_run_git)

    assert build_info_module._source_state() == ("abc12345", False)
    assert calls[1] == (
        "status",
        "--porcelain",
        "--",
        "src",
        "pyproject.toml",
    )


def test_source_change_keeps_build_unlocked(monkeypatch) -> None:
    monkeypatch.delenv("FA_QC_SOURCE_REVISION", raising=False)

    def fake_run_git(*args: str) -> str:
        if args[0] == "rev-parse":
            return "abc12345"
        return " M src/report/summary.py"

    monkeypatch.setattr(build_info_module, "_run_git", fake_run_git)

    assert get_build_info()["lock_status"] == "UNLOCKED"


def test_untracked_runtime_source_keeps_build_unlocked(monkeypatch) -> None:
    monkeypatch.delenv("FA_QC_SOURCE_REVISION", raising=False)

    def fake_run_git(*args: str) -> str:
        if args[0] == "rev-parse":
            return "abc12345"
        return "?? src/new_runtime_module.py"

    monkeypatch.setattr(build_info_module, "_run_git", fake_run_git)

    assert get_build_info()["lock_status"] == "UNLOCKED"

"""案例库 Lead 批量回归（需本地 ``固定资产质检agent/案例库``）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.case_library import (
    DEFAULT_MAX_WORKBOOK_MB,
    find_case_library_dir,
    iter_case_workbooks,
    should_skip_case_workbook,
)
from ingest.lead_sheet import load_lead_from_workbook
from ingest.rollforward_sheet import load_rollforward_from_workbook
from rules.lead_runner import run_lead_rules
from rules.registry import attach_rule_metadata

_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT = _ROOT / "artifacts" / "case_lead_regression.json"

# B–G 标准 SWP Lead ingest 基线（handoff / lead-qc-rules）
_STANDARD_CRA = 5
_STANDARD_MOV = 4
_STANDARD_EXP = 7


def _case_dir() -> Path | None:
    return find_case_library_dir(_ROOT)


@pytest.fixture(scope="module")
def case_refs():
    case_dir = _case_dir()
    if case_dir is None:
        pytest.skip("案例库目录不存在")
    return iter_case_workbooks(_ROOT, max_mb=DEFAULT_MAX_WORKBOOK_MB)


def test_a_company_workbook_always_skipped(case_refs):
    a_refs = [r for r in case_refs if "A有限" in r.path.name or "A公司" in r.path.name]
    if not a_refs:
        pytest.skip("案例库中无 A 公司底稿")
    for ref in a_refs:
        assert ref.skipped
        assert ref.skip_reason is not None


@pytest.mark.parametrize(
    "label,cra,mov,exp",
    [
        ("B", _STANDARD_CRA, _STANDARD_MOV, _STANDARD_EXP),
        ("C", _STANDARD_CRA, _STANDARD_MOV, _STANDARD_EXP),
        ("D", _STANDARD_CRA, _STANDARD_MOV, _STANDARD_EXP),
        ("E", _STANDARD_CRA, _STANDARD_MOV, _STANDARD_EXP),
        ("F", _STANDARD_CRA, _STANDARD_MOV, _STANDARD_EXP),
        ("G", _STANDARD_CRA, _STANDARD_MOV, _STANDARD_EXP),
    ],
)
def test_case_library_lead_ingest_baseline(label, cra, mov, exp, case_refs):
    targets = [r for r in case_refs if not r.skipped and label in r.path.stem]
    if not targets:
        pytest.skip(f"未找到案例 {label}")
    ref = targets[0]
    assert should_skip_case_workbook(ref.path) is None
    lead = load_lead_from_workbook(ref.path)
    assert lead.source_sheet
    assert len(lead.cra_rows) == cra
    assert len(lead.movement_rows) == mov
    assert len(lead.expectations) == exp


def test_case_library_lead_rules_runnable(case_refs):
    """每条未跳过底稿可跑通 Lead 规则且无异常。"""
    runnable = [r for r in case_refs if not r.skipped]
    if not runnable:
        pytest.skip("无可跑案例库底稿")
    for ref in runnable:
        lead = load_lead_from_workbook(ref.path)
        rf = load_rollforward_from_workbook(ref.path)
        if not rf.source_sheet:
            rf = None
        issues = attach_rule_metadata(run_lead_rules(lead, rollforward=rf))
        assert isinstance(issues, list)


@pytest.mark.skipif(not _ARTIFACT.is_file(), reason="先运行 scripts/run_case_lead_regression.py")
def test_regression_artifact_matches_live_run(case_refs):
    """JSON 回归表与现场跑批一致（防漂移）。"""
    saved = json.loads(_ARTIFACT.read_text(encoding="utf-8"))
    by_file = {r["file"]: r for r in saved["rows"]}
    for ref in case_refs:
        if ref.skipped:
            continue
        lead = load_lead_from_workbook(ref.path)
        live = {
            "cra_rows": len(lead.cra_rows),
            "movement_rows": len(lead.movement_rows),
            "expectations": len(lead.expectations),
            "lead_sheet": lead.source_sheet,
        }
        snap = by_file.get(ref.path.name)
        assert snap is not None, ref.path.name
        assert snap["status"] == "ok"
        for k, v in live.items():
            assert snap[k] == v, f"{ref.path.name}.{k}"

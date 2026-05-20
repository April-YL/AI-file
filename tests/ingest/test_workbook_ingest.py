"""整本底稿结构、后推解析与勾稽单测。"""

from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from ingest.models import SheetKind
from ingest.reconciliation import ReconciliationStatus, run_workbook_reconciliations
from ingest.rollforward_sheet import parse_rollforward_rows
from ingest.workbook_ingest import load_workbook_ingest
from ingest.workbook_structure import StructureIssueCode, analyze_workbook_structure

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def reconciliation_workbook(tmp_path: Path) -> Path:
    """FA list 与 K.01 后推期末合计一致。"""
    path = tmp_path / "recon_demo.xlsx"
    wb = openpyxl.Workbook()

    ws_sum = wb.active
    ws_sum.title = "汇总"
    ws_sum.append(["程序", "工作表", "是否执行"])
    ws_sum.append(["K.01", "K.01", "是"])

    ws_lead = wb.create_sheet("K.00 Lead Sheet")
    ws_lead["A1"] = "客户名称"
    ws_lead["B1"] = "测试客户"
    ws_lead["A2"] = "可容忍误差"
    ws_lead["B2"] = 100000

    ws_fa = wb.create_sheet("FA list")
    ws_fa.append(
        [
            "固定资产编号",
            "固定资产名称",
            "原值",
            "累计折旧",
            "净值",
        ]
    )
    ws_fa.append(["FA-TEST-001", "设备A", 1000, 200, 800])
    ws_fa.append(["FA-TEST-002", "设备B", 2000, 300, 1700])

    ws_rf = wb.create_sheet("K.01 Agree SL to GL")
    ws_rf.append(["固定资产类别", "原值", "累计折旧", "净值"])
    ws_rf.append(["机器设备", 1500, 250, 1250])
    ws_rf.append(["电子设备", 1500, 250, 1250])
    ws_rf.append(["合计", 3000, 500, 2500])

    wb.save(path)
    wb.close()
    return path


@pytest.fixture
def mismatch_workbook(tmp_path: Path) -> Path:
    path = tmp_path / "recon_mismatch.xlsx"
    wb = openpyxl.Workbook()
    ws_fa = wb.active
    ws_fa.title = "FA list"
    ws_fa.append(["固定资产编号", "原值", "累计折旧", "净值"])
    ws_fa.append(["FA-TEST-001", 1000, 100, 900])
    ws_rf = wb.create_sheet("K.01 Agree SL to GL")
    ws_rf.append(["类别", "原值", "累计折旧", "净值"])
    ws_rf.append(["合计", 1000, 100, 800])
    wb.save(path)
    wb.close()
    return path


def test_workbook_structure_core_sheets(reconciliation_workbook: Path):
    structure = analyze_workbook_structure(reconciliation_workbook)
    kinds = set(structure.sheets_by_kind.keys())
    assert "summary" in kinds
    assert "lead" in kinds
    assert "fa_list" in kinds
    assert "rollforward" in kinds
    assert len(structure.program_flow) >= 4
    missing_core = [
        i for i in structure.issues if i.code == StructureIssueCode.MISSING_CORE_SHEET
    ]
    assert not missing_core


def test_rollforward_total_row():
    rows = [
        ("固定资产类别", "原值", "累计折旧", "净值"),
        ("A", 1000, 100, 900),
        ("合计", 1000, 100, 900),
    ]
    rf = parse_rollforward_rows(rows, source_sheet="K.01")
    assert rf.total_row == 3
    assert rf.ending_totals.get("net_value") == Decimal("900")
    assert len(rf.amount_column_bindings) == 3
    assert all(b.period_role.value == "unknown" for b in rf.amount_column_bindings)


def test_rollforward_opening_ending_bindings_and_totals():
    rows = [
        ("类别", "期初原值", "期末原值", "期初累计折旧", "期末累计折旧", "期末净值"),
        ("机器", 1000, 1200, 200, 240, 960),
        ("合计", 1000, 1200, 200, 240, 960),
    ]
    rf = parse_rollforward_rows(rows, source_sheet="K.01")
    roles = {b.period_role.value for b in rf.amount_column_bindings}
    assert "opening" in roles
    assert "ending" in roles
    assert rf.opening_totals.get("original_value") == Decimal("1000")
    assert rf.ending_totals.get("original_value") == Decimal("1200")
    assert rf.ending_totals.get("net_value") == Decimal("960")


def test_reconciliation_match(reconciliation_workbook: Path):
    ctx = load_workbook_ingest(reconciliation_workbook)
    assert ctx.fa_list is not None
    assert ctx.rollforward is not None
    net_checks = [c for c in ctx.reconciliations if c.link_id == "fa_list_rollforward_net"]
    assert len(net_checks) == 1
    assert net_checks[0].status == ReconciliationStatus.MATCH


def test_reconciliation_mismatch(mismatch_workbook: Path):
    ctx = load_workbook_ingest(mismatch_workbook)
    net_checks = [c for c in ctx.reconciliations if c.link_id == "fa_list_rollforward_net"]
    assert net_checks[0].status == ReconciliationStatus.MISMATCH


def test_load_workbook_ingest_on_fixture():
    path = FIXTURES / "workbook_with_lead.xlsx"
    if not path.is_file():
        pytest.skip("fixture missing")
    ctx = load_workbook_ingest(path)
    assert ctx.structure.sheets_by_kind
    assert ctx.fa_list is not None or ctx.fa_list_sheets

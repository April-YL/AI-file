from pathlib import Path

import openpyxl

from ingest.k03_sheet import (
    EXECUTION_PATH_POLICY_REVIEW,
    EXECUTION_PATH_SAP_HIGH,
    EXECUTION_PATH_SAP_MEDIUM,
    EXECUTION_PATH_TOD_BY_ITEM,
    EXECUTION_PATH_TOD_SAMPLING,
    EXECUTION_PATH_UNKNOWN,
    INGEST_DEPTH_DETAILED,
    INGEST_DEPTH_LIGHTWEIGHT,
    INGEST_DEPTH_TEMPLATE_DETECTION,
    K03_BRANCH_DEPRECIATION_TEST,
    K03_BRANCH_POLICY_REVIEW,
    RULE_STATUS_LATER_PHASE,
    load_k03_sheets_from_workbook,
)
from ingest.workbook_ingest import load_workbook_ingest


def _save(wb: openpyxl.Workbook, path: Path) -> Path:
    wb.save(path)
    wb.close()
    return path


def _append_by_item_sheet(wb: openpyxl.Workbook, title: str = "K.03.2 折旧测试"):
    ws = wb.create_sheet(title)
    ws.append(["说明", "TOD-by item 全量折旧测试"])
    ws.append([])
    ws.append(
        [
            "资产编号",
            "资产名称",
            "资产类别",
            "原值",
            "残值率",
            "折旧年限",
            "折旧起始日期",
            "管理层计算折旧",
            "审计重新计算折旧",
            "差异",
            "结论",
            "备注字段",
        ]
    )
    ws.append(
        [
            "FA-TEST-001",
            "设备A",
            "机器设备",
            1200,
            "5%",
            60,
            "2025-01-01",
            228,
            228,
            0,
            "通过",
            "extra",
        ]
    )
    ws.append(["合计", "", "", 1200, "", "", "", 228, 228, 0, "", ""])
    ws.append(["结论", "未见重大差异"])
    return ws


def test_loads_independent_tod_by_item_dataset(tmp_path: Path):
    path = tmp_path / "K1 SWP 固定资产 202YMMDD XYZ公司（By item折旧测试）.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _append_by_item_sheet(wb)
    _save(wb, path)

    datasets = load_k03_sheets_from_workbook(path)

    assert len(datasets) == 1
    ds = datasets[0]
    assert ds.k03_branch == K03_BRANCH_DEPRECIATION_TEST
    assert ds.execution_path == EXECUTION_PATH_TOD_BY_ITEM
    assert ds.ingest_depth == INGEST_DEPTH_DETAILED
    assert ds.rule_status == RULE_STATUS_LATER_PHASE
    assert ds.sheet_name == "K.03.2 折旧测试"
    assert ds.header_rows == [3]
    assert ds.detail_table_range is not None
    assert ds.detail_table_range.start_row == 4
    assert ds.total_rows == [5]
    assert ds.conclusion_area is not None
    assert ds.row_count == 1
    assert ds.column_count == 12
    assert ds.detail_table_ref is not None
    assert ds.detail_table_ref.sheet_name == "K.03.2 折旧测试"
    assert "original_value" in ds.normalized_column_map
    assert "management_depreciation" in ds.normalized_column_map
    assert "audit_recalculated_depreciation" in ds.normalized_column_map
    assert "depreciation_difference" in ds.normalized_column_map
    assert "备注字段" in ds.unmapped_columns
    assert "original_value" in ds.amount_columns
    assert "depreciation_start_date" in ds.date_columns
    assert ds.preview_rows[0]["cell_refs"]["asset_id"] == "A4"
    data = ds.to_dict()
    assert "detail_rows" not in data
    assert data["detail_table_ref"]["start_row"] == 4
    assert data["summary"]["mapped_field_count"] >= 8
    assert len(data["llm_candidate_context"]["preview_rows"]) == 1


def test_standard_k032_tod_uses_structure_not_name_only(tmp_path: Path):
    path = tmp_path / "standard.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("K.03.2 折旧测试TOD")
    ws.append(["程序说明", "抽样 TOD 测试"])
    ws.append(["样本编号", "资产编号", "原值", "本期折旧", "检查程序", "结论"])
    ws.append([1, "FA-TEST-001", 1000, 100, "检查折旧凭证", "通过"])
    ws.append(["结论", "样本测试未见异常"])
    _save(wb, path)

    ds = load_k03_sheets_from_workbook(path)[0]

    assert ds.k03_branch == K03_BRANCH_DEPRECIATION_TEST
    assert ds.execution_path == EXECUTION_PATH_TOD_SAMPLING
    assert ds.ingest_depth == INGEST_DEPTH_LIGHTWEIGHT
    assert ds.rule_status == RULE_STATUS_LATER_PHASE
    assert ds.conclusion_area is not None


def test_standard_k032_can_be_classified_as_tod_by_item_by_structure(tmp_path: Path):
    path = tmp_path / "standard_by_item.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _append_by_item_sheet(wb, title="K.03.2 折旧测试TOD")
    _save(wb, path)

    ds = load_k03_sheets_from_workbook(path)[0]

    assert ds.execution_path == EXECUTION_PATH_TOD_BY_ITEM
    assert ds.ingest_depth == INGEST_DEPTH_DETAILED


def test_unknown_tod_writes_warning_instead_of_forcing_path(tmp_path: Path):
    path = tmp_path / "unknown_tod.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("K.03.2 折旧测试TOD")
    ws.append(["项目", "说明"])
    ws.append(["折旧测试", "结构不足，无法判断执行路径"])
    _save(wb, path)

    ds = load_k03_sheets_from_workbook(path)[0]

    assert ds.execution_path == EXECUTION_PATH_UNKNOWN
    assert "k03_tod_execution_path_not_identified" in ds.warnings


def test_sap_templates_are_detection_only(tmp_path: Path):
    path = tmp_path / "sap.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.03.1 SAP-中精确度"
    ws.append(["SAP 中精确度测试"])
    ws2 = wb.create_sheet("K.03.1 SAP-高精确度")
    ws2.append(["SAP 高精确度测试"])
    _save(wb, path)

    datasets = load_k03_sheets_from_workbook(path)
    paths = {ds.sheet_name: ds.execution_path for ds in datasets}

    assert paths["K.03.1 SAP-中精确度"] == EXECUTION_PATH_SAP_MEDIUM
    assert paths["K.03.1 SAP-高精确度"] == EXECUTION_PATH_SAP_HIGH
    assert all(ds.ingest_depth == INGEST_DEPTH_TEMPLATE_DETECTION for ds in datasets)
    assert all(ds.unsupported_or_later_phase for ds in datasets)


def test_policy_review_is_lightweight_k03_branch(tmp_path: Path):
    path = tmp_path / "policy.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "K.03.3 折旧政策复核"
    ws.append(["说明", "复核折旧政策是否与上期一致"])
    ws.append(["政策描述", "机器设备使用年限 5 年，残值率 5%"])
    ws.append(["结论", "政策未见变化"])
    _save(wb, path)

    ds = load_k03_sheets_from_workbook(path)[0]

    assert ds.k03_branch == K03_BRANCH_POLICY_REVIEW
    assert ds.execution_path == EXECUTION_PATH_POLICY_REVIEW
    assert ds.ingest_depth == INGEST_DEPTH_LIGHTWEIGHT
    assert ds.rule_status == RULE_STATUS_LATER_PHASE
    assert ds.unsupported_or_later_phase is False
    assert ds.llm_candidate_context["candidate_for"] == "depreciation_policy_semantic_review"


def test_workbook_ingest_exposes_k03_sheets(tmp_path: Path):
    path = tmp_path / "workbook.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _append_by_item_sheet(wb)
    ws = wb.create_sheet("K.03.3 折旧政策复核")
    ws.append(["结论", "政策未见变化"])
    _save(wb, path)

    ctx = load_workbook_ingest(path)

    assert len(ctx.k03_sheets) == 2
    branches = {ds.k03_branch for ds in ctx.k03_sheets}
    assert branches == {K03_BRANCH_DEPRECIATION_TEST, K03_BRANCH_POLICY_REVIEW}
    data = ctx.to_dict()
    assert len(data["k03_sheets"]) == 2
    assert "detail_rows" not in data["k03_sheets"][0]


def test_workbook_ingest_does_not_truncate_tod_by_item_detail_rows(tmp_path: Path):
    path = tmp_path / "long_k03_by_item.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("K.03.2 折旧测试")
    ws.append(
        [
            "资产编号",
            "资产名称",
            "原值",
            "残值率",
            "折旧年限",
            "管理层计算折旧",
            "审计重新计算折旧",
            "差异",
        ]
    )
    for idx in range(250):
        ws.append([f"FA-TEST-{idx:03d}", f"设备{idx}", 1200, "5%", 60, 228, 228, 0])
    ws.append(["合计", "", 300000, "", "", 57000, 57000, 0])
    _save(wb, path)

    ctx = load_workbook_ingest(path, max_rows=50)

    assert ctx.k03_sheets[0].execution_path == EXECUTION_PATH_TOD_BY_ITEM
    assert ctx.k03_sheets[0].row_count == 250
    assert ctx.k03_sheets[0].column_count == 8
    assert ctx.k03_sheets[0].total_rows == [252]
    assert ctx.k03_sheets[0].detail_table_ref is not None
    assert ctx.k03_sheets[0].detail_table_ref.end_row == 252
    assert len(ctx.k03_sheets[0].preview_rows) <= 5
    assert len(ctx.k03_sheets[0].llm_candidate_context["preview_rows"]) <= 3
    assert "detail_rows" not in ctx.k03_sheets[0].to_dict()


def test_schema_reserves_sap_plus_tod_sampling_path():
    from ingest.k03_sheet import EXECUTION_PATH_SAP_PLUS_TOD_SAMPLING

    assert EXECUTION_PATH_SAP_PLUS_TOD_SAMPLING == "sap_plus_tod_sampling"

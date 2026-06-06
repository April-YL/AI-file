from pathlib import Path

import openpyxl

from ingest.workbook_ingest import load_workbook_ingest


def _base_workbook(path: Path, *, summary_status: str = "是") -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "汇总"
    ws.append(["程序", "工作表", "是否执行", "不执行的原因"])
    ws.append(["K.02.1 新增测试", "K.02.1 新增测试", summary_status, ""])

    ws_add = wb.create_sheet("新增清单")
    ws_add.append(["固定资产类别", "固定资产编号", "固定资产名称", "入账开始日期", "原值", "新增方式"])
    ws_add.append(["机器设备", "FA-TEST-001", "设备A", "2025-01-01", 1000, "购置"])

    ws_test = wb.create_sheet("K.02.1 新增测试")
    ws_test.append(["记录我们的详细测试所涵盖的总体"])
    ws_test.append(["购置总金额", "", "", "", 1000])
    ws_test.append(["Breakdown中购置金额", "", "", "", 1000])
    ws_test.append(["差异", "", "", "", 0, "Rx", "差异是否需要进一步调查？", "", "否"])
    ws_test.append([])
    ws_test.append(["样本类型", "固定资产类别", "总账账户代码", "固定资产编号", "固定资产名称", "资产原价"])
    ws_test.append(["代表性样本", "机器设备", "2240", "FA-TEST-001", "设备A", 1000])

    ws_sample = wb.create_sheet("K.02.1a 新增选样输出")
    ws_sample.append(["源数据汇总"])
    ws_sample.append(["已上传数据", "", "", "", 1000])
    ws_sample.append(["样本池总体金额", "", "", "", 1000])
    ws_sample.append(["已选取样本"])
    ws_sample.append(["源样本#", "抽样ID", "样本类型", "固定资产类别", "固定资产编号", "固定资产名称", "原值", "新增方式"])
    ws_sample.append([1, 140, "代表性样本", "机器设备", "FA-TEST-001", "设备A", 1000, "购置"])

    wb.save(path)
    return wb


def test_addition_execution_path_complete(tmp_path: Path):
    path = tmp_path / "addition_complete.xlsx"
    wb = _base_workbook(path)
    wb.close()

    ctx = load_workbook_ingest(path)

    assert ctx.addition_test is not None
    assert ctx.addition_test.source_sheet == "K.02.1 新增测试"
    assert ctx.addition_test.amounts["purchase_population_amount"].amount == "1000"
    assert ctx.addition_test.amounts["rollforward_purchase_amount"].amount == "1000"
    assert ctx.addition_test.amounts["difference_amount"].amount == "0"
    assert len(ctx.addition_test.tested_samples) == 1
    assert ctx.addition_test.tested_samples[0].asset_id == "FA-TEST-001"
    assert ctx.addition_test.tested_samples[0].original_value == "1000"
    assert ctx.addition_sample_output is not None
    assert ctx.addition_sample_output.source_sheet == "K.02.1a 新增选样输出"
    assert ctx.addition_sample_output.amounts["uploaded_data_amount"].amount == "1000"
    assert ctx.addition_sample_output.amounts["sample_pool_amount"].amount == "1000"
    assert len(ctx.addition_sample_output.selected_samples) == 1
    assert ctx.addition_sample_output.selected_samples[0].asset_id == "FA-TEST-001"
    assert ctx.addition_sample_output.selected_samples[0].addition_method == "购置"
    assert ctx.addition_execution_path is not None
    assert ctx.addition_execution_path.path_kind == "executed_package_complete"
    assert ctx.addition_execution_path.missing_components == []


def test_addition_execution_path_test_sheet_waiver_note(tmp_path: Path):
    path = tmp_path / "addition_waiver_note.xlsx"
    wb = _base_workbook(path)
    ws = wb["K.02.1 新增测试"]
    ws["A9"] = "本期新增固定资产金额小于 TE，且各单项资产均小于 TT，无性质异常，无需执行详细测试。"
    del wb["K.02.1a 新增选样输出"]
    wb.save(path)
    wb.close()

    ctx = load_workbook_ingest(path)

    assert ctx.addition_execution_path is not None
    assert ctx.addition_execution_path.path_kind == "test_sheet_waiver_note"
    assert "K.02.1a 新增选样输出" in ctx.addition_execution_path.missing_components
    assert ctx.addition_execution_path.test_sheet_waiver_note


def test_addition_execution_path_summary_waived(tmp_path: Path):
    path = tmp_path / "addition_summary_waived.xlsx"
    wb = _base_workbook(path, summary_status="否")
    ws = wb["汇总"]
    ws["D2"] = "本年度无新增固定资产。"
    del wb["新增清单"]
    del wb["K.02.1 新增测试"]
    del wb["K.02.1a 新增选样输出"]
    wb.save(path)
    wb.close()

    ctx = load_workbook_ingest(path)

    assert ctx.addition_execution_path is not None
    assert ctx.addition_execution_path.path_kind == "summary_waived"
    assert ctx.addition_execution_path.summary_waiver_reason == "本年度无新增固定资产。"

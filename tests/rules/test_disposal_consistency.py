from ingest.disposal_test_sheet import (
    DisposalExecutionPathDataset,
    DisposalSampleOutputDataset,
    DisposalSampleRow,
    DisposalTestSheetDataset,
    DisposalTestedSampleRow,
    DisposalAmountItem,
)
from rules.disposal_consistency import (
    build_disposal_consistency_preview,
    check_disposal_sample_match,
)
from rules.models import Severity


def _executed_path() -> DisposalExecutionPathDataset:
    return DisposalExecutionPathDataset(
        path_kind="executed_package_complete",
        recognition_confidence=0.9,
        summary_status="yes",
        disposal_list_sheet="处置清单",
        disposal_test_sheet="K.02.2 处置测试",
        disposal_sample_output_sheet="K.02.2a 处置选样输出",
    )


def test_disposal_sample_match_flags_sample_type_mismatch_only():
    disposal_test = DisposalTestSheetDataset(
        source_file="case-j.xlsx",
        source_sheet="K.02.2 处置测试",
        tested_samples=[
            DisposalTestedSampleRow(
                source_row=69,
                sample_type="关键项（key item）",
                asset_id="10300002409",
                asset_name="红外光谱仪",
                net_value="95982.10",
            )
        ],
    )
    disposal_sample_output = DisposalSampleOutputDataset(
        source_file="case-j.xlsx",
        source_sheet="K.02.2a 处置选样输出",
        amounts={
            "key_item_count": DisposalAmountItem(
                label="关键项数量",
                amount="0",
                source_row=50,
                source_column=6,
            )
        },
        selected_samples=[
            DisposalSampleRow(
                source_row=102,
                sample_type="代表性样本",
                asset_id="10300002409",
                asset_name="红外光谱仪",
                net_value="95982.1",
            ),
            DisposalSampleRow(
                source_row=104,
                sample_type="替换样本",
                asset_id="10500000194",
                asset_name="燃气灶",
                net_value="48.7",
            ),
        ],
    )

    preview = build_disposal_consistency_preview(
        disposal_test,
        disposal_sample_output,
        execution_path=_executed_path(),
    )
    assert preview.selected_count == 1
    assert preview.tested_count == 1
    assert preview.matched_count == 1
    assert preview.unmatched_selected == []
    assert len(preview.sample_type_mismatches) == 1

    issues = check_disposal_sample_match(
        disposal_test,
        disposal_sample_output,
        execution_path=_executed_path(),
    )
    assert {issue.field for issue in issues} == {"sample_type", "key_item_count"}
    assert all(issue.severity == Severity.NEED_REVIEW for issue in issues)
    assert any("样本类型不一致" in issue.message for issue in issues)
    assert any("关键项数量" in issue.message for issue in issues)


def test_disposal_sample_match_skips_when_summary_waived():
    path = DisposalExecutionPathDataset(
        path_kind="summary_waived",
        recognition_confidence=0.8,
        summary_status="no",
        summary_waiver_reason="实际处置金额小于TT，不进行本次测试",
        disposal_list_sheet="处置清单",
    )
    issues = check_disposal_sample_match(
        DisposalTestSheetDataset(
            source_file="case-g.xlsx",
            source_sheet="K.02.2 处置测试",
            tested_samples=[
                DisposalTestedSampleRow(
                    source_row=10,
                    sample_type="关键项",
                    asset_id="FA-D-001",
                    net_value="100",
                )
            ],
        ),
        None,
        execution_path=path,
    )
    assert issues == []

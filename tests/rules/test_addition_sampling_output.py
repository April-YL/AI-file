from ingest.addition_test_sheet import (
    AdditionAmountItem,
    AdditionExecutionPathDataset,
    AdditionParameterItem,
    AdditionSampleOutputDataset,
    AdditionTestSheetDataset,
    AdditionTestedSampleRow,
)
from ingest.field_mapping import FieldMapping
from ingest.lead_sheet import CraAssertionRow, LeadBasicInfoField, LeadSheetDataset
from ingest.records import AssetRecord, FaListDataset
from rules.addition_runner import run_addition_rules
from rules.addition_sampling_output import (
    check_addition_sample_pool_purchase_amount_match,
    check_addition_sample_replacement_reason,
    check_addition_sampling_assertions_scope,
    check_addition_sampling_te_cra_consistency,
)
from rules.models import Severity


def _addition_list(amounts: list[str]) -> FaListDataset:
    return FaListDataset(
        source_file="case.xlsx",
        source_sheet="新增清单",
        mapped_fields=[
            FieldMapping("original_value", "原值", 1),
            FieldMapping("addition_method", "新增方式", 2),
        ],
        records=[
            AssetRecord(source_row=i + 2, original_value=amount, addition_method="购置")
            for i, amount in enumerate(amounts)
        ],
    )


def _sample_output(
    *,
    sample_pool: str = "100",
    te: str = "100",
    cra: str = "最低",
    assertions: str = "存在/发生",
) -> AdditionSampleOutputDataset:
    return AdditionSampleOutputDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1a 新增选样输出",
        parameters={
            "te": AdditionParameterItem("可容忍误差（TE）", te, 15, 6),
            "covered_assertions": AdditionParameterItem("测试涵盖的认定", assertions, 16, 6),
            "cra": AdditionParameterItem("综合风险评估", cra, 18, 6),
        },
        amounts={
            "sample_pool_amount": AdditionAmountItem("样本池总体金额", sample_pool, 41, 6),
        },
    )


def _lead(
    *,
    te: str = "100",
    rows: list[CraAssertionRow] | None = None,
) -> LeadSheetDataset:
    return LeadSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.00 Lead Sheet",
        basic_info_fields=[
            LeadBasicInfoField(field_key="te", label="TE", value=te, source_row=8, source_col=4),
        ],
        cra_rows=rows
        or [
            CraAssertionRow(assertion="存在性/发生 (E/O)", cra="Minimal", source_row=16),
        ],
    )


def test_sample_pool_matches_purchase_amount():
    issues = check_addition_sample_pool_purchase_amount_match(
        _addition_list(["40", "60"]),
        _sample_output(sample_pool="100"),
    )

    assert issues == []


def test_sample_pool_mismatch_fails():
    issues = check_addition_sample_pool_purchase_amount_match(
        _addition_list(["40", "60"]),
        _sample_output(sample_pool="110"),
    )

    assert len(issues) == 1
    assert issues[0].severity == Severity.FAIL
    assert issues[0].rule_id == "addition_sample_pool_purchase_amount_match"


def test_sampling_rules_are_skipped_when_addition_is_summary_waived():
    issues = run_addition_rules(
        None,
        addition_sample_output=_sample_output(sample_pool="110", te="200"),
        addition_execution_path=AdditionExecutionPathDataset(
            path_kind="summary_waived",
            recognition_confidence=0.82,
            summary_status="no",
            summary_waiver_reason="新增购置金额小于SAD。",
            missing_components=["K.02.1 新增测试"],
        ),
    )

    assert issues == []


def test_sampling_te_and_chinese_cra_match_lead_english_cra():
    issues = check_addition_sampling_te_cra_consistency(
        _sample_output(te="100", cra="最低", assertions="存在/发生"),
        _lead(te="100"),
    )

    assert issues == []


def test_sampling_te_and_cra_mismatch_fail():
    lead = _lead(
        te="213730",
        rows=[
            CraAssertionRow(assertion="存在性/发生 (E/O)", cra="Minimal", source_row=16),
            CraAssertionRow(assertion="计价/计量（V/M）", cra="Low", source_row=17),
            CraAssertionRow(assertion="权利和义务（R&O）", cra="Minimal", source_row=18),
        ],
    )

    issues = check_addition_sampling_te_cra_consistency(
        _sample_output(
            te="241890",
            cra="最低",
            assertions="存在/发生, 计量/计价, 权利与义务",
        ),
        lead,
    )

    assert {issue.field for issue in issues} == {"te", "cra"}
    assert all(issue.severity == Severity.FAIL for issue in issues)


def test_sampling_assertions_with_completeness_need_review():
    issues = check_addition_sampling_assertions_scope(
        _sample_output(assertions="完整性, 存在/发生, 计量/计价")
    )

    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW


def test_replacement_sample_requires_reason():
    dataset = AdditionTestSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1 新增测试",
        tested_samples=[
            AdditionTestedSampleRow(
                source_row=34,
                sample_type="替换样本",
                asset_id="FA-001",
                evidence_description="合同与发票",
            )
        ],
    )

    issues = check_addition_sample_replacement_reason(dataset)

    assert len(issues) == 1
    assert issues[0].severity == Severity.NEED_REVIEW


def test_replacement_sample_with_original_sample_reason_passes():
    dataset = AdditionTestSheetDataset(
        source_file="case.xlsx",
        source_sheet="K.02.1 新增测试",
        tested_samples=[
            AdditionTestedSampleRow(
                source_row=34,
                sample_type="替换样本",
                asset_id="FA-001",
                evidence_description="原样本为自动结转凭证，不代表实际事项，因此启用替换样本。",
            )
        ],
    )

    assert check_addition_sample_replacement_reason(dataset) == []

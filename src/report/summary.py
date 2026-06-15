from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ingest.models import AssetRecord
from report.manual_review import ManualReviewSection
from rules.models import QcIssue, Severity

if TYPE_CHECKING:
    from llm.review import LlmEnrichment

_SEVERITY_RANK = {
    Severity.FAIL: 4,
    Severity.NEED_REVIEW: 3,
    Severity.WARN: 2,
    Severity.PASS: 1,
}


def worst_severity(severities: list[Severity]) -> Severity:
    if not severities:
        return Severity.PASS
    return max(severities, key=lambda s: _SEVERITY_RANK[s])


@dataclass
class AssetResult:
    asset_id: str
    severity: Severity
    issue_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "severity": self.severity.value,
            "issue_count": self.issue_count,
        }


@dataclass
class ReportSummary:
    total_records: int
    pass_count: int
    warn_count: int
    fail_count: int
    need_review_count: int
    overall_severity: Severity
    by_rule: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "need_review_count": self.need_review_count,
            "overall_severity": self.overall_severity.value,
            "by_rule": self.by_rule,
        }


@dataclass
class QcReport:
    """固定资产质检报告。

    ``summary_sheet_section``：汇总页 + AE-003；
    ``lead_sheet_section``：K.00 Lead + 基准信息/摘录规则摘要；
    ``rollforward_sheet_section``：K.01 后推 + 六区块识别 + P0 规则摘要。
    ``addition_sheet_section``：K.02 新增测试 + K.02.1a 选样输出 + 一致性预览。
    ``ingest_review_section``：读取结果复核提示（LLM 辅助，不改变规则结论）。
    """

    source_file: str
    source_sheet: str
    procedure_code: str
    rule_ids: list[str]
    issues: list[QcIssue]
    asset_results: list[AssetResult]
    summary: ReportSummary
    llm_enrichment: LlmEnrichment | None = None
    manual_review_sections: list[ManualReviewSection] = field(default_factory=list)
    summary_sheet_section: dict[str, Any] | None = None
    lead_sheet_section: dict[str, Any] | None = None
    rollforward_sheet_section: dict[str, Any] | None = None
    addition_sheet_section: dict[str, Any] | None = None
    ingest_review_section: dict[str, Any] | None = None
    runtime_timings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source_file": self.source_file,
            "source_sheet": self.source_sheet,
            "procedure_code": self.procedure_code,
            "rule_ids": self.rule_ids,
            "issues": [i.to_dict() for i in self.issues],
            "asset_results": [a.to_dict() for a in self.asset_results],
            "summary": self.summary.to_dict(),
        }
        if self.summary_sheet_section is not None:
            data["summary_sheet_section"] = self.summary_sheet_section
        if self.lead_sheet_section is not None:
            data["lead_sheet_section"] = self.lead_sheet_section
        if self.rollforward_sheet_section is not None:
            data["rollforward_sheet_section"] = self.rollforward_sheet_section
        if self.addition_sheet_section is not None:
            data["addition_sheet_section"] = self.addition_sheet_section
        if self.ingest_review_section is not None:
            data["ingest_review_section"] = self.ingest_review_section
        if self.llm_enrichment is not None:
            data["llm_enrichment"] = self.llm_enrichment.to_dict()
        if self.manual_review_sections:
            data["manual_review_sections"] = [
                s.to_dict() if hasattr(s, "to_dict") else s
                for s in self.manual_review_sections
            ]
        if self.runtime_timings:
            data["runtime_timings"] = self.runtime_timings
        return data


def build_report(
    *,
    source_file: str,
    source_sheet: str,
    procedure_code: str,
    rule_ids: list[str],
    records: list[AssetRecord],
    issues: list[QcIssue],
    summary_sheet_section: dict[str, Any] | None = None,
    lead_sheet_section: dict[str, Any] | None = None,
    rollforward_sheet_section: dict[str, Any] | None = None,
    addition_sheet_section: dict[str, Any] | None = None,
    ingest_review_section: dict[str, Any] | None = None,
) -> QcReport:
    issues_by_asset: dict[str, list[QcIssue]] = {}
    sheet_level: list[QcIssue] = []

    for issue in issues:
        if issue.asset_id:
            issues_by_asset.setdefault(issue.asset_id, []).append(issue)
        else:
            sheet_level.append(issue)

    asset_results: list[AssetResult] = []
    pass_count = warn_count = fail_count = need_review_count = 0

    seen_assets: set[str] = set()
    for record in records:
        aid = record.asset_id or record.identity()
        seen_assets.add(aid)
        row_issues = issues_by_asset.get(aid, [])
        sev = worst_severity([i.severity for i in row_issues])
        asset_results.append(
            AssetResult(
                asset_id=aid,
                severity=sev,
                issue_count=len(row_issues),
            )
        )
        if sev == Severity.PASS:
            pass_count += 1
        elif sev == Severity.WARN:
            warn_count += 1
        elif sev == Severity.FAIL:
            fail_count += 1
        else:
            need_review_count += 1

    for issue in sheet_level:
        if issue.severity == Severity.WARN:
            warn_count += 1
        elif issue.severity == Severity.FAIL:
            fail_count += 1
        elif issue.severity == Severity.NEED_REVIEW:
            need_review_count += 1

    by_rule: dict[str, int] = {}
    for issue in issues:
        by_rule[issue.rule_id] = by_rule.get(issue.rule_id, 0) + 1

    all_severities = [i.severity for i in issues]
    if records and not issues:
        overall = Severity.PASS
    else:
        overall = worst_severity(all_severities) if all_severities else Severity.PASS

    summary = ReportSummary(
        total_records=len(records),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        need_review_count=need_review_count,
        overall_severity=overall,
        by_rule=by_rule,
    )

    return QcReport(
        source_file=source_file,
        source_sheet=source_sheet,
        procedure_code=procedure_code,
        rule_ids=rule_ids,
        issues=issues,
        asset_results=asset_results,
        summary=summary,
        summary_sheet_section=summary_sheet_section,
        lead_sheet_section=lead_sheet_section,
        rollforward_sheet_section=rollforward_sheet_section,
        addition_sheet_section=addition_sheet_section,
        ingest_review_section=ingest_review_section,
    )

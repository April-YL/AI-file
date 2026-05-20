from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ingest.lead_sheet import LeadSheetDataset


@dataclass
class ManualReviewSection:
    """质检报告中供人工核对的数据摘录区块。"""

    dict_rule_code: str
    rule_id: str
    title: str
    checklist_prompt: str
    instruction: str
    items: list[dict[str, Any]] = field(default_factory=list)
    source_sheet: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dict_rule_code": self.dict_rule_code,
            "rule_id": self.rule_id,
            "title": self.title,
            "checklist_prompt": self.checklist_prompt,
            "instruction": self.instruction,
            "source_sheet": self.source_sheet,
            "items": self.items,
            "notes": self.notes,
        }


def build_manual_review_sections(
    lead: LeadSheetDataset | None,
) -> list[ManualReviewSection]:
    if lead is None:
        return [
            ManualReviewSection(
                dict_rule_code="AE-001",
                rule_id="materiality_consistency",
                title="PM/TE/SAD 与 Canvas 一致性",
                checklist_prompt="◆PM/TE/SAD与Canvas中最终的结果一致",
                instruction="底稿中未摘录到 Lead 表数据；请打开 K.00 Lead Sheet 与 Canvas/A3 人工逐项核对。",
                notes=["未加载 Lead 工作表（仅 CSV 或无底稿 Excel）。"],
            ),
            ManualReviewSection(
                dict_rule_code="AE-002",
                rule_id="risk_threshold_consistency",
                title="各认定 CRA、TT",
                checklist_prompt="◆各认定CRA正确，TT取值正确",
                instruction="请人工核对固定资产及相关认定的 CRA、TT。",
                notes=["未加载 Lead 工作表。"],
            ),
        ]

    sheet = lead.source_sheet or "K.00 Lead Sheet"
    sections: list[ManualReviewSection] = []

    mat_items = [c.to_dict(sheet) for c in lead.materiality]
    sections.append(
        ManualReviewSection(
            dict_rule_code="AE-001",
            rule_id="materiality_consistency",
            title="PM/TE/SAD 与 Canvas 一致性",
            checklist_prompt="◆PM/TE/SAD与Canvas中最终的结果一致",
            instruction=(
                "下表为从底稿 Lead 表自动摘录的数值；请将「底稿值」与 Canvas/A3 最终结果对比，"
                "在纸质或电子复核记录中勾选一致/差异说明。Agent 无法直连 Canvas，不做自动比对。"
            ),
            source_sheet=sheet,
            items=mat_items,
            notes=list(lead.notes) if not mat_items else [],
        )
    )

    cra_items = [r.to_dict(sheet) for r in lead.cra_rows]
    sections.append(
        ManualReviewSection(
            dict_rule_code="AE-002",
            rule_id="risk_threshold_consistency",
            title="各认定 CRA、TT",
            checklist_prompt="◆各认定CRA正确，TT取值正确",
            instruction=(
                "下表为从 Lead 表摘录的认定级 CRA、TT；请与 Canvas/项目组风险底稿核对是否正确。"
                "固定资产认定行应重点关注。"
            ),
            source_sheet=sheet,
            items=cra_items,
            notes=[] if cra_items else ["未识别 CRA/TT 表头，请人工打开 Lead 表核对。"],
        )
    )

    return sections

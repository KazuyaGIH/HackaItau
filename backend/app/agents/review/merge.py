"""Merge validators (A) + AI review (B) → ReviewOutput (ARCHITECTURE.md §6.4).

reexecution_required só com finding high + owner + required_action conhecido. Findings da rodada anterior que
não reaparecem (mesmo code+owner) entram como `resolved`, para o relatório mostrar o que o rework corrigiu.
"""

from app.agents.review.remediations import rework_for
from app.core.schemas.outputs import Finding, ReviewOutput

_POLICY_CODES = {"POLICY_THRESHOLD_BREACH", "PRODUCT_UNKNOWN", "TENOR_OUT_OF_RANGE", "STRUCTURE_EXCEEDS_REQUEST"}


def merge_review(
    validator_findings: list[Finding],
    ai_findings: list[Finding],
    overall_assessment: str,
    *,
    rework_round: int,
    previous: ReviewOutput | None = None,
) -> ReviewOutput:
    current = list(validator_findings) + [f.model_copy(update={"required_action": None}) for f in ai_findings]
    keys = {(f.code, f.owner_agent) for f in current}
    resolved = [
        f.model_copy(update={"status": "resolved"})
        for f in (previous.findings if previous else [])
        if f.status == "open" and (f.code, f.owner_agent) not in keys
    ]
    findings = current + resolved

    rework = rework_for(current)
    open_material = [f for f in current if f.status == "open" and f.severity != "info"]
    if rework:
        status = "rework_required"
    elif open_material:
        status = "passed_with_findings"
    else:
        status = "passed"
    return ReviewOutput(
        review_status=status,  # type: ignore[arg-type]
        findings=findings,
        grounding_ok=not any(f.code == "EVIDENCE_NOT_FOUND" for f in current),
        policy_ok=not any(f.code in _POLICY_CODES for f in current),
        reexecution_required=rework is not None,
        reopen_agent=rework[0] if rework else None,
        rework_round=rework_round,
        overall_assessment=overall_assessment,
    )

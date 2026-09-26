"""finding.code → ação de rework conhecida (ARCHITECTURE.md §6.4). Só entradas aqui disparam rework."""

from app.core.schemas.agent import ReworkInstruction
from app.core.schemas.outputs import Finding

ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED = "ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED"
RISK_IGNORED_BY_STRUCTURE = "RISK_IGNORED_BY_STRUCTURE"

REMEDIATIONS: dict[str, str] = {
    ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED: "recalculate_with_historical_baseline",
    RISK_IGNORED_BY_STRUCTURE: "address_risks_in_structure",
}


def required_action(code: str) -> str | None:
    return REMEDIATIONS.get(code)


def _params(f: Finding) -> dict:
    if f.code == ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED:
        return {"baseline_policy": "historical"}
    if f.code == RISK_IGNORED_BY_STRUCTURE:
        return {"risk_codes": [c for c in f.message.split("`") if c.isupper()]}
    return {}


def rework_for(findings: list[Finding]) -> tuple[str, ReworkInstruction] | None:
    """Escolhe o rework: 1º finding high, aberto, com owner e ação conhecida. Um só por rodada."""
    for f in findings:
        if f.severity == "high" and f.status == "open" and f.owner_agent and f.required_action:
            return f.owner_agent, ReworkInstruction(
                finding_ids=[f.id], required_action=f.required_action, params=_params(f), message=f.message
            )
    return None

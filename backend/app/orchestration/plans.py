"""Plano fixo por intent (ARCHITECTURE.md §4): ordem dos agentes, instrução TRUSTED e projeção compacta de inputs.

`input_projection` é a única ponte entre outputs upstream e o próximo agente — CÓDIGO decide o que passa
(context minimization). Structuring recebe só Eligibility/Risk compactos; nunca sources brutos.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.schemas.agent import AgentResult
from app.core.schemas.outputs import EligibilityOutput, InterpretedDemand, RiskOutput, StructuringOutput

Projection = Callable[[InterpretedDemand, dict[str, AgentResult]], dict[str, Any]]

ELIGIBILITY, RISK, STRUCTURING, REVIEW = "agro_eligibility", "agro_credit_risk", "agro_structuring", "credit_review"


@dataclass(frozen=True)
class PlanStep:
    agent_id: str
    instruction: str
    upstream: tuple[str, ...]
    project: Projection


def _demand(d: InterpretedDemand) -> dict[str, Any]:
    return {"requested_amount": d.requested_amount, "purpose": d.purpose, "crop": d.crop, "cycle": d.cycle}


def _eligibility_compact(results: dict[str, AgentResult]) -> dict[str, Any]:
    r = results.get(ELIGIBILITY)
    if not r:
        return {}
    e = EligibilityOutput.model_validate(r.output)
    return {
        "status": e.status,
        "product_fit": e.product_fit,
        "warnings": [w.model_dump() for w in e.warnings],
        "missing_items": [m.model_dump() for m in e.missing_items],
        "output_id": r.output_id,
    }


def _risk_compact(results: dict[str, AgentResult]) -> dict[str, Any]:
    r = results.get(RISK)
    if not r:
        return {}
    ro = RiskOutput.model_validate(r.output)
    return {
        "baseline_policy": ro.baseline_policy,
        "repayment_capacity": ro.repayment_capacity,
        "risk_summary": ro.risk_summary,
        "metrics": {
            "calculation_id": ro.metrics.calculation_id,
            "coverage": ro.metrics.coverage,
            "pro_forma_leverage": ro.metrics.pro_forma_leverage,
            "classification": ro.metrics.classification,
        },
        "stress_scenarios": [
            {"scenario_id": s.scenario_id, "label": s.label, "coverage": s.coverage, "classification": s.classification}
            for s in ro.stress_scenarios
        ],
        "main_risks": [i.model_dump() for i in ro.main_risks],
        "mitigants": [i.model_dump() for i in ro.mitigants],
        "output_id": r.output_id,
    }


def _structuring_compact(results: dict[str, AgentResult]) -> dict[str, Any]:
    r = results.get(STRUCTURING)
    if not r:
        return {}
    so = StructuringOutput.model_validate(r.output)
    return {
        "alternatives": [
            {
                "id": a.id,
                "name": a.name,
                "product_id": a.product_id,
                "amount": a.amount,
                "tenor_months": a.tenor_months,
                "guarantees": a.guarantees,
                "conditions": a.conditions,
                "addressed_risk_codes": a.addressed_risk_codes,
            }
            for a in so.alternatives
        ],
        "output_id": r.output_id,
    }


def project_eligibility(d: InterpretedDemand, results: dict[str, AgentResult]) -> dict[str, Any]:
    return _demand(d)


def project_risk(d: InterpretedDemand, results: dict[str, AgentResult]) -> dict[str, Any]:
    return _demand(d) | {"eligibility": _eligibility_compact(results)}


def project_structuring(d: InterpretedDemand, results: dict[str, AgentResult]) -> dict[str, Any]:
    return _demand(d) | {"eligibility": _eligibility_compact(results), "risk": _risk_compact(results)}


def project_review(d: InterpretedDemand, results: dict[str, AgentResult]) -> dict[str, Any]:
    return _demand(d) | {
        "eligibility": _eligibility_compact(results),
        "risk": _risk_compact(results),
        "structuring": _structuring_compact(results),
    }


CREDITO_AGRO: tuple[PlanStep, ...] = (
    PlanStep(
        ELIGIBILITY,
        "Verifique elegibilidade e completude documental para a operação descrita nos inputs. Liste itens faltantes.",
        (),
        project_eligibility,
    ),
    PlanStep(
        RISK,
        "Interprete as métricas e cenários já calculados (CALC-*). Não recalcule; explique riscos, mitigantes, "
        "premissas qualitativas e incertezas citando evidências.",
        (ELIGIBILITY,),
        project_risk,
    ),
    PlanStep(
        STRUCTURING,
        "Proponha 2–3 alternativas comparáveis de estrutura usando só o catálogo, a política e os outputs compactos. "
        "Não ranqueie nem marque preferida. Trate os riscos listados em addressed_risk_codes.",
        (ELIGIBILITY, RISK),
        project_structuring,
    ),
    PlanStep(
        REVIEW,
        "Red team: questione premissas frágeis, riscos ignorados, conclusões excessivas e inconsistências qualitativas "
        "nos outputs upstream. Cada finding precisa de evidence_ids existentes.",
        (ELIGIBILITY, RISK, STRUCTURING),
        project_review,
    ),
)

PLANS: dict[str, tuple[PlanStep, ...]] = {"credito_agro": CREDITO_AGRO}


def plan_for(intent: str) -> tuple[PlanStep, ...]:
    return PLANS.get(intent, CREDITO_AGRO)


def dependents_of(plan: tuple[PlanStep, ...], agent_id: str) -> list[str]:
    """Agentes que consomem `agent_id` (direta ou transitivamente), na ordem do plano. Review fica de fora."""
    reopened = {agent_id}
    out = []
    for step in plan:
        if step.agent_id == REVIEW or step.agent_id == agent_id:
            continue
        if reopened & set(step.upstream):
            reopened.add(step.agent_id)
            out.append(step.agent_id)
    return out

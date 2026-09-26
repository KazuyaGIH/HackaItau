"""Handlers das tools `calc`. Premissas chegam prontas (risk/baseline.py); aqui só se calcula e registra CALC-*."""

from typing import Any

from app.calculations.credit_metrics import FORMULA, MetricInputs, credit_metrics
from app.calculations.policy_params import load_policy_params
from app.calculations.stress import run_scenarios, worst_class
from app.core.schemas.evidence import CalculationRecord, calculation_id
from app.tools.deps import ToolDeps
from app.tools.registry import AssumptionSetParams, CreditMetricsParams, StressParams, register_handler

CALC_CREDIT_METRICS = "credit_metrics"
CALC_STRESS = "stress"


def _inputs(a: AssumptionSetParams) -> MetricInputs:
    return MetricInputs(
        planted_area_hectares=a.planted_area_hectares,
        productivity=a.productivity,
        price=a.price,
        cost_per_hectare=a.cost_per_hectare,
        requested_amount=a.requested_amount,
        net_debt=a.net_debt,
        ebitda=a.ebitda,
    )


async def calculate_credit_metrics(params: dict[str, Any], deps: ToolDeps) -> CalculationRecord:
    p = CreditMetricsParams(**params)
    policy = load_policy_params()
    inputs = _inputs(p.assumptions)
    m = credit_metrics(inputs, policy.thresholds)
    return CalculationRecord(
        id=calculation_id(CALC_CREDIT_METRICS, deps.round),
        name=CALC_CREDIT_METRICS,
        formula=FORMULA,
        inputs=inputs.model_dump() | {"baseline_policy": p.assumptions.baseline_policy},
        input_sources=dict(p.assumptions.sources),
        thresholds_source_ids=list(p.assumptions.thresholds_source_ids or policy.thresholds.kb_ids()),
        outputs=m.model_dump(),
        classification=m.classification,
        computed_by_agent=deps.agent_id,
        round=deps.round,
    )


async def run_stress_scenarios(params: dict[str, Any], deps: ToolDeps) -> CalculationRecord:
    p = StressParams(**params)
    policy = load_policy_params()
    scenarios = [policy.scenario(sid) for sid in p.scenario_ids]  # ids desconhecidos → KeyError (não inventa cenário)
    inputs = _inputs(p.assumptions)
    outcomes = run_scenarios(inputs, scenarios, policy.thresholds)
    return CalculationRecord(
        id=calculation_id(CALC_STRESS, deps.round),
        name=CALC_STRESS,
        formula="para cada cenário: inputs_choque = inputs * (1 + shock); credit_metrics(inputs_choque)",
        inputs=inputs.model_dump() | {"scenario_ids": p.scenario_ids, "baseline_policy": p.assumptions.baseline_policy},
        input_sources=dict(p.assumptions.sources),
        thresholds_source_ids=list(p.assumptions.thresholds_source_ids or policy.thresholds.kb_ids())
        + [policy.thresholds.scenarios_kb_id()],
        outputs={"scenarios": [o.model_dump(exclude={"inputs"}) for o in outcomes]},
        classification=worst_class(outcomes),
        computed_by_agent=deps.agent_id,
        round=deps.round,
    )


CALC_HANDLERS = {
    "calculate_credit_metrics": calculate_credit_metrics,
    "run_stress_scenarios": run_stress_scenarios,
}


def install_calc_handlers() -> None:
    for name, handler in CALC_HANDLERS.items():
        register_handler(name, handler)

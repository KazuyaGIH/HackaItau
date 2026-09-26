"""Cenários de stress — funções puras. Choques fixos vêm de policies.json; cada cenário re-executa credit_metrics."""

from pydantic import BaseModel

from app.calculations.credit_metrics import CoverageClass, MetricInputs, credit_metrics
from app.calculations.policy_params import StressScenario, Thresholds

SHOCKABLE = ("price", "productivity", "cost_per_hectare")


class ScenarioOutcome(BaseModel):
    scenario_id: str
    label: str
    shocks: dict[str, float]
    inputs: MetricInputs
    coverage: float
    expected_cash_generation: float
    pro_forma_leverage: float
    classification: CoverageClass


def apply_shocks(base: MetricInputs, shocks: dict[str, float]) -> MetricInputs:
    values = base.model_dump()
    for name, pct in shocks.items():
        if name not in SHOCKABLE:
            raise ValueError(f"choque não permitido: {name}")
        values[name] = round(values[name] * (1 + pct), 6)
    return MetricInputs(**values)


def run_scenarios(base: MetricInputs, scenarios: list[StressScenario], t: Thresholds) -> list[ScenarioOutcome]:
    out = []
    for sc in scenarios:
        shocked = apply_shocks(base, sc.shocks)
        m = credit_metrics(shocked, t)
        out.append(
            ScenarioOutcome(
                scenario_id=sc.scenario_id,
                label=sc.label,
                shocks=sc.shocks,
                inputs=shocked,
                coverage=m.coverage,
                expected_cash_generation=m.expected_cash_generation,
                pro_forma_leverage=m.pro_forma_leverage,
                classification=m.coverage_class,
            )
        )
    return out


def worst_class(outcomes: list[ScenarioOutcome]) -> CoverageClass:
    order: list[CoverageClass] = ["comfortable", "reduced_buffer", "attention_required", "insufficient"]
    return max((o.classification for o in outcomes), key=order.index, default="comfortable")

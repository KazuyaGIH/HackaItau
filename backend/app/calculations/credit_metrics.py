"""Métricas de crédito — funções puras (ARCHITECTURE.md §13). Sem I/O, sem LLM."""

from typing import Literal

from pydantic import BaseModel

from app.calculations.policy_params import Thresholds

CoverageClass = Literal["comfortable", "reduced_buffer", "attention_required", "insufficient"]
RepaymentCapacity = Literal["adequate", "adequate_with_conditions", "tight", "insufficient"]
RiskSummary = Literal["low", "moderate", "elevated", "high"]

FORMULA = (
    "expected_revenue = planted_area_hectares * productivity * price; "
    "crop_cost = planted_area_hectares * cost_per_hectare; "
    "expected_cash_generation = expected_revenue - crop_cost; "
    "net_debt_ebitda = net_debt / ebitda; "
    "pro_forma_leverage = (net_debt + requested_amount) / ebitda; "
    "coverage = expected_cash_generation / requested_amount"
)


class MetricInputs(BaseModel):
    planted_area_hectares: float
    productivity: float
    price: float
    cost_per_hectare: float
    requested_amount: float
    net_debt: float
    ebitda: float


class MetricOutputs(BaseModel):
    expected_revenue: float
    crop_cost: float
    expected_cash_generation: float
    net_debt_ebitda: float
    pro_forma_leverage: float
    coverage: float
    coverage_class: CoverageClass
    leverage_within_limit: bool
    pro_forma_within_limit: bool
    classification: str  # coverage_class + "|leverage_ok" / "|leverage_breach"


def classify_coverage(coverage: float, t: Thresholds) -> CoverageClass:
    c = t.coverage
    if coverage >= c.comfortable_min:
        return "comfortable"
    if coverage >= c.reduced_buffer_min:
        return "reduced_buffer"
    if coverage >= c.attention_required_min:
        return "attention_required"
    return "insufficient"


def repayment_capacity(coverage: float, pro_forma_within_limit: bool, t: Thresholds) -> RepaymentCapacity:
    r = t.repayment_capacity
    if coverage >= r.adequate_min_coverage and pro_forma_within_limit:
        return "adequate"
    if coverage >= r.adequate_with_conditions_min_coverage:
        return "adequate_with_conditions"
    if coverage >= r.tight_min_coverage:
        return "tight"
    return "insufficient"


def risk_summary(capacity: RepaymentCapacity, worst_stress_class: CoverageClass) -> RiskSummary:
    if capacity == "insufficient" or worst_stress_class == "insufficient":
        return "high"
    if capacity == "tight" or worst_stress_class == "attention_required":
        return "elevated"
    if capacity == "adequate_with_conditions" or worst_stress_class == "reduced_buffer":
        return "moderate"
    return "low"


def credit_metrics(i: MetricInputs, t: Thresholds) -> MetricOutputs:
    if i.ebitda <= 0 or i.requested_amount <= 0:
        raise ValueError("ebitda e requested_amount devem ser positivos")
    expected_revenue = i.planted_area_hectares * i.productivity * i.price
    crop_cost = i.planted_area_hectares * i.cost_per_hectare
    cash = expected_revenue - crop_cost
    nd_ebitda = i.net_debt / i.ebitda
    pro_forma = (i.net_debt + i.requested_amount) / i.ebitda
    coverage = cash / i.requested_amount
    cov_class = classify_coverage(coverage, t)
    lev_ok = nd_ebitda <= t.net_debt_ebitda_max
    pf_ok = pro_forma <= t.pro_forma_leverage_max
    return MetricOutputs(
        expected_revenue=round(expected_revenue, 2),
        crop_cost=round(crop_cost, 2),
        expected_cash_generation=round(cash, 2),
        net_debt_ebitda=round(nd_ebitda, 4),
        pro_forma_leverage=round(pro_forma, 4),
        coverage=round(coverage, 4),
        coverage_class=cov_class,
        leverage_within_limit=lev_ok,
        pro_forma_within_limit=pf_ok,
        classification=f"{cov_class}|{'leverage_ok' if lev_ok and pf_ok else 'leverage_breach'}",
    )

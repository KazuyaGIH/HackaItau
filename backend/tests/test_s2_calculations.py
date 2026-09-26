"""S2.4 — cálculos determinísticos (funções puras) e handlers calc registrando CALC-*."""

import pytest

from app.calculations.credit_metrics import MetricInputs, classify_coverage, credit_metrics, repayment_capacity
from app.calculations.policy_params import load_policy_params
from app.calculations.stress import apply_shocks, run_scenarios, worst_class

BASE = dict(
    planted_area_hectares=42_000,
    price=135,
    cost_per_hectare=6_300,
    requested_amount=50_000_000,
    net_debt=196_000_000,
    ebitda=70_000_000,
)


@pytest.fixture(scope="module")
def policy():
    return load_policy_params()


def test_formulas_declared_61(policy):
    o = credit_metrics(MetricInputs(productivity=61, **BASE), policy.thresholds)
    assert o.expected_revenue == pytest.approx(345_870_000)
    assert o.crop_cost == pytest.approx(264_600_000)
    assert o.expected_cash_generation == pytest.approx(81_270_000)
    assert o.net_debt_ebitda == pytest.approx(2.8)
    assert o.pro_forma_leverage == pytest.approx(3.5143, abs=1e-4)
    assert o.coverage == pytest.approx(1.6254, abs=1e-4)
    assert o.coverage_class == "comfortable"
    assert o.pro_forma_within_limit is False  # 3.51 > 3.5 → breach vem do código, não do LLM


def test_baseline_61_vs_58_changes_classification(policy):
    a = credit_metrics(MetricInputs(productivity=61, **BASE), policy.thresholds)
    b = credit_metrics(MetricInputs(productivity=58, **BASE), policy.thresholds)
    assert b.coverage == pytest.approx(1.2852, abs=1e-4)
    assert (a.coverage_class, b.coverage_class) == ("comfortable", "reduced_buffer")


def test_thresholds_from_policy_not_hardcoded(policy):
    t = policy.thresholds
    assert classify_coverage(t.coverage.comfortable_min, t) == "comfortable"
    assert classify_coverage(t.coverage.comfortable_min - 0.01, t) == "reduced_buffer"
    assert classify_coverage(t.coverage.attention_required_min - 0.01, t) == "insufficient"
    assert repayment_capacity(1.6, False, t) == "adequate_with_conditions"
    assert repayment_capacity(1.6, True, t) == "adequate"
    assert repayment_capacity(0.9, True, t) == "insufficient"


def test_stress_scenarios_reexecute_and_worst(policy):
    base = MetricInputs(productivity=61, **BASE)
    outcomes = run_scenarios(base, policy.stress_scenarios, policy.thresholds)
    by_id = {o.scenario_id: o for o in outcomes}
    assert set(by_id) == {"base", "price_minus_15pct", "productivity_minus_10pct", "combined"}
    assert by_id["price_minus_15pct"].inputs.price == pytest.approx(135 * 0.85)
    assert by_id["combined"].inputs.productivity == pytest.approx(61 * 0.9)
    assert by_id["base"].coverage > by_id["price_minus_15pct"].coverage > by_id["combined"].coverage
    assert worst_class(outcomes) == "insufficient"


def test_apply_shocks_only_allowed_fields():
    base = MetricInputs(productivity=61, **BASE)
    with pytest.raises(ValueError):
        apply_shocks(base, {"net_debt": -0.5})


def test_invalid_inputs_rejected(policy):
    with pytest.raises(ValueError):
        credit_metrics(MetricInputs(productivity=61, **{**BASE, "ebitda": 0}), policy.thresholds)


async def test_calc_tools_register_calculation_records(toolbox_factory):
    tb = toolbox_factory("agro_credit_risk", round_=2)
    policy = load_policy_params()
    assumptions = dict(
        productivity=61,
        baseline_policy="declared",
        sources={"productivity": "SRC-AGRO-PROFILE-CLIENTE-001"},
        thresholds_source_ids=policy.thresholds.kb_ids(),
        **BASE,
    )
    m = await tb.call("calculate_credit_metrics", assumptions=assumptions)
    s = await tb.call("run_stress_scenarios", assumptions=assumptions, scenario_ids=policy.scenario_ids())
    assert m.ok and m.calculation is not None and s.ok and s.calculation is not None
    assert m.calculation.id == "CALC-CREDIT-METRICS-R2" and s.calculation.id == "CALC-STRESS-R2"
    assert m.calculation.computed_by_agent == "agro_credit_risk" and m.calculation.round == 2
    assert m.calculation.inputs["productivity"] == 61
    assert m.calculation.input_sources["productivity"] == "SRC-AGRO-PROFILE-CLIENTE-001"
    assert m.calculation.thresholds_source_ids == policy.thresholds.kb_ids()
    assert "expected_revenue" in m.calculation.formula
    assert len(s.calculation.outputs["scenarios"]) == 4
    assert {m.calculation.id, s.calculation.id} <= tb.evidence.ids()


async def test_structuring_cannot_run_calculations(toolbox_factory):
    tb = toolbox_factory("agro_structuring")
    assumptions = dict(productivity=61, baseline_policy="declared", sources={}, **BASE)
    r = await tb.call("calculate_credit_metrics", assumptions=assumptions)
    assert not r.ok and r.reason == "tool_not_allowed_for_agent"
    assert tb.evidence.ids() == set()

"""Agro Credit Risk Agent (ARCHITECTURE.md §6.2).

gather: required_data + baseline (código) + calculate_credit_metrics + run_stress_scenarios via Gateway.
reason: LLM devolve só RiskLLMOutput (qualitativo).
validate: metrics/stress/repayment_capacity/risk_summary copiados dos CALC-*; números no texto que divergem → warning.
"""

import re

from pydantic import BaseModel

from app.agents.base import BaseAgent, ToolboxLike, ValidatedOutput, gather_required_data
from app.agents.risk.baseline import Baseline, BaselineError, BaselinePolicy, build_baseline
from app.calculations.credit_metrics import repayment_capacity, risk_summary
from app.calculations.policy_params import load_policy_params
from app.core.schemas.agent import AgentCard, TaskSpec
from app.core.schemas.context import ExecutionContext
from app.core.schemas.evidence import CalculationRecord, EvidenceBundle
from app.core.schemas.outputs import MetricsSummary, RiskLLMOutput, RiskOutput, ScenarioResult
from app.tools.calc_tools import CALC_CREDIT_METRICS, CALC_STRESS

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?\s*x\b", re.IGNORECASE)


class RiskAgentError(Exception):
    pass


class RiskAgent(BaseAgent):
    def __init__(self, card: AgentCard) -> None:
        super().__init__(card)
        self._baselines: dict[str, Baseline] = {}

    def _policy(self, task: TaskSpec) -> BaselinePolicy:
        if task.rework and task.rework.params.get("baseline_policy") == "historical":
            return "historical"
        return "declared"

    async def gather(self, ctx: ExecutionContext, task: TaskSpec, toolbox: ToolboxLike) -> EvidenceBundle:
        bundle = await gather_required_data(self.card, ctx, task, toolbox)
        requested = task.inputs.get("requested_amount")
        if requested is None:
            raise RiskAgentError("requested_amount ausente nos inputs do task")
        policy = load_policy_params()
        try:
            baseline = build_baseline(bundle, float(requested), policy.thresholds, self._policy(task))
        except BaselineError as exc:
            raise RiskAgentError(str(exc)) from exc
        self._baselines[task.task_id] = baseline

        params = baseline.params.model_dump()
        metrics = await toolbox.call("calculate_credit_metrics", assumptions=params)
        stress = await toolbox.call("run_stress_scenarios", assumptions=params, scenario_ids=policy.scenario_ids())
        for r in (metrics, stress):
            if not r.ok or r.calculation is None:
                raise RiskAgentError(f"cálculo negado/indisponível: {r.tool_name}:{r.reason}")
            bundle.calculations.append(r.calculation)
        return bundle

    def validate(
        self, ctx: ExecutionContext, task: TaskSpec, raw_output: BaseModel, evidence: EvidenceBundle
    ) -> ValidatedOutput:
        llm = RiskLLMOutput.model_validate(raw_output.model_dump())
        calc_m = _calc(evidence, CALC_CREDIT_METRICS)
        calc_s = _calc(evidence, CALC_STRESS)
        baseline = self._baselines.pop(task.task_id, None)
        if baseline is None:
            raise RiskAgentError("baseline não encontrado para o task")
        thresholds = load_policy_params().thresholds

        mo = calc_m.outputs
        metrics = MetricsSummary(
            calculation_id=calc_m.id,
            expected_revenue=mo["expected_revenue"],
            crop_cost=mo["crop_cost"],
            expected_cash_generation=mo["expected_cash_generation"],
            net_debt_ebitda=mo["net_debt_ebitda"],
            pro_forma_leverage=mo["pro_forma_leverage"],
            coverage=mo["coverage"],
            classification=mo["classification"],
        )
        scenarios = [
            ScenarioResult(
                scenario_id=s["scenario_id"],
                label=s["label"],
                shocks=s["shocks"],
                coverage=s["coverage"],
                expected_cash_generation=s["expected_cash_generation"],
                classification=s["classification"],
            )
            for s in calc_s.outputs["scenarios"]
        ]
        capacity = repayment_capacity(mo["coverage"], mo["pro_forma_within_limit"], thresholds)
        summary = risk_summary(capacity, calc_s.classification or "comfortable")

        warnings: list[str] = []
        stated = _NUM_RE.findall(_all_text(llm))
        known = {f"{v:.2f}".replace(".", ",") for v in (mo["coverage"], mo["pro_forma_leverage"], mo["net_debt_ebitda"])}
        known |= {f"{v:.1f}".replace(".", ",") for v in (mo["coverage"], mo["pro_forma_leverage"], mo["net_debt_ebitda"])}
        known |= {k.replace(",", ".") for k in known}
        for tok in stated:
            num = tok.lower().rstrip("x").strip()
            if num not in known:
                warnings.append(f"numero_no_texto_divergente_do_calc:{tok.strip()}")

        output = RiskOutput(
            **llm.model_dump(),
            baseline_policy=baseline.params.baseline_policy,  # type: ignore[arg-type]
            repayment_capacity=capacity,
            risk_summary=summary,
            metrics=metrics,
            stress_scenarios=scenarios,
            calculation_ids=[calc_m.id, calc_s.id],
        )
        return ValidatedOutput(
            output=output.model_dump(),
            assumptions=baseline.assumptions,
            calculation_ids=[calc_m.id, calc_s.id],
            warnings=warnings,
        )


def _calc(evidence: EvidenceBundle, name: str) -> CalculationRecord:
    for c in evidence.calculations:
        if c.name == name:
            return c
    raise RiskAgentError(f"CALC ausente: {name}")


def _all_text(llm: RiskLLMOutput) -> str:
    parts = [llm.risk_narrative]
    for group in (llm.main_risks, llm.mitigants, llm.qualitative_assumptions, llm.uncertainties):
        parts.extend(i.message for i in group)
    return " ".join(parts)

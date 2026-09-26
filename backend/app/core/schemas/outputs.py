"""Output schemas dos 4 agentes (ARCHITECTURE.md §6). Estes são os JSONs que o LLM devolve e o código valida.

Convenção: campos que o LLM preenche são texto/categorias qualitativas com evidence_ids.
Campos materiais (números, classificações por threshold) são preenchidos por código a partir de CALC-*.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["info", "low", "medium", "high"]


class EvidencedItem(BaseModel):
    code: str  # curto, estável, usado para cross-check (ex.: "GEO_CONCENTRATION", "DOC_AREA_MISMATCH")
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    severity: Severity | None = None


# ---------------------------------------------------------------- Eligibility


class MissingItem(BaseModel):
    item: str
    blocking: bool
    message: str = ""


class EligibilityOutput(BaseModel):
    status: Literal["ready", "ready_with_warnings", "blocked"]
    product_fit: str  # ex.: "credito_rural_custeio"
    checklist: list[EvidencedItem] = Field(default_factory=list)  # itens verificados (ok)
    missing_items: list[MissingItem] = Field(default_factory=list)
    warnings: list[EvidencedItem] = Field(default_factory=list)
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- Risk


class MetricsSummary(BaseModel):
    """Copiado de CALC-CREDIT-METRICS-R<n> por código."""

    calculation_id: str
    expected_revenue: float
    crop_cost: float
    expected_cash_generation: float
    net_debt_ebitda: float
    pro_forma_leverage: float
    coverage: float
    classification: str


class ScenarioResult(BaseModel):
    """Copiado de CALC-STRESS-R<n> por código."""

    scenario_id: str  # "base" | "price_minus_15pct" | "productivity_minus_10pct" | "combined"
    label: str
    shocks: dict[str, float]
    coverage: float
    expected_cash_generation: float
    classification: Literal["comfortable", "reduced_buffer", "attention_required", "insufficient"]


class RiskLLMOutput(BaseModel):
    """O que o LLM devolve no Risk: só texto/qualitativo. Nenhum número material."""

    risk_narrative: str
    main_risks: list[EvidencedItem]
    mitigants: list[EvidencedItem] = Field(default_factory=list)
    qualitative_assumptions: list[EvidencedItem] = Field(default_factory=list)
    uncertainties: list[EvidencedItem] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class RiskOutput(RiskLLMOutput):
    """RiskLLMOutput + campos code_owned preenchidos pelo validate a partir de CALC-*."""

    baseline_policy: Literal["declared", "historical"]
    repayment_capacity: Literal["adequate", "adequate_with_conditions", "tight", "insufficient"]
    risk_summary: Literal["low", "moderate", "elevated", "high"]
    metrics: MetricsSummary
    stress_scenarios: list[ScenarioResult]
    calculation_ids: list[str]


# ---------------------------------------------------------------- Structuring


class Alternative(BaseModel):
    model_config = ConfigDict(extra="forbid")  # rejeita preferred/ranking/score vindos do LLM

    id: str  # "ALT-1"
    name: str
    product_id: str  # deve existir no catálogo (SRC-PRODUCT-*)
    amount: float
    tenor_months: int
    amortization: str
    guarantees: list[str]
    conditions: list[str]  # condicionantes
    rationale: str
    when_it_fits: str
    advantages: list[str]
    risks: list[str]
    trade_offs: list[str]
    addressed_risk_codes: list[str] = Field(default_factory=list)  # códigos de main_risks do Risk cobertos
    evidence_ids: list[str] = Field(default_factory=list)


class StructuringOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 2–3 alternativas comparáveis; sem campo de preferência por design (ARCHITECTURE.md D9)
    alternatives: list[Alternative] = Field(min_length=2, max_length=3)
    comparison_notes: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- Review


class Finding(BaseModel):
    id: str  # "F-001"
    code: str  # ex.: ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED
    severity: Severity
    message: str
    owner_agent: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    origin: Literal["validator", "ai_review", "output_guard"]
    required_action: str | None = None  # só quando remediations.py conhece
    status: Literal["open", "resolved", "informational"] = "open"


class AIReviewOutput(BaseModel):
    """O que o LLM devolve no red team: findings com evidence_ids obrigatórios."""

    findings: list[Finding]
    overall_assessment: str


class ReviewOutput(BaseModel):
    review_status: Literal["passed", "passed_with_findings", "rework_required"]
    findings: list[Finding]
    grounding_ok: bool
    policy_ok: bool
    reexecution_required: bool
    reopen_agent: str | None = None
    rework_round: int = 0
    overall_assessment: str = ""


# ---------------------------------------------------------------- Interpreter (Orchestrator)


class InterpretedDemand(BaseModel):
    intent: str  # "credito_agro"
    client_ref: str | None
    requested_amount: float | None
    purpose: str | None  # "custeio"
    crop: str | None  # "soja"
    cycle: str | None  # "2025/2026"
    notes: str = ""


OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "EligibilityOutput": EligibilityOutput,
    "RiskLLMOutput": RiskLLMOutput,
    "RiskOutput": RiskOutput,
    "StructuringOutput": StructuringOutput,
    "AIReviewOutput": AIReviewOutput,
    "ReviewOutput": ReviewOutput,
    "InterpretedDemand": InterpretedDemand,
}


def output_schema_json(name: str) -> dict[str, Any]:
    return OUTPUT_SCHEMAS[name].model_json_schema()

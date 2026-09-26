"""Relatório estruturado e imparcial (ARCHITECTURE.md §16). Montado por código; números só de CALC-*."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.schemas.evidence import EvidenceRef
from app.core.schemas.outputs import Alternative, Finding, ScenarioResult, Severity

DISCLAIMER = (
    "Análise gerada para suporte à decisão. Não representa aprovação de crédito. Ambiente demonstrativo com dados fictícios."
)


class ReportItem(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    severity: Severity | None = None
    code: str | None = None


class ReportSummary(BaseModel):
    objective: str
    requested_amount: float | None
    purpose: str | None
    crop: str | None
    eligibility_status: str
    alternatives_count: int
    rework_rounds: int


class CalculationView(BaseModel):
    calculation_id: str
    name: str
    formula: str
    inputs: dict[str, Any]
    input_sources: dict[str, str]
    outputs: dict[str, Any]
    classification: str | None
    thresholds_source_ids: list[str] = Field(default_factory=list)


class AssumptionView(BaseModel):
    name: str
    value: Any
    unit: str | None = None
    source_id: str | None
    origin: Literal["code", "llm_qualitative"]
    justification: str
    changed_in_rework: bool = False
    previous_value: Any | None = None


class ScenarioView(ScenarioResult):
    calculation_id: str


class AlternativeView(Alternative):
    pass


class ReviewView(BaseModel):
    review_status: str
    findings: list[Finding]
    rework_rounds: int
    resolved_count: int
    open_count: int
    overall_assessment: str = ""


class AgentGovernanceView(BaseModel):
    agent_id: str
    data_domains_accessed: list[str]
    tool_calls: int
    denied_calls: int
    fields_hidden: int
    llm_calls: int
    fallback_used: bool


class GovernanceView(BaseModel):
    user_id: str
    purpose: str
    case_scope_client_ids: list[str]
    agents: list[AgentGovernanceView]
    permission_denials: int
    security_events: int
    fields_hidden_total: int
    permissions_changed: Literal[False] = False  # invariante: nunca muda durante o case


class HumanGateView(BaseModel):
    status: Literal["pending", "approved_next_step", "adjustment_requested"]
    available_actions: list[Literal["approve_next_step", "request_adjustment"]]
    comments: list[str] = Field(default_factory=list)
    notice: str = "Decisões materiais permanecem sob responsabilidade humana."


class Report(BaseModel):
    case_id: str
    client_id: str
    generated_at: datetime
    decision_status: Literal["ready_for_human_review"] = "ready_for_human_review"
    disclaimer: str = DISCLAIMER
    summary: ReportSummary
    facts: list[ReportItem]
    calculations: list[CalculationView]
    assumptions: list[AssumptionView]
    favorable_factors: list[ReportItem]
    risk_factors: list[ReportItem]
    stress_scenarios: list[ScenarioView]
    uncertainties: list[ReportItem]
    missing_data: list[ReportItem]
    alternatives: list[AlternativeView]  # 2–3, lado a lado, sem ranking
    sources: list[EvidenceRef]
    review: ReviewView
    governance: GovernanceView
    human_gate: HumanGateView
    llm_mode: Literal["real", "fallback", "mixed"]

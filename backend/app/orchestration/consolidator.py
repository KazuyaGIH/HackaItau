"""Consolidação → Report (ARCHITECTURE.md §16). Só CÓDIGO monta; números vêm de CALC-*; nenhuma síntese por LLM."""

from datetime import datetime, timezone

from app.core.events import EventLog
from app.core.evidence import EvidenceRegistry
from app.core.schemas.agent import AgentResult, Assumption
from app.core.schemas.case import CaseState
from app.core.schemas.events import EventType
from app.core.schemas.outputs import (
    EligibilityOutput,
    EvidencedItem,
    ReviewOutput,
    RiskOutput,
    StructuringOutput,
)
from app.core.schemas.report import (
    AgentGovernanceView,
    AlternativeView,
    AssumptionView,
    CalculationView,
    GovernanceView,
    HumanGateView,
    Report,
    ReportItem,
    ReportSummary,
    ReviewView,
    ScenarioView,
)
from app.orchestration.plans import ELIGIBILITY, RISK, STRUCTURING


def _item(i: EvidencedItem) -> ReportItem:
    return ReportItem(text=i.message, evidence_ids=list(i.evidence_ids), severity=i.severity, code=i.code)


def _assumption_views(current: list[Assumption], previous: list[Assumption]) -> list[AssumptionView]:
    prev = {a.name: a for a in previous}
    views = []
    for a in current:
        p = prev.get(a.name)
        changed = p is not None and p.value != a.value
        views.append(
            AssumptionView(
                name=a.name,
                value=a.value,
                unit=a.unit,
                source_id=a.source_id,
                origin=a.origin,
                justification=a.justification,
                changed_in_rework=changed,
                previous_value=p.value if changed and p else None,
            )
        )
    return views


def _governance(
    state: CaseState, results: dict[str, AgentResult], events: EventLog, evidence: EvidenceRegistry
) -> GovernanceView:
    hidden_by_agent: dict[str, int] = {}
    for s in evidence.sources():
        hidden_by_agent[s.accessed_by_agent] = hidden_by_agent.get(s.accessed_by_agent, 0) + s.fields_hidden
    agents = []
    for agent_id in state.selected_agents:
        r = results.get(agent_id)
        denied = sum(1 for e in events.of_type(EventType.PERMISSION_DENIED) if e.agent_id == agent_id)
        llm_calls = sum(1 for e in events.of_type(EventType.LLM_CALLED) if e.agent_id == agent_id)
        agents.append(
            AgentGovernanceView(
                agent_id=agent_id,
                data_domains_accessed=r.data_domains_accessed if r else [],
                tool_calls=r.tool_calls if r else 0,
                denied_calls=denied,
                fields_hidden=hidden_by_agent.get(agent_id, 0),
                llm_calls=llm_calls,
                fallback_used=bool(r and r.usage.fallback_used),
            )
        )
    assert state.scope is not None
    return GovernanceView(
        user_id=state.user_id,
        purpose=state.scope.purpose,
        case_scope_client_ids=list(state.scope.client_ids),
        agents=agents,
        permission_denials=len(events.of_type(EventType.PERMISSION_DENIED)),
        security_events=len(events.of_type(EventType.SECURITY_EVENT)),
        fields_hidden_total=sum(hidden_by_agent.values()),
    )


def llm_mode_of(results: dict[str, AgentResult]) -> str:
    flags = {r.usage.fallback_used for r in results.values()}
    if flags == {True}:
        return "fallback"
    if flags == {False} or not flags:
        return "real"
    return "mixed"


def consolidate(
    state: CaseState,
    events: EventLog,
    evidence: EvidenceRegistry,
    results: dict[str, AgentResult],
    first_round: dict[str, AgentResult],
    review: ReviewOutput,
) -> Report:
    assert state.scope is not None and state.interpreted is not None
    d = state.interpreted
    elig = EligibilityOutput.model_validate(results[ELIGIBILITY].output) if ELIGIBILITY in results else None
    risk = RiskOutput.model_validate(results[RISK].output) if RISK in results else None
    struct = StructuringOutput.model_validate(results[STRUCTURING].output) if STRUCTURING in results else None

    facts: list[ReportItem] = [_item(i) for i in elig.checklist] if elig else []
    favorable = [_item(i) for i in risk.mitigants] if risk else []
    risk_factors = [_item(i) for i in risk.main_risks] if risk else []
    if elig:
        risk_factors += [_item(w) for w in elig.warnings]
    uncertainties = [_item(i) for i in risk.uncertainties] if risk else []
    missing = (
        [
            ReportItem(text=f"{m.item}: {m.message}", severity="high" if m.blocking else "low", code="MISSING_ITEM")
            for m in elig.missing_items
        ]
        if elig
        else []
    )
    for r in results.values():
        for w in r.warnings:
            uncertainties.append(ReportItem(text=f"[{r.agent_id}] {w}", severity="info", code="AGENT_WARNING"))

    assumptions: list[AssumptionView] = []
    if RISK in results:
        assumptions = _assumption_views(results[RISK].assumptions, first_round.get(RISK, results[RISK]).assumptions)
        if risk:
            assumptions += [
                AssumptionView(
                    name=q.code,
                    value=q.message,
                    source_id=q.evidence_ids[0] if q.evidence_ids else None,
                    origin="llm_qualitative",
                    justification="",
                )
                for q in risk.qualitative_assumptions
            ]

    calculations = [
        CalculationView(
            calculation_id=c.id,
            name=c.name,
            formula=c.formula,
            inputs=c.inputs,
            input_sources=c.input_sources,
            outputs=c.outputs,
            classification=c.classification,
            thresholds_source_ids=c.thresholds_source_ids,
        )
        for c in evidence.calculations()
    ]
    scenarios = (
        [ScenarioView(**s.model_dump(), calculation_id=results[RISK].calculation_ids[-1]) for s in risk.stress_scenarios]
        if risk
        else []
    )
    alternatives = [AlternativeView(**a.model_dump()) for a in struct.alternatives] if struct else []

    open_count = sum(1 for f in review.findings if f.status == "open")
    resolved_count = sum(1 for f in review.findings if f.status == "resolved")
    return Report(
        case_id=state.case_id,
        client_id=state.scope.client_ids[0],
        generated_at=datetime.now(timezone.utc),
        summary=ReportSummary(
            objective=d.notes or f"Análise de {d.purpose or 'crédito'} — {d.crop or 'cultura n/d'} {d.cycle or ''}".strip(),
            requested_amount=d.requested_amount,
            purpose=d.purpose,
            crop=d.crop,
            eligibility_status=elig.status if elig else "n/a",
            alternatives_count=len(alternatives),
            rework_rounds=state.rework_rounds,
        ),
        facts=facts,
        calculations=calculations,
        assumptions=assumptions,
        favorable_factors=favorable,
        risk_factors=risk_factors,
        stress_scenarios=scenarios,
        uncertainties=uncertainties,
        missing_data=missing,
        alternatives=alternatives,
        sources=[ref for ref in (evidence.ref(i) for i in sorted(evidence.ids())) if ref is not None],
        review=ReviewView(
            review_status=review.review_status,
            findings=review.findings,
            rework_rounds=state.rework_rounds,
            resolved_count=resolved_count,
            open_count=open_count,
            overall_assessment=review.overall_assessment,
        ),
        governance=_governance(state, results, events, evidence),
        human_gate=HumanGateView(status="pending", available_actions=["approve_next_step", "request_adjustment"]),
        llm_mode=llm_mode_of(results),  # type: ignore[arg-type]
    )

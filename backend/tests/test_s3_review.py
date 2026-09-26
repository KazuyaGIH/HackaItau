"""S3.1–S3.3 — validators determinísticos (camada A), merge/rework e Output Guard, isolados do orquestrador."""

import copy
import json

import pytest

from app.agents.registry import AgentRegistry
from app.agents.review.merge import merge_review
from app.agents.review.remediations import rework_for
from app.agents.review.validators import (
    ReviewContext,
    approval_language,
    assumption_above_baseline_unjustified,
    calc_inconsistent,
    evidence_not_found,
    permission_violation_attempted,
    risk_ignored_by_structure,
    run_validators,
    structure_vs_request_and_catalog,
)
from app.agents.runtime import AgentRuntime
from app.calculations.policy_params import load_policy_params
from app.config import Settings
from app.container import build_container
from app.core.events import EventLog
from app.core.evidence import EvidenceRegistry
from app.core.schemas.agent import AgentResult, TaskSpec
from app.core.schemas.case import DemoOptions
from app.core.schemas.events import EventType
from app.core.schemas.outputs import Finding
from app.core.schemas.report import ReportItem
from app.governance.output_guard import REDACTED, OutputGuard
from tests.conftest import make_ctx

AGENTS = ("agro_eligibility", "agro_credit_risk", "agro_structuring")
INPUTS = {"requested_amount": 50_000_000, "purpose": "custeio", "crop": "soja"}
PROMPT = "O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2025/26."


@pytest.fixture(scope="module")
def registry():
    return AgentRegistry()


async def _pipeline(registry, toolbox_factory, analyst, scope_001, *, adversarial=False):
    """Roda os 3 agentes de análise com ScriptedFallback e devolve (results, evidence, events)."""
    events, evidence = EventLog("case-test"), EvidenceRegistry()
    results: dict[str, AgentResult] = {}
    rt = AgentRuntime(None, "fake-model", fallback_enabled=True)
    for agent_id in AGENTS:
        task = TaskSpec(
            task_id=f"t-{agent_id}",
            agent_id=agent_id,
            round=1,
            instruction="Analise o case.",
            inputs=INPUTS,
            upstream_output_ids=[r.output_id for r in results.values()],
        )
        tb = toolbox_factory(agent_id, events=events, evidence=evidence, adversarial=adversarial)
        ctx = make_ctx(analyst, agent_id, scope_001)
        results[agent_id] = await rt.run(registry.get(agent_id), ctx, task, tb, events, evidence)
    return results, evidence, events


def _ctx(results, evidence, events) -> ReviewContext:
    return ReviewContext(
        results=results, evidence=evidence, events=events, policy=load_policy_params(), requested_amount=50_000_000
    )


def _mutated(results: dict[str, AgentResult], agent_id: str, **changes) -> dict[str, AgentResult]:
    out = dict(results)
    r = results[agent_id]
    out[agent_id] = r.model_copy(update={"output": copy.deepcopy(r.output) | changes})
    return out


@pytest.fixture
async def pipeline(registry, toolbox_factory, analyst, scope_001):
    return await _pipeline(registry, toolbox_factory, analyst, scope_001)


# ------------------------------------------------------------------ validators


async def test_clean_pipeline_only_raises_the_baseline_assumption(pipeline):
    results, evidence, events = pipeline
    findings = run_validators(_ctx(results, evidence, events))
    codes = {f.code for f in findings}
    assert "ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED" in codes  # 61 declarado > 58 histórico, sem justificativa
    assert not codes & {"EVIDENCE_NOT_FOUND", "CALC_INCONSISTENT", "PRODUCT_UNKNOWN", "APPROVAL_LANGUAGE"}
    f = next(f for f in findings if f.code == "ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED")
    assert f.severity == "high" and f.owner_agent == "agro_credit_risk"
    assert f.required_action == "recalculate_with_historical_baseline"
    assert "SRC-AGRO-PROFILE-CLIENTE-001" in f.evidence_ids and "CALC-CREDIT-METRICS-R1" in f.evidence_ids
    assert all(f.id.startswith("F-") and evidence.missing(f.evidence_ids) == [] for f in findings)


async def test_baseline_58_with_justification_is_not_flagged(pipeline):
    results, evidence, events = pipeline
    r = results["agro_credit_risk"]
    justified = [
        a.model_copy(update={"value": 58.0, "justification": "baseline histórico (rework)"})
        if a.name == "productivity"
        else a
        for a in r.assumptions
    ]
    results2 = dict(results) | {"agro_credit_risk": r.model_copy(update={"assumptions": justified})}
    assert assumption_above_baseline_unjustified(_ctx(results2, evidence, events)) == []


async def test_evidence_not_found_catches_invented_ids(pipeline):
    results, evidence, events = pipeline
    elig = results["agro_eligibility"].output
    checklist = copy.deepcopy(elig["checklist"])
    checklist[0]["evidence_ids"] = ["SRC-INVENTADO-001"]
    findings = evidence_not_found(_ctx(_mutated(results, "agro_eligibility", checklist=checklist), evidence, events))
    assert [f.code for f in findings] == ["EVIDENCE_NOT_FOUND"]
    assert "SRC-INVENTADO-001" in findings[0].message and findings[0].owner_agent == "agro_eligibility"


async def test_calc_inconsistent_detects_tampered_metric(pipeline):
    results, evidence, events = pipeline
    metrics = copy.deepcopy(results["agro_credit_risk"].output["metrics"])
    metrics["coverage"] = 9.99  # LLM "melhorou" o número; CALC registrado não bate
    findings = calc_inconsistent(_ctx(_mutated(results, "agro_credit_risk", metrics=metrics), evidence, events))
    assert [f.code for f in findings] == ["CALC_INCONSISTENT"] and "coverage" in findings[0].message
    assert findings[0].evidence_ids == ["CALC-CREDIT-METRICS-R1"]
    # o output original (números vindos do CALC) passa
    assert calc_inconsistent(_ctx(results, evidence, events)) == []


async def test_risk_ignored_by_structure(pipeline):
    results, evidence, events = pipeline
    alts = copy.deepcopy(results["agro_structuring"].output["alternatives"])
    for a in alts:
        a["addressed_risk_codes"] = []
    findings = risk_ignored_by_structure(_ctx(_mutated(results, "agro_structuring", alternatives=alts), evidence, events))
    assert len(findings) == 1 and findings[0].code == "RISK_IGNORED_BY_STRUCTURE"
    assert findings[0].owner_agent == "agro_structuring"
    assert findings[0].required_action == "address_risks_in_structure"
    assert "OUT-agro_credit_risk-R1" in findings[0].evidence_ids


async def test_structure_vs_request_and_catalog(pipeline):
    results, evidence, events = pipeline
    alts = copy.deepcopy(results["agro_structuring"].output["alternatives"])
    alts[0]["amount"] = 80_000_000
    alts[1]["tenor_months"] = 999
    alts[1]["product_id"] = "PROD-NAO-EXISTE"
    codes = sorted(
        f.code
        for f in structure_vs_request_and_catalog(
            _ctx(_mutated(results, "agro_structuring", alternatives=alts), evidence, events)
        )
    )
    assert codes == ["PRODUCT_UNKNOWN", "STRUCTURE_EXCEEDS_REQUEST"]


async def test_approval_language_flagged_unless_negated(pipeline):
    results, evidence, events = pipeline
    bad = _mutated(results, "agro_credit_risk", risk_summary="Crédito aprovado; certamente sem risco.")
    findings = approval_language(_ctx(bad, evidence, events))
    assert [f.code for f in findings] == ["APPROVAL_LANGUAGE"] and findings[0].owner_agent == "agro_credit_risk"
    ok = _mutated(results, "agro_credit_risk", risk_summary="Esta análise não é crédito aprovado nem recomendação.")
    assert approval_language(_ctx(ok, evidence, events)) == []


async def test_permission_violation_is_informational_finding(registry, toolbox_factory, analyst, scope_001):
    results, evidence, events = await _pipeline(registry, toolbox_factory, analyst, scope_001, adversarial=True)
    assert events.of_type(EventType.PERMISSION_DENIED)
    findings = permission_violation_attempted(_ctx(results, evidence, events))
    assert findings and all(f.status == "informational" and f.severity == "info" for f in findings)
    assert rework_for(findings) is None  # nunca dispara rework


# ------------------------------------------------------------------ merge / rework


def _f(code, severity="high", owner="agro_credit_risk", action="recalculate_with_historical_baseline", status="open"):
    return Finding(
        id=f"F-{code[:4]}",
        code=code,
        severity=severity,
        message=code,
        owner_agent=owner,
        evidence_ids=["CALC-CREDIT-METRICS-R1"],
        origin="validator",
        required_action=action,
        status=status,
    )


def test_merge_requires_rework_only_with_owner_and_known_action():
    ai = [_f("FRAGILE_ASSUMPTION", owner=None, action=None).model_copy(update={"origin": "ai_review"})]
    r1 = merge_review([_f("ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED")], ai, "ok", rework_round=1)
    assert r1.review_status == "rework_required" and r1.reexecution_required
    assert r1.reopen_agent == "agro_credit_risk"

    # high sem ação conhecida → findings ficam abertos, mas não há rework automático
    r_unknown = merge_review([_f("SOMETHING_NEW", action=None)], [], "ok", rework_round=1)
    assert r_unknown.review_status == "passed_with_findings" and not r_unknown.reexecution_required

    # round 2 sem o finding → marcado como resolvido; AI finding recorrente continua aberto
    r2 = merge_review([], ai, "ok", rework_round=2, previous=r1)
    assert r2.review_status == "passed_with_findings" and not r2.reexecution_required
    resolved = [f for f in r2.findings if f.status == "resolved"]
    assert [f.code for f in resolved] == ["ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED"]
    assert merge_review([], [], "ok", rework_round=2, previous=r2).review_status == "passed"


# ------------------------------------------------------------------ output guard


@pytest.fixture
async def guarded_case():
    c = build_container(Settings(llm_api_key="sk-test-secret-value-000000", llm_fallback_enabled=True, _env_file=None))
    c.runtime.provider = None  # sem chamadas reais; fallback
    rec = await c.orchestrator.create_case("analyst-001", PROMPT, DemoOptions())
    await c.orchestrator.run(rec.state.case_id)
    assert rec.state.report is not None, rec.state.error
    return c, rec


async def test_output_guard_is_noop_on_clean_report(guarded_case):
    c, rec = guarded_case
    guard = OutputGuard(c.repo, c.settings.secret_values(), rec.state.scope)
    res = guard.apply(rec.state.report, rec.evidence, next_finding_seq=1)
    assert not res.applied and res.redactions == {}


async def test_output_guard_redacts_and_neutralizes(guarded_case):
    c, rec = guarded_case
    report = rec.state.report.model_copy(deep=True)
    never_value = c.repo.get_client("CLIENTE-001")["internal_rating_notes"]
    report.risk_factors.append(
        ReportItem(
            text=(
                "Recomendamos a aprovação. Chave sk-test-secret-value-000000 e LLM_API_KEY=abc123. "
                f"Ver CLIENTE-999. Nota: {never_value}"
            ),
            evidence_ids=["CALC-CREDIT-METRICS-R1"],
            severity="high",
        )
    )
    report.facts.append(ReportItem(text="Claim material inventada.", evidence_ids=["SRC-INVENTADA"], severity="info"))
    report.summary.objective = "Operação aprovada com certeza."

    guard = OutputGuard(c.repo, c.settings.secret_values(), rec.state.scope)
    res = guard.apply(report, rec.evidence, 50)
    assert res.applied
    codes = {f.code for f in res.findings}
    assert {"GUARD_SECRET", "GUARD_SCOPE", "GUARD_FORBIDDEN_FIELD", "GUARD_LANGUAGE", "GUARD_UNGROUNDED"} <= codes
    dump = json.dumps(res.report.model_dump(mode="json"), ensure_ascii=False)
    leaks = ("sk-test-secret-value-000000", "abc123", "CLIENTE-999", never_value, "Recomendamos a aprovação", "com certeza")
    for leaked in leaks:
        assert leaked not in dump, leaked
    assert REDACTED in dump and "para avaliação humana" in dump
    assert not any("inventada" in f.text for f in res.report.facts)
    assert any(u.code == "GUARD_UNGROUNDED" and "inventada" in u.text for u in res.report.uncertainties)
    assert res.report.decision_status == "ready_for_human_review"
    assert all(f.origin == "output_guard" and f.status == "informational" for f in res.findings)
    assert res.findings[0].id == "F-G-050"
    # IDs estruturais não são tocados
    assert res.report.client_id == "CLIENTE-001" and res.report.sources == rec.state.report.sources

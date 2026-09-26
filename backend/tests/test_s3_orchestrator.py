"""S3: orquestração end-to-end com ScriptedFallback, gate de Eligibility, rework ≤ 1, Output Guard e human gate."""

import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.container import build_container
from app.core.schemas.case import CaseStatus, DemoOptions
from app.core.schemas.context import CaseScope
from app.core.schemas.events import EventType
from app.data.json_repository import JsonMockRepository
from app.llm.provider import LLMResponse, LLMUsage
from app.orchestration.orchestrator import OrchestratorError

PROMPT = "O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2025/26."
ANALYST = "analyst-001"


def _settings(**kw) -> Settings:
    return Settings(llm_api_key="", llm_fallback_enabled=True, _env_file=None, **kw)


@pytest.fixture
def container():
    return build_container(_settings())


async def _bootstrap(container, prompt=PROMPT, adversarial=False):
    rec = await container.orchestrator.create_case(ANALYST, prompt, DemoOptions(adversarial_document=adversarial))
    assert rec.state.status == CaseStatus.planned, rec.state
    return rec


# ------------------------------------------------------------------ golden path


async def test_golden_path_ends_in_human_review_with_neutral_report(container):
    rec = await _bootstrap(container)
    await container.orchestrator.run(rec.state.case_id)
    st = rec.state
    assert st.status == CaseStatus.human_review_required, st.error
    assert st.report is not None and st.review is not None

    types = [e.type for e in rec.events.all()]
    for t in (
        EventType.REVIEW_STARTED,
        EventType.REVIEW_COMPLETED,
        EventType.RESULT_CONSOLIDATED,
        EventType.HUMAN_REVIEW_REQUIRED,
    ):
        assert t in types
    # ordem fixa do plano; Review por último
    started = [e.agent_id for e in rec.events.of_type(EventType.AGENT_STARTED)]
    assert started[:3] == ["agro_eligibility", "agro_credit_risk", "agro_structuring"]
    assert "credit_review" in started

    rep = st.report
    assert rep.client_id == "CLIENTE-001"
    assert rep.human_gate.status == "pending" and rep.human_gate.available_actions == [
        "approve_next_step",
        "request_adjustment",
    ]
    assert rep.llm_mode == "fallback"
    assert len(rep.alternatives) >= 2 and len(rep.calculations) >= 2 and rep.stress_scenarios
    # números materiais vêm de CALC-*, nunca do LLM
    metrics = next(c for c in rep.calculations if c.name == "credit_metrics")
    assert metrics.outputs["expected_revenue"] in (345_870_000.0, 328_860_000.0)
    # relatório neutro
    text = json.dumps(rep.model_dump(mode="json"), ensure_ascii=False).lower()
    for banned in ("aprovado", "aprovamos", "recomendamos a aprovação", "reprovado", "cliente-999"):
        assert banned not in text, banned
    assert rep.sources and all(s.id.startswith(("SRC-", "KB-", "CALC-", "OUT-")) for s in rep.sources)


async def test_baseline_61_vs_58_triggers_exactly_one_rework(container):
    rec = await _bootstrap(container)
    await container.orchestrator.run(rec.state.case_id)
    st = rec.state
    assert st.status == CaseStatus.human_review_required, st.error
    assert st.rework_rounds == 1
    codes = {f.code for f in st.review.findings}
    assert "ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED" in codes
    resolved = [
        f for f in st.review.findings if f.code == "ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED" and f.status == "resolved"
    ]
    assert resolved, "finding do baseline deveria estar resolvido após rework com histórico"
    reopened = [e.agent_id for e in rec.events.of_type(EventType.TASK_REOPENED)]
    assert reopened[0] == "agro_credit_risk" and "agro_structuring" in reopened  # owner + dependente
    assert rec.events.of_type(EventType.TASK_REOPENED) and st.review.reexecution_required is False
    risk_starts = [e for e in rec.events.of_type(EventType.AGENT_STARTED) if e.agent_id == "agro_credit_risk"]
    risk_rounds = [e.payload["round"] for e in risk_starts]
    assert risk_rounds == [1, 2]
    # relatório mostra a premissa alterada (61 → 58) e a cobertura recalculada
    prod = next(a for a in st.report.assumptions if a.name == "productivity")
    assert prod.changed_in_rework is True and prod.previous_value == 61 and prod.value == 58
    metrics = next(c for c in st.report.calculations if c.calculation_id.endswith("R2") and c.name == "credit_metrics")
    assert metrics.outputs["expected_revenue"] == 328_860_000.0


# ------------------------------------------------------------------ eligibility gate


class _RepoWithoutFinancialStatements(JsonMockRepository):
    """Mesmo mock, mas o documento obrigatório `demonstracoes_financeiras` não existe."""

    def list_documents(self, client_id: str, scenario_tags: list[str]) -> list[dict]:
        return [d for d in super().list_documents(client_id, scenario_tags) if d.get("type") != "demonstracoes_financeiras"]


async def test_eligibility_blocked_stops_before_risk_then_input_unblocks():
    container = build_container(_settings())
    container.orchestrator._repo = _RepoWithoutFinancialStatements(container.settings.mock_data_dir)
    rec = await _bootstrap(container)

    # LLM tenta dizer "ready"; o status é decidido por CÓDIGO (política de documentos obrigatórios)
    class OptimisticProvider:
        async def complete(self, *, model, messages, response_schema=None, temperature=0.0, tools=None):
            body = {
                "status": "ready",
                "product_fit": "credito_rural_custeio",
                "checklist": [],
                "missing_items": [],
                "warnings": [],
                "summary": "Tudo em ordem.",
                "evidence_ids": [],
            }
            return LLMResponse(content=json.dumps(body), usage=LLMUsage(model=model, tokens_in=1, tokens_out=1))

    container.runtime.provider = OptimisticProvider()
    await container.orchestrator.run(rec.state.case_id)
    st = rec.state
    assert st.status == CaseStatus.waiting_input, st.error
    assert st.missing_info is not None and st.missing_info.reason == "eligibility_blocked"
    assert st.missing_info.items == ["demonstracoes_financeiras"]
    started = {e.agent_id for e in rec.events.of_type(EventType.AGENT_STARTED)}
    assert started == {"agro_eligibility"}  # Risk não rodou
    assert next(a for a in st.agents if a.agent_id == "agro_credit_risk").status.value == "waiting"
    assert st.report is None
    with pytest.raises(OrchestratorError, match="não está em revisão humana"):
        container.orchestrator.human_review(st.case_id, "approve_next_step", "")

    # input completa o dado (nunca muda scope), volta para planned e a execução segue até o gate humano
    container.orchestrator.provide_input(
        st.case_id, {"demonstracoes_financeiras": "DF-2025 recebida", "client_ref": "CLIENTE-999"}
    )
    assert st.status == CaseStatus.planned and st.scope.client_ids == ("CLIENTE-001",)
    assert rec.answers == {"demonstracoes_financeiras": "DF-2025 recebida"}
    container.runtime.provider = None
    await container.orchestrator.run(st.case_id)
    assert st.status == CaseStatus.human_review_required, st.error
    assert st.scope.client_ids == ("CLIENTE-001",)


# ------------------------------------------------------------------ adversarial demo


async def test_adversarial_document_denied_and_visible_in_report(container):
    rec = await _bootstrap(container, adversarial=True)
    await container.orchestrator.run(rec.state.case_id)
    st = rec.state
    assert st.status == CaseStatus.human_review_required, st.error
    kinds = {e.payload["kind"] for e in rec.events.of_type(EventType.SECURITY_EVENT)}
    assert {"INJECTION_SUSPECTED", "SCOPE_VIOLATION_BLOCKED"} <= kinds
    assert rec.events.of_type(EventType.PERMISSION_DENIED)
    assert st.report.governance.permission_denials >= 1 and st.report.governance.security_events >= 2
    assert st.scope.client_ids == ("CLIENTE-001",)
    assert next(a for a in st.agents if a.agent_id == "agro_eligibility").denied_calls >= 1
    assert "CLIENTE-999" not in json.dumps(st.report.model_dump(mode="json"))
    codes = {f.code for f in st.review.findings}
    assert "PERMISSION_VIOLATION_ATTEMPTED" in codes


# ------------------------------------------------------------------ human gate


async def test_human_gate_approve_is_not_credit_approval(container):
    rec = await _bootstrap(container)
    await container.orchestrator.run(rec.state.case_id)
    container.orchestrator.human_review(rec.state.case_id, "request_adjustment", "Detalhar garantias.")
    assert rec.state.status == CaseStatus.human_review_required
    assert rec.state.report.human_gate.status == "adjustment_requested"
    assert rec.state.report.human_gate.comments == ["Detalhar garantias."]

    container.orchestrator.human_review(rec.state.case_id, "approve_next_step", "ok")
    assert rec.state.status == CaseStatus.completed_demo
    gate = rec.state.report.human_gate
    assert gate.status == "approved_next_step" and gate.available_actions == []
    note = rec.events.of_type(EventType.CASE_COMPLETED)[0].payload["note"]
    assert "NÃO é aprovação de crédito" in note
    with pytest.raises(OrchestratorError):
        container.orchestrator.human_review(rec.state.case_id, "approve_next_step", "")


async def test_case_scope_is_immutable(container):
    rec = await _bootstrap(container)
    with pytest.raises(ValidationError):
        rec.state.scope.client_ids = ("CLIENTE-999",)  # type: ignore[misc]
    assert CaseScope(client_ids=("CLIENTE-001",), purpose="credit_analysis_agro").client_ids == ("CLIENTE-001",)


async def test_run_without_llm_and_without_fallback_fails_auditably():
    c = build_container(Settings(llm_api_key="", llm_fallback_enabled=False, _env_file=None))
    rec = await c.orchestrator.create_case(ANALYST, PROMPT, DemoOptions())
    await c.orchestrator.run(rec.state.case_id)
    assert rec.state.status == CaseStatus.failed
    assert rec.state.error and "llm_unconfigured" in rec.state.error
    assert rec.events.of_type(EventType.EXECUTION_FAILED)

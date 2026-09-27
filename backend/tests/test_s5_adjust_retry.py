"""S5: ajuste humano reexecuta a squad; retry retoma a execução a partir do agente que falhou."""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import build_container, get_container
from app.core.schemas.case import CaseStatus, DemoOptions
from app.core.schemas.events import EventType
from app.llm.openai_compat import LLMError
from app.main import app
from app.orchestration.orchestrator import MAX_HUMAN_ADJUSTMENTS, OrchestratorError
from tests.fake_llm import StubProvider

PROMPT = "O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2025/26."
ANALYST = "analyst-001"


class FlakyProvider(StubProvider):
    """Falha (como um 429 do provider) na n-ésima chamada com o schema dado; depois responde normalmente."""

    def __init__(self, fail_schema: str, on_call: int = 1) -> None:
        super().__init__()
        self.fail_schema = fail_schema
        self.on_call = on_call
        self.seen = 0

    async def complete(self, *, model, messages, response_schema=None, temperature=0.0, tools=None):
        if response_schema is not None and response_schema.__name__ == self.fail_schema:
            self.seen += 1
            if self.seen == self.on_call:
                raise LLMError("provider respondeu HTTP 429: quota excedida")
        return await super().complete(
            model=model, messages=messages, response_schema=response_schema, temperature=temperature, tools=tools
        )


def _container(provider=None):
    c = build_container(Settings(llm_api_key="", _env_file=None))
    c.runtime.provider = provider or StubProvider()
    return c


async def _reviewed_case(c):
    rec = await c.orchestrator.create_case(ANALYST, PROMPT, DemoOptions())
    await c.orchestrator.run(rec.state.case_id)
    assert rec.state.status == CaseStatus.human_review_required, rec.state.error
    return rec


def _started(rec, round_: int) -> list[str]:
    return [e.agent_id for e in rec.events.of_type(EventType.AGENT_STARTED) if e.payload["round"] == round_]


# ------------------------------------------------------------------ ajuste humano


async def test_adjustment_reruns_target_and_dependents_with_the_analyst_comment():
    provider = StubProvider()
    c = _container(provider)
    rec = await _reviewed_case(c)
    calls_before = len(provider.calls)

    await c.orchestrator.adjust(rec.state.case_id, "Considerar garantia adicional na alternativa 2.", "agro_structuring")

    st = rec.state
    assert st.status == CaseStatus.human_review_required, st.error
    started = rec.events.of_type(EventType.ORCHESTRATOR_STARTED)[-1].payload
    assert started["phase"] == "human_adjustment" and started["target_agent"] == "agro_structuring"
    assert started["round"] == 3 and started["plan"] == ["agro_structuring", "credit_review"]
    # só o alvo (sem dependentes) e a revisão rodam; Eligibility e Risk ficam como estavam
    assert _started(rec, 3) == ["agro_structuring", "credit_review"]
    reopened = [e for e in rec.events.of_type(EventType.TASK_REOPENED) if e.payload.get("source") == "human"]
    assert [e.agent_id for e in reopened] == ["agro_structuring"]

    # o comentário chega ao agente como dado não confiável, identificado como vindo do analista
    prompts = ["\n".join(m.content for m in msgs) for msgs in provider.calls[calls_before:]]
    adjusted = [p for p in prompts if "Ajuste solicitado pelo analista" in p]
    assert len(adjusted) == 1
    assert "label=analyst_comment" in adjusted[0] and "garantia adicional" in adjusted[0]

    # relatório novo, de volta ao gate humano, com o comentário preservado
    gate = st.report.human_gate
    assert gate.status == "pending" and gate.comments == ["Considerar garantia adicional na alternativa 2."]
    types = [e.type for e in rec.events.list_after(0)]
    assert types[-1] == EventType.HUMAN_REVIEW_REQUIRED
    assert types.count(EventType.RESULT_CONSOLIDATED) == 2


async def test_adjusting_risk_keeps_the_baseline_fixed_by_the_review():
    c = _container()
    rec = await _reviewed_case(c)

    await c.orchestrator.adjust(rec.state.case_id, "Detalhar a sensibilidade a preço.", "agro_credit_risk")

    st = rec.state
    assert st.status == CaseStatus.human_review_required, st.error
    assert _started(rec, 3) == ["agro_credit_risk", "agro_structuring", "credit_review"]
    # sem os params do rework anterior a produtividade voltaria a 61 (o erro que o Review corrigiu)
    productivity = next(a for a in st.report.assumptions if a.name == "productivity")
    assert productivity.value == 58
    open_codes = {f.code for f in st.review.findings if f.status == "open"}
    assert "ASSUMPTION_ABOVE_BASELINE_UNJUSTIFIED" not in open_codes


async def test_adjustment_is_validated_and_bounded():
    c = _container()
    rec = await _reviewed_case(c)
    cid = rec.state.case_id

    with pytest.raises(OrchestratorError) as bad_target:
        await c.orchestrator.adjust(cid, "rever", "credit_review")
    assert bad_target.value.code == "invalid_target_agent" and bad_target.value.http_status == 422
    with pytest.raises(OrchestratorError) as empty:
        await c.orchestrator.adjust(cid, "   ", "agro_structuring")
    assert empty.value.code == "comment_required"
    assert not rec.events.of_type(EventType.HUMAN_ADJUSTMENT_REQUESTED)  # nada registrado quando o pedido é inválido

    for i in range(MAX_HUMAN_ADJUSTMENTS):
        await c.orchestrator.adjust(cid, f"ajuste {i}", "agro_structuring")
    with pytest.raises(OrchestratorError, match="limite"):
        await c.orchestrator.adjust(cid, "mais um", "agro_structuring")
    assert rec.state.status == CaseStatus.human_review_required


# ------------------------------------------------------------------ retry


async def test_retry_resumes_from_the_failed_agent():
    c = _container(FlakyProvider("StructuringOutput"))
    rec = await c.orchestrator.create_case(ANALYST, PROMPT, DemoOptions())
    await c.orchestrator.run(rec.state.case_id)
    st = rec.state
    assert st.status == CaseStatus.failed and st.error.startswith("agro_structuring:provider_error")

    await c.orchestrator.retry(st.case_id)

    assert st.status == CaseStatus.human_review_required, st.error
    assert st.error is None
    round1 = _started(rec, 1)
    # Eligibility e Risk já tinham concluído: não chamam o LLM de novo; Structuring retoma
    assert round1.count("agro_eligibility") == 1 and round1.count("agro_credit_risk") == 1
    assert round1.count("agro_structuring") == 2
    retry = [e.payload for e in rec.events.of_type(EventType.ORCHESTRATOR_STARTED) if e.payload["phase"] == "retry"]
    assert retry == [{"phase": "retry", "job": "execution", "round": 1, "failed_agent": "agro_structuring"}]
    assert st.rework_rounds == 1  # o rework automático do Review continua acontecendo


async def test_retry_during_the_review_rework_does_not_repeat_the_reopening():
    c = _container(FlakyProvider("RiskLLMOutput", on_call=2))  # falha no Risk da rodada 2 (rework)
    rec = await c.orchestrator.create_case(ANALYST, PROMPT, DemoOptions())
    await c.orchestrator.run(rec.state.case_id)
    assert rec.state.status == CaseStatus.failed

    await c.orchestrator.retry(rec.state.case_id)

    assert rec.state.status == CaseStatus.human_review_required, rec.state.error
    reopened = [(e.agent_id, e.payload["round"]) for e in rec.events.of_type(EventType.TASK_REOPENED)]
    assert reopened == [("agro_credit_risk", 2), ("agro_structuring", 2)]
    assert _started(rec, 1).count("credit_review") == 1  # a revisão da rodada 1 não roda de novo
    productivity = next(a for a in rec.state.report.assumptions if a.name == "productivity")
    assert productivity.value == 58


async def test_failed_adjustment_can_be_retried():
    c = _container(FlakyProvider("StructuringOutput", on_call=3))  # R1, R2 ok; falha no ajuste (R3)
    rec = await _reviewed_case(c)
    await c.orchestrator.adjust(rec.state.case_id, "Alongar prazo.", "agro_structuring")
    assert rec.state.status == CaseStatus.failed

    await c.orchestrator.retry(rec.state.case_id)

    assert rec.state.status == CaseStatus.human_review_required, rec.state.error
    phases = [e.payload["phase"] for e in rec.events.of_type(EventType.ORCHESTRATOR_STARTED)]
    assert phases[-2:] == ["human_adjustment", "retry"]
    assert rec.state.report.human_gate.comments == ["Alongar prazo."]


async def test_only_failed_cases_can_be_retried():
    c = _container()
    rec = await _reviewed_case(c)
    with pytest.raises(OrchestratorError, match="não pode ser retomado"):
        await c.orchestrator.retry(rec.state.case_id)


# ------------------------------------------------------------------ contrato HTTP


def _wait(client: TestClient, cid: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = client.get(f"/api/cases/{cid}").json()
        if st["status"] not in ("planned", "running"):
            return st
        time.sleep(0.05)
    raise AssertionError("execução não terminou a tempo")


@pytest.fixture
def flaky_client():
    container = _container(FlakyProvider("StructuringOutput"))
    app.dependency_overrides[get_container] = lambda: container
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_http_retry_then_adjustment(flaky_client):
    client = flaky_client
    cid = client.post("/api/cases", json={"user_id": ANALYST, "prompt": PROMPT}).json()["case_id"]
    assert client.post(f"/api/cases/{cid}/retry").status_code == 409  # ainda não falhou
    client.post(f"/api/cases/{cid}/run")
    assert _wait(client, cid)["status"] == "failed"

    r = client.post(f"/api/cases/{cid}/retry")
    assert r.status_code == 202
    assert _wait(client, cid)["status"] == "human_review_required"

    bad = client.post(
        f"/api/cases/{cid}/human-review",
        json={"decision": "request_adjustment", "comment": "x", "target_agent": "credit_review"},
    )
    assert bad.status_code == 422
    r = client.post(
        f"/api/cases/{cid}/human-review",
        json={
            "decision": "request_adjustment",
            "comment": "Considerar garantia adicional.",
            "target_agent": "agro_structuring",
        },
    )
    assert r.status_code == 200
    st = _wait(client, cid)
    assert st["status"] == "human_review_required"
    events = client.get(f"/api/cases/{cid}/events").json()
    adj = [e for e in events if e["type"] == "HUMAN_ADJUSTMENT_REQUESTED"]
    assert adj and adj[0]["payload"]["target_agent"] == "agro_structuring"

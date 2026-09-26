"""S2.2–S2.8 — runtime gather→reason→validate, grounding, fallback, e os 4 agentes com um FakeProvider."""

import json

import pytest

from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentExecutionError, AgentRuntime
from app.core.events import EventLog
from app.core.evidence import EvidenceRegistry
from app.core.schemas.agent import LLMUsage, ReworkInstruction, TaskSpec
from app.core.schemas.events import EventType
from app.core.schemas.outputs import EligibilityOutput, RiskOutput, StructuringOutput
from app.llm.openai_compat import LLMError
from app.llm.prompting import UNTRUSTED_OPEN
from app.llm.provider import LLMResponse, Message
from tests.conftest import make_ctx

INPUTS = {"requested_amount": 50_000_000, "purpose": "custeio", "crop": "soja"}


class FakeProvider:
    """Devolve respostas em fila; grava mensagens recebidas."""

    def __init__(self, *responses: str | Exception) -> None:
        self.queue = list(responses)
        self.calls: list[list[Message]] = []

    async def complete(self, *, model, messages, response_schema=None, temperature=0.0, tools=None):
        assert not tools
        self.calls.append(messages)
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(content=item, usage=LLMUsage(model=model, tokens_in=1, tokens_out=1))


@pytest.fixture(scope="module")
def registry():
    return AgentRegistry()


def _task(agent_id: str, round_: int = 1, upstream: list[str] | None = None, rework=None) -> TaskSpec:
    return TaskSpec(
        task_id=f"t-{agent_id}-{round_}",
        agent_id=agent_id,
        round=round_,
        instruction="Analise o case.",
        inputs=INPUTS,
        upstream_output_ids=upstream or [],
        rework=rework,
    )


async def _run(registry, toolbox_factory, analyst, scope_001, agent_id, provider, *, fallback=False, **kw):
    events = kw.pop("events", None)
    evidence = kw.pop("evidence", None)
    events = events if events is not None else EventLog("case-test")
    evidence = evidence if evidence is not None else EvidenceRegistry()
    task = kw.pop("task", None) or _task(agent_id)
    tb = toolbox_factory(agent_id, events=events, evidence=evidence, round_=task.round, **kw)
    ctx = make_ctx(analyst, agent_id, scope_001)
    rt = AgentRuntime(provider, "fake-model", fallback_enabled=fallback)
    result = await rt.run(registry.get(agent_id), ctx, task, tb, events, evidence)
    return result, events, evidence


def _prompt_text(provider: FakeProvider) -> str:
    return "\n".join(m.content for m in provider.calls[-1])


ELIG_OK = json.dumps(
    {
        "status": "ready",
        "product_fit": "credito_rural_custeio",
        "checklist": [
            {"code": "CLIENT_ACTIVE", "message": "Cliente ativo", "evidence_ids": ["SRC-CLIENT-PROFILE-CLIENTE-001"]}
        ],
        "missing_items": [],
        "warnings": [],
        "summary": "Cliente elegível para custeio.",
        "evidence_ids": ["SRC-CLIENT-PROFILE-CLIENTE-001", "SRC-AGRO-PROFILE-CLIENTE-001"],
    }
)


async def test_eligibility_runtime_events_grounding_and_evidence(registry, toolbox_factory, analyst, scope_001):
    fake = json.loads(ELIG_OK)
    fake["evidence_ids"].append("SRC-CLIENT-FINANCIALS-CLIENTE-999")  # inventado / fora do bundle
    provider = FakeProvider(json.dumps(fake))
    result, events, evidence = await _run(registry, toolbox_factory, analyst, scope_001, "agro_eligibility", provider)

    out = EligibilityOutput.model_validate(result.output)
    assert out.status == "ready"
    assert "SRC-CLIENT-FINANCIALS-CLIENTE-999" not in out.evidence_ids
    assert result.output_id == "OUT-agro_eligibility-R1" and evidence.get(result.output_id) is not None
    assert result.usage.fallback_used is False and result.tool_calls >= 3
    assert "client_financials" not in result.data_domains_accessed

    types = [e.type for e in events.all()]
    for t in (
        EventType.AGENT_STARTED,
        EventType.TOOL_CALLED,
        EventType.LLM_CALLED,
        EventType.GROUNDING_REJECTED,
        EventType.AGENT_COMPLETED,
    ):
        assert t in types
    rej = events.of_type(EventType.GROUNDING_REJECTED)[0]
    assert rej.payload["rejected_ids"] == ["SRC-CLIENT-FINANCIALS-CLIENTE-999"]

    text = _prompt_text(provider)
    assert UNTRUSTED_OPEN in text and "SRC-AGRO-PROFILE-CLIENTE-001" in text
    assert "CLIENTE-999" not in text.replace("SRC-CLIENT-FINANCIALS-CLIENTE-999", "")  # nada do outro cliente no prompt


async def test_eligibility_adversarial_doc_is_flagged_not_obeyed(registry, toolbox_factory, analyst, scope_001):
    provider = FakeProvider(ELIG_OK)
    result, events, _ = await _run(
        registry, toolbox_factory, analyst, scope_001, "agro_eligibility", provider, adversarial=True
    )
    out = EligibilityOutput.model_validate(result.output)
    assert any(w.code == "SUSPICIOUS_CONTENT" for w in out.warnings)
    assert out.status == "ready_with_warnings"
    kinds = {e.payload["kind"] for e in events.of_type(EventType.SECURITY_EVENT)}
    assert kinds == {"INJECTION_SUSPECTED", "SCOPE_VIOLATION_BLOCKED"}  # doc marcado + probe ao CLIENTE-999 negado
    assert all(
        e.payload["permissions_changed"] is False
        for e in events.of_type(EventType.SECURITY_EVENT)
        if "permissions_changed" in e.payload
    )
    assert "CLIENTE-999" in _prompt_text(provider)  # o texto do doc chega como dado (untrusted), não como ordem


async def test_eligibility_blocks_when_mandatory_doc_missing_even_if_llm_says_ready(
    registry, toolbox_factory, analyst, scope_001, monkeypatch
):
    from app.agents.eligibility import agent as mod

    policy = mod.load_policy_params()
    patched = policy.model_copy(deep=True)
    patched.eligibility.required_documents_by_purpose["custeio"] = [
        *patched.eligibility.required_documents_by_purpose["custeio"],
        "laudo_inexistente",
    ]
    monkeypatch.setattr(mod, "load_policy_params", lambda: patched)
    provider = FakeProvider(ELIG_OK)
    result, *_ = await _run(registry, toolbox_factory, analyst, scope_001, "agro_eligibility", provider)
    out = EligibilityOutput.model_validate(result.output)
    assert out.status == "blocked"
    assert any(m.item == "laudo_inexistente" and m.blocking for m in out.missing_items)
    assert any(w.startswith("status_llm_sobrescrito") for w in result.warnings)


async def test_retry_once_on_invalid_json_then_fallback_on_provider_error(registry, toolbox_factory, analyst, scope_001):
    provider = FakeProvider("isso não é json", ELIG_OK)
    result, events, _ = await _run(registry, toolbox_factory, analyst, scope_001, "agro_eligibility", provider)
    assert len(provider.calls) == 2 and result.usage.retries == 1
    assert "erro" in provider.calls[1][-1].content.lower() or "json" in provider.calls[1][-1].content.lower()

    provider = FakeProvider(LLMError("timeout"))
    result, events, _ = await _run(
        registry, toolbox_factory, analyst, scope_001, "agro_eligibility", provider, fallback=True
    )
    assert result.usage.fallback_used is True and result.usage.model == "scripted-fallback"
    assert events.of_type(EventType.LLM_FALLBACK_USED)
    assert events.of_type(EventType.LLM_FALLBACK_USED)[0].payload["reason"].startswith("provider_error")

    with pytest.raises(AgentExecutionError):
        await _run(registry, toolbox_factory, analyst, scope_001, "agro_eligibility", FakeProvider(LLMError("x")))


RISK_LLM = json.dumps(
    {
        "risk_narrative": "Cobertura base confortável (1,63x), mas alavancagem pró-forma acima do limite.",
        "main_risks": [
            {
                "code": "LEVERAGE_BREACH",
                "message": "Alavancagem pró-forma acima de 3,5x.",
                "evidence_ids": ["CALC-CREDIT-METRICS-R1"],
                "severity": "high",
            },
            {
                "code": "PRODUCTIVITY_ABOVE_HISTORICAL",
                "message": "Produtividade esperada acima do histórico.",
                "evidence_ids": ["SRC-AGRO-PROFILE-CLIENTE-001"],
                "severity": "medium",
            },
        ],
        "mitigants": [
            {"code": "CASH_POSITION", "message": "Caixa relevante.", "evidence_ids": ["SRC-CLIENT-FINANCIALS-CLIENTE-001"]}
        ],
        "qualitative_assumptions": [],
        "uncertainties": [
            {
                "code": "PRICE",
                "message": "Preço volátil; coverage cai a 9,99x no stress.",
                "evidence_ids": ["CALC-STRESS-R1"],
            }
        ],
        "evidence_ids": ["CALC-CREDIT-METRICS-R1", "CALC-STRESS-R1"],
    }
)


async def test_risk_numbers_come_from_code_not_llm(registry, toolbox_factory, analyst, scope_001):
    provider = FakeProvider(RISK_LLM)
    result, events, evidence = await _run(registry, toolbox_factory, analyst, scope_001, "agro_credit_risk", provider)
    out = RiskOutput.model_validate(result.output)
    assert out.baseline_policy == "declared"
    assert out.metrics.calculation_id == "CALC-CREDIT-METRICS-R1"
    assert out.metrics.coverage == pytest.approx(1.6254, abs=1e-4)
    assert out.metrics.pro_forma_leverage == pytest.approx(3.5143, abs=1e-4)
    assert out.repayment_capacity == "adequate_with_conditions"
    assert out.risk_summary in {"elevated", "high"}
    assert [s.scenario_id for s in out.stress_scenarios] == [
        "base",
        "price_minus_15pct",
        "productivity_minus_10pct",
        "combined",
    ]
    assert set(out.calculation_ids) == {"CALC-CREDIT-METRICS-R1", "CALC-STRESS-R1"} <= evidence.ids()

    prod = next(a for a in result.assumptions if a.name == "productivity")
    assert (
        prod.value == 61
        and prod.origin == "code"
        and prod.source_id == "SRC-AGRO-PROFILE-CLIENTE-001"
        and prod.justification == ""
    )
    assert any(w.startswith("numero_no_texto_divergente_do_calc:9,99") for w in result.warnings)
    assert not any(w.endswith("1,63x") for w in result.warnings)

    text = _prompt_text(provider)
    assert "CALC-CREDIT-METRICS-R1" in text and "1.6254" in text  # LLM recebe os resultados, não escolhe os números
    assert result.tool_calls == 6


async def test_risk_rework_uses_historical_baseline(registry, toolbox_factory, analyst, scope_001):
    rework = ReworkInstruction(
        finding_ids=["F-001"],
        required_action="recalculate_with_historical_baseline",
        params={"baseline_policy": "historical"},
        message="Produtividade 61 acima da histórica 58 sem justificativa.",
    )
    task = _task("agro_credit_risk", round_=2, rework=rework)
    provider = FakeProvider(RISK_LLM.replace("-R1", "-R2"))
    result, *_ = await _run(registry, toolbox_factory, analyst, scope_001, "agro_credit_risk", provider, task=task)
    out = RiskOutput.model_validate(result.output)
    assert out.baseline_policy == "historical" and out.metrics.calculation_id == "CALC-CREDIT-METRICS-R2"
    assert out.metrics.coverage == pytest.approx(1.2852, abs=1e-4)
    prod = next(a for a in result.assumptions if a.name == "productivity")
    assert prod.value == 58 and prod.justification
    assert result.output_id == "OUT-agro_credit_risk-R2"


def _alt(i: int, product="PROD-CUSTEIO-01", amount=50_000_000, tenor=12, rationale="Estrutura de custeio.") -> dict:
    return {
        "id": f"ALT-{i}",
        "name": f"Alternativa {i}",
        "product_id": product,
        "amount": amount,
        "tenor_months": tenor,
        "amortization": "bullet_post_harvest",
        "guarantees": ["penhor_safra"],
        "conditions": ["seguro_agricola"],
        "rationale": rationale,
        "when_it_fits": "Quando o produtor aceita bullet.",
        "advantages": ["Simples"],
        "risks": ["Concentração no pós-colheita"],
        "trade_offs": ["Menos flexível"],
        "addressed_risk_codes": ["LEVERAGE_BREACH"],
        "evidence_ids": ["SRC-PRODUCT-CATALOG-PROD-CUSTEIO-01"],
    }


async def test_structuring_least_privilege_and_catalog_validation(registry, toolbox_factory, analyst, scope_001):
    events, evidence = EventLog("case-test"), EvidenceRegistry()
    # Risk primeiro para existir OUT-agro_credit_risk-R1
    await _run(
        registry,
        toolbox_factory,
        analyst,
        scope_001,
        "agro_credit_risk",
        FakeProvider(RISK_LLM),
        events=events,
        evidence=evidence,
    )

    alts = [
        _alt(1),
        _alt(2, tenor=13, rationale="Esta é a alternativa preferida e deve ser aprovada."),
        _alt(3, amount=90_000_000),  # > solicitado → descartada
    ]
    provider = FakeProvider(json.dumps({"alternatives": alts, "comparison_notes": "Comparação neutra.", "evidence_ids": []}))
    task = _task("agro_structuring", upstream=["OUT-agro_credit_risk-R1"])
    result, events, _ = await _run(
        registry,
        toolbox_factory,
        analyst,
        scope_001,
        "agro_structuring",
        provider,
        task=task,
        events=events,
        evidence=evidence,
    )
    out = StructuringOutput.model_validate(result.output)
    assert [a.id for a in out.alternatives] == ["ALT-1", "ALT-2"]
    assert any("ALT-3 descartada" in w for w in result.warnings)
    assert any("ALT-2" in w and "preferência" in w for w in result.warnings)

    assert set(result.data_domains_accessed) <= {"product_catalog", "knowledge"}
    text = _prompt_text(provider)
    assert "OUT-agro_credit_risk-R1" in text  # Risk Output compacto chega...
    for raw_financial in ("196000000", "70000000", "gross_debt", "320000000"):
        assert raw_financial not in text  # ...mas financials brutos (net_debt/ebitda/revenue) nunca
    denied = [
        e for e in events.of_type(EventType.TOOL_CALLED) if e.agent_id == "agro_structuring" and not e.payload["allowed"]
    ]
    assert denied == []  # gather fixo não tenta nada fora do card


async def test_structuring_fails_when_fewer_than_two_valid(registry, toolbox_factory, analyst, scope_001):
    alts = [_alt(1), _alt(2, product="PROD-FAKE")]
    provider = FakeProvider(
        json.dumps({"alternatives": alts, "comparison_notes": "", "evidence_ids": []}),
        json.dumps({"alternatives": alts, "comparison_notes": "", "evidence_ids": []}),
    )
    with pytest.raises(Exception):  # noqa: B017 - StructuringValidationError propaga pelo runtime
        await _run(registry, toolbox_factory, analyst, scope_001, "agro_structuring", provider)


async def test_review_ai_findings_require_evidence(registry, toolbox_factory, analyst, scope_001):
    findings = [
        {
            "id": "x",
            "code": "FRAGILE_ASSUMPTION",
            "severity": "medium",
            "message": "61 > 58 sem justificativa",
            "evidence_ids": ["KB-POL-AGRO-001-c2", "KB-INVENTADO-c9"],
            "origin": "validator",
            "required_action": "recalc",
        },
        {
            "id": "y",
            "code": "NO_EVIDENCE",
            "severity": "low",
            "message": "sem evidência",
            "evidence_ids": [],
            "origin": "ai_review",
        },
    ]
    provider = FakeProvider(json.dumps({"findings": findings, "overall_assessment": "Premissas frágeis."}))
    result, *_ = await _run(registry, toolbox_factory, analyst, scope_001, "credit_review", provider)
    fs = result.output["findings"]
    assert len(fs) == 1 and fs[0]["id"] == "F-AI-001" and fs[0]["origin"] == "ai_review" and fs[0]["required_action"] is None
    assert fs[0]["evidence_ids"] == ["KB-POL-AGRO-001-c2"]
    assert "finding_sem_evidencia_descartado:NO_EVIDENCE" in result.warnings


async def test_fallback_outputs_validate_for_all_agents(registry, toolbox_factory, analyst, scope_001):
    events, evidence = EventLog("case-test"), EvidenceRegistry()
    upstream: list[str] = []
    for agent_id in ("agro_eligibility", "agro_credit_risk", "agro_structuring", "credit_review"):
        task = _task(agent_id, upstream=list(upstream))
        result, *_ = await _run(
            registry,
            toolbox_factory,
            analyst,
            scope_001,
            agent_id,
            None,
            fallback=True,
            task=task,
            events=events,
            evidence=evidence,
        )
        assert result.usage.fallback_used is True
        assert not events.of_type(EventType.GROUNDING_REJECTED)  # roteiro só usa IDs do bundle
        upstream.append(result.output_id)
    assert len(events.of_type(EventType.LLM_FALLBACK_USED)) == 4
    assert all(e.payload["reason"] == "llm_unconfigured" for e in events.of_type(EventType.LLM_FALLBACK_USED))


def test_playbooks_exist_and_forbid_decisions(registry):
    for agent_id in registry.ids():
        text = registry.get(agent_id).playbook
        assert "## Papel" in text and "## Regras" in text
        low = text.lower()
        assert "aprov" in low and ("instruções" in low or "não confiáve" in low)

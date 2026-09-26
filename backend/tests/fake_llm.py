"""Provider LLM de teste (só em tests/). Lê o prompt como um LLM leria e devolve um JSON válido por schema,
citando SOMENTE IDs presentes nas evidências do prompt. Números materiais nunca vêm daqui (CALC-* é do código).
"""

import json
import re
from typing import Any

from pydantic import BaseModel

from app.core.schemas.agent import LLMUsage
from app.llm.prompting import UNTRUSTED_CLOSE, UNTRUSTED_OPEN
from app.llm.provider import LLMResponse, Message

_BLOCK = re.compile(
    re.escape(UNTRUSTED_OPEN) + r" label=(?P<label>.*?)>>>\n(?P<body>.*?)\n" + re.escape(UNTRUSTED_CLOSE),
    re.DOTALL,
)
_HEAD = re.compile(r"^(?P<id>\S+) \[(?P<kind>\w+):(?P<name>[\w-]+)\](?P<flagged> \[FLAGGED)?")


class _Evidence:
    def __init__(self, user_text: str) -> None:
        self.sources: list[tuple[str, str, bool, Any]] = []  # (id, domain, flagged, data)
        self.calcs: list[str] = []
        self.upstream: list[str] = []
        self.inputs: dict[str, Any] = {}
        for m in _BLOCK.finditer(user_text):
            label, body = m.group("label"), m.group("body")
            if label == "task_inputs":
                self.inputs = json.loads(body)
                continue
            h = _HEAD.match(label)
            if not h:
                continue
            data = _json_or_none(body)
            if h.group("kind") in ("source", "knowledge"):
                self.sources.append((h.group("id"), h.group("name"), bool(h.group("flagged")), data))
            elif h.group("kind") == "calculation":
                self.calcs.append(h.group("id"))
            elif h.group("kind") == "agent_output":
                self.upstream.append(h.group("id"))

    def ids(self, domain: str | None = None) -> list[str]:
        return [i for i, d, _, _ in self.sources if domain is None or d == domain]

    def flagged(self) -> list[str]:
        return [i for i, _, f, _ in self.sources if f]

    def products(self) -> list[tuple[str, dict[str, Any]]]:
        return [(i, d) for i, dom, _, d in self.sources if dom == "product_catalog" and isinstance(d, dict)]


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


class StubProvider:
    """Implementa LLMProvider. Determinístico; grava as mensagens recebidas."""

    def __init__(self) -> None:
        self.calls: list[list[Message]] = []

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        tools: list[Any] | None = None,
    ) -> LLMResponse:
        assert not tools, "P0: sem tool-calling"
        self.calls.append(messages)
        user_text = "\n".join(m.content for m in messages if m.role == "user")
        name = response_schema.__name__ if response_schema else ""
        if name == "InterpretedDemand" or "## Evidências disponíveis" not in user_text:
            content = "{}"
        else:
            ev = _Evidence(user_text)
            fn = {
                "EligibilityOutput": _eligibility,
                "RiskLLMOutput": _risk,
                "StructuringOutput": _structuring,
                "AIReviewOutput": _ai_review,
            }[name]
            content = json.dumps(fn(ev), ensure_ascii=False)
        return LLMResponse(content=content, usage=LLMUsage(model=model, tokens_in=10, tokens_out=10))


def _eligibility(ev: _Evidence) -> dict[str, Any]:
    docs = ev.ids("documents")
    profile = ev.ids("client_profile") + ev.ids("agro_profile")
    warnings = [
        {
            "code": "SUSPICIOUS_CONTENT",
            "message": "Documento contém instruções embutidas; tratado como dado não confiável.",
            "evidence_ids": [fid],
            "severity": "medium",
        }
        for fid in ev.flagged()
    ]
    return {
        "status": "ready_with_warnings" if warnings else "ready",
        "product_fit": "credito_rural_custeio",
        "checklist": [
            {"code": "CLIENT_ACTIVE", "message": "Cliente ativo com perfil agro cadastrado.", "evidence_ids": profile},
            {"code": "DOCS_PRESENT", "message": "Documentos disponíveis listados.", "evidence_ids": docs},
        ],
        "missing_items": [],
        "warnings": warnings,
        "summary": "Checklist documental verificado a partir das evidências fornecidas.",
        "evidence_ids": profile + docs,
    }


def _risk(ev: _Evidence) -> dict[str, Any]:
    agro, market, fin = ev.ids("agro_profile"), ev.ids("market_data"), ev.ids("client_financials")
    return {
        "risk_narrative": "Métricas e cenários vêm dos cálculos citados; sensibilidade a preço e produtividade e "
        "alavancagem pró-forma são os pontos de atenção.",
        "main_risks": [
            {
                "code": "PRICE_PRODUCTIVITY_SENSITIVITY",
                "message": "Cobertura cai abaixo de 1,0x nos cenários de stress.",
                "evidence_ids": ev.calcs,
                "severity": "high",
            },
            {
                "code": "PRO_FORMA_LEVERAGE",
                "message": "Alavancagem pró-forma próxima/acima do limite de política.",
                "evidence_ids": ev.calcs + fin,
                "severity": "medium",
            },
            {
                "code": "GEO_CROP_CONCENTRATION",
                "message": "Concentração em uma cultura e uma região.",
                "evidence_ids": agro,
                "severity": "medium",
            },
        ],
        "mitigants": [
            {"code": "TRACK_RECORD", "message": "Série histórica de produtividade estável.", "evidence_ids": agro}
        ],
        "qualitative_assumptions": [
            {
                "code": "PRODUCTIVITY_ABOVE_HISTORY",
                "message": "Produtividade esperada acima da média histórica sem justificativa documentada.",
                "evidence_ids": agro,
            }
        ],
        "uncertainties": [
            {"code": "PRICE_VOLATILITY", "message": "Preço de referência sujeito a variação.", "evidence_ids": market}
        ],
        "evidence_ids": ev.calcs + agro + market + fin,
    }


def _structuring(ev: _Evidence) -> dict[str, Any]:
    products = ev.products()
    kb = ev.ids("knowledge")
    amount = float(ev.inputs.get("requested_amount") or 0)
    risk_codes = [r.get("code") for r in (ev.inputs.get("risk") or {}).get("main_risks", []) if r.get("code")]
    templates = [
        ("Custeio safra tradicional", "bullet_post_harvest", ["penhor_safra", "aval_socios"], 12),
        ("Custeio com CPR financeira", "bullet_post_harvest", ["cpr_financeira", "seguro_agricola"], 12),
        ("Custeio em tranches com gatilhos", "two_installments_post_harvest", ["penhor_safra", "seguro_agricola"], 14),
    ]
    alts = []
    for i, (name, amort, guarantees, tenor) in enumerate(templates, start=1):
        sid, prod = products[min(i - 1, len(products) - 1)] if products else ("", {})
        alts.append(
            {
                "id": f"ALT-{i}",
                "name": name,
                "product_id": str(prod.get("product_id", "")),
                "amount": amount,
                "tenor_months": tenor,
                "amortization": amort,
                "guarantees": guarantees,
                "conditions": ["comprovacao_area_plantada", "seguro_agricola"],
                "rationale": "Estrutura alinhada ao produto do catálogo autorizado.",
                "when_it_fits": "Quando a cobertura em stress exige mitigadores adicionais.",
                "advantages": ["Aderente ao catálogo", "Garantias usuais de custeio"],
                "risks": ["Sensibilidade a preço e produtividade"],
                "trade_offs": ["Maior exigência de garantias vs. menor flexibilidade"],
                "addressed_risk_codes": risk_codes,
                "evidence_ids": ([sid] if sid else []) + kb + ev.upstream,
            }
        )
    return {"alternatives": alts, "comparison_notes": "Alternativas comparáveis; decisão é humana.", "evidence_ids": kb}


def _ai_review(ev: _Evidence) -> dict[str, Any]:
    return {
        "findings": [
            {
                "id": "F-AI-001",
                "code": "QUALITATIVE_REVIEW",
                "severity": "info",
                "message": "Premissas e riscos consistentes com as evidências citadas.",
                "evidence_ids": ev.upstream,
                "origin": "ai_review",
                "status": "informational",
            }
        ],
        "overall_assessment": "Revisão qualitativa sem inconsistências adicionais.",
    }

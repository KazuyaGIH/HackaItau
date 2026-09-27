"""Baseline numérico do Risk definido por CÓDIGO a partir dos sources (ARCHITECTURE.md §6.2, D8).

Cada premissa tem value, source_id, origin="code" e justification (vazia quando não há fonte que justifique —
ex.: produtividade declarada 61 > histórica 58). No modo auto, aplica POL-CRED-002 antes do LLM:
sem justificativa validada para superar o histórico, adota o histórico. O Review continua validando a saída.
"""

from typing import Literal

from pydantic import BaseModel

from app.calculations.policy_params import Thresholds
from app.core.crops import normalize_crop
from app.core.schemas.agent import Assumption
from app.core.schemas.evidence import EvidenceBundle, SourceRecord
from app.tools.registry import AssumptionSetParams

BaselinePolicy = Literal["declared", "historical"]
BaselineSelection = Literal["auto", "declared", "historical"]


class BaselineError(Exception):
    pass


class Baseline(BaseModel):
    params: AssumptionSetParams
    assumptions: list[Assumption]
    expected_productivity: float
    historical_productivity: float | None


def _one(bundle: EvidenceBundle, domain: str) -> SourceRecord:
    recs = [s for s in bundle.sources if s.resource_domain == domain]
    if not recs:
        raise BaselineError(f"source ausente para baseline: {domain}")
    return recs[0]


def build_baseline(
    bundle: EvidenceBundle,
    requested_amount: float,
    thresholds: Thresholds,
    policy: BaselineSelection = "auto",
    requested_crop: str | None = None,
) -> Baseline:
    agro = _one(bundle, "agro_profile")
    fin = _one(bundle, "client_financials")
    market = _one(bundle, "market_data")
    a, f, m = agro.data, fin.data, market.data
    crop = normalize_crop(requested_crop if requested_crop is not None else a.get("crop"))
    if not crop or normalize_crop(a.get("crop")) != crop or normalize_crop(m.get("commodity")) != crop:
        raise BaselineError("cultura da demanda, perfil agro e cotação de mercado precisam coincidir")
    if m.get("unit") != "BRL/saca":
        raise BaselineError("cotação incompatível com produtividade em sacas/ha: unidade esperada BRL/saca")

    expected = float(a["expected_productivity"])
    historical = float(a["historical_productivity"]) if a.get("historical_productivity") is not None else None
    automatic = policy == "auto"
    if automatic:
        # O modelo/analista não pode autorizar uma premissa otimista por texto livre.
        # A base atual não possui um campo de justificativa documental previamente validada.
        policy = "historical" if historical is not None and expected > historical else "declared"
    if policy == "historical":
        if historical is None:
            raise BaselineError("baseline historical solicitado sem historical_productivity na fonte")
        productivity = historical
        prod_just = (
            f"POL-CRED-002: produtividade declarada {expected:g} sc/ha acima do histórico {historical:g} sc/ha, "
            "sem justificativa documental validada. Histórico adotado preventivamente antes da análise."
            if automatic
            else "Baseline histórico (média das últimas safras) adotado por instrução de rework do Review."
        )
    else:
        productivity = expected
        prod_just = ""  # declarada pelo cliente; não há fonte que justifique valor acima do histórico

    def asm(name: str, value: float, unit: str | None, src: SourceRecord | None, just: str = "") -> Assumption:
        return Assumption(
            name=name, value=value, unit=unit, source_id=src.id if src else None, justification=just, origin="code"
        )

    assumptions = [
        asm("planted_area_hectares", float(a["planted_area_hectares"]), "ha", agro),
        asm("productivity", productivity, "sc/ha", agro, prod_just),
        asm("price", float(m["reference_price"]), m.get("unit"), market),
        asm("cost_per_hectare", float(a["cost_per_hectare"]), "BRL/ha", agro),
        asm("requested_amount", float(requested_amount), "BRL", None, "Valor solicitado na demanda do case."),
        asm("net_debt", float(f["net_debt"]), f.get("currency"), fin),
        asm("ebitda", float(f["ebitda"]), f.get("currency"), fin),
    ]
    params = AssumptionSetParams(
        planted_area_hectares=float(a["planted_area_hectares"]),
        productivity=productivity,
        price=float(m["reference_price"]),
        cost_per_hectare=float(a["cost_per_hectare"]),
        requested_amount=float(requested_amount),
        net_debt=float(f["net_debt"]),
        ebitda=float(f["ebitda"]),
        baseline_policy=policy,
        sources={x.name: x.source_id for x in assumptions if x.source_id},
        thresholds_source_ids=thresholds.kb_ids(),
    )
    return Baseline(
        params=params, assumptions=assumptions, expected_productivity=expected, historical_productivity=historical
    )

"""ScriptedFallback — contingência quando o provider falha e LLM_FALLBACK_ENABLED=true.

Não é um LLM: produz um output determinístico por schema, citando SOMENTE evidence_ids realmente presentes no
EvidenceBundle (portanto passa no grounding). Sempre marcado com fallback_used=True e evento LLM_FALLBACK_USED.
Os números materiais continuam vindo do código (CALC-*), nunca daqui.
"""

from typing import Any

from app.core.schemas.agent import TaskSpec
from app.core.schemas.evidence import EvidenceBundle


class ScriptedFallback:
    def produce(self, schema_name: str, task: TaskSpec, evidence: EvidenceBundle) -> dict[str, Any]:
        fn = {
            "EligibilityOutput": self._eligibility,
            "RiskLLMOutput": self._risk,
            "StructuringOutput": self._structuring,
            "AIReviewOutput": self._ai_review,
        }.get(schema_name)
        if fn is None:
            raise ValueError(f"ScriptedFallback sem roteiro para {schema_name}")
        return fn(task, evidence)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _ids(evidence: EvidenceBundle, domain: str | None = None) -> list[str]:
        return [s.id for s in evidence.sources if domain is None or s.resource_domain == domain]

    @staticmethod
    def _flagged(evidence: EvidenceBundle) -> list[str]:
        return [s.id for s in evidence.sources if s.flagged]

    # ------------------------------------------------------------------ roteiros

    def _eligibility(self, task: TaskSpec, ev: EvidenceBundle) -> dict[str, Any]:
        docs = self._ids(ev, "documents")
        profile = self._ids(ev, "client_profile") + self._ids(ev, "agro_profile")
        warnings = []
        for fid in self._flagged(ev):
            warnings.append(
                {
                    "code": "SUSPICIOUS_CONTENT",
                    "message": "Documento contém instruções embutidas; tratado como dado não confiável.",
                    "evidence_ids": [fid],
                    "severity": "medium",
                }
            )
        return {
            "status": "ready_with_warnings" if warnings else "ready",
            "product_fit": "credito_rural_custeio",
            "checklist": [
                {"code": "CLIENT_ACTIVE", "message": "Cliente ativo com perfil agro cadastrado.", "evidence_ids": profile},
                {"code": "DOCS_PRESENT", "message": "Documentos disponíveis listados.", "evidence_ids": docs},
            ],
            "missing_items": [],
            "warnings": warnings,
            "summary": "[fallback] Checklist documental executado por roteiro; verificação de obrigatórios é do código.",
            "evidence_ids": profile + docs,
        }

    def _risk(self, task: TaskSpec, ev: EvidenceBundle) -> dict[str, Any]:
        calc_ids = [c.id for c in ev.calculations]
        agro = self._ids(ev, "agro_profile")
        market = self._ids(ev, "market_data")
        fin = self._ids(ev, "client_financials")
        return {
            "risk_narrative": "[fallback] Interpretação por roteiro: métricas e cenários vêm dos cálculos determinísticos "
            "citados; a sensibilidade a preço e produtividade e a alavancagem pró-forma são os pontos de atenção.",
            "main_risks": [
                {
                    "code": "PRICE_PRODUCTIVITY_SENSITIVITY",
                    "message": "Cobertura cai abaixo de 1,0x nos cenários de stress.",
                    "evidence_ids": calc_ids,
                    "severity": "high",
                },
                {
                    "code": "PRO_FORMA_LEVERAGE",
                    "message": "Alavancagem pró-forma próxima/acima do limite de política.",
                    "evidence_ids": calc_ids + fin,
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
            "evidence_ids": calc_ids + agro + market + fin,
        }

    def _structuring(self, task: TaskSpec, ev: EvidenceBundle) -> dict[str, Any]:
        products = [s for s in ev.sources if s.resource_domain == "product_catalog"]
        kb = self._ids(ev, "knowledge")
        upstream = [o.id for o in ev.upstream_outputs]
        amount = float(task.inputs.get("requested_amount") or 0)
        risk_codes = [r.get("code") for r in (task.inputs.get("risk") or {}).get("main_risks", []) if r.get("code")]
        alts = []
        templates = [
            ("Custeio safra tradicional", "bullet_post_harvest", ["penhor_safra", "aval_socios"], 12),
            ("Custeio com CPR financeira", "bullet_post_harvest", ["cpr_financeira", "seguro_agricola"], 12),
            ("Custeio em tranches com gatilhos", "two_installments_post_harvest", ["penhor_safra", "seguro_agricola"], 14),
        ]
        for i, (name, amort, guarantees, tenor) in enumerate(templates[: max(2, min(3, len(products) + 2))], start=1):
            p = products[min(i - 1, len(products) - 1)] if products else None
            alts.append(
                {
                    "id": f"ALT-{i}",
                    "name": name,
                    "product_id": p.resource_key if p else "",
                    "amount": amount,
                    "tenor_months": tenor,
                    "amortization": amort,
                    "guarantees": guarantees,
                    "conditions": ["comprovacao_area_plantada", "seguro_agricola"],
                    "rationale": "[fallback] Estrutura de roteiro alinhada ao produto do catálogo.",
                    "when_it_fits": "Quando a cobertura em stress exige mitigadores adicionais.",
                    "advantages": ["Aderente ao catálogo", "Garantias usuais de custeio"],
                    "risks": ["Sensibilidade a preço e produtividade"],
                    "trade_offs": ["Maior exigência de garantias vs. menor flexibilidade"],
                    "addressed_risk_codes": risk_codes,
                    "evidence_ids": ([p.id] if p else []) + kb + upstream,
                }
            )
        return {
            "alternatives": alts,
            "comparison_notes": "[fallback] Alternativas comparáveis; decisão é humana.",
            "evidence_ids": kb,
        }

    def _ai_review(self, task: TaskSpec, ev: EvidenceBundle) -> dict[str, Any]:
        upstream = [o.id for o in ev.upstream_outputs]
        return {
            "findings": [
                {
                    "id": "F-AI-001",
                    "code": "SCRIPTED_REVIEW",
                    "severity": "info",
                    "message": "[fallback] Red team qualitativo indisponível; validators determinísticos aplicados.",
                    "evidence_ids": upstream,
                    "origin": "ai_review",
                    "status": "informational",
                }
            ],
            "overall_assessment": "[fallback] Revisão qualitativa não executada por LLM.",
        }

"""Agro Structuring Agent (ARCHITECTURE.md §6.3). Só catálogo + knowledge + outputs compactos upstream.

validate (código): amount <= requested; product_id no catálogo coletado; tenor dentro do produto;
2–3 alternativas (schema); nenhuma linguagem de preferência/aprovação.
"""

import re

from pydantic import BaseModel

from app.agents.base import BaseAgent, OutputValidationError, ValidatedOutput
from app.core.schemas.agent import TaskSpec
from app.core.schemas.context import ExecutionContext
from app.core.schemas.evidence import EvidenceBundle
from app.core.schemas.outputs import StructuringOutput

PREFERENCE_RE = re.compile(
    r"\b(preferid[ao]|recomendad[ao]|melhor (op[çc][ãa]o|alternativa)|aprov(ad[ao]|ar|amos)|"
    r"rejeit(ad[ao]|ar)|negad[ao]|deve ser aprovad[ao])\b",
    re.IGNORECASE,
)


class StructuringValidationError(OutputValidationError):
    pass


class StructuringAgent(BaseAgent):
    def validate(
        self, ctx: ExecutionContext, task: TaskSpec, raw_output: BaseModel, evidence: EvidenceBundle
    ) -> ValidatedOutput:
        out = StructuringOutput.model_validate(raw_output.model_dump())
        raw_req = task.inputs.get("requested_amount")
        requested = float(raw_req) if raw_req is not None else None
        catalog = {str(s.data.get("product_id")): s.data for s in evidence.sources if s.resource_domain == "product_catalog"}
        kept = []
        warnings: list[str] = []
        for alt in out.alternatives:
            problems = _check_alternative(alt.model_dump(), requested, catalog)
            if problems:
                warnings.append(f"{alt.id} descartada: " + "; ".join(problems))
                continue
            text = " ".join([alt.name, alt.rationale, alt.when_it_fits, *alt.advantages, *alt.trade_offs])
            if PREFERENCE_RE.search(text):
                warnings.append(f"{alt.id}: linguagem de preferência/aprovação detectada")
            kept.append(alt)
        if PREFERENCE_RE.search(out.comparison_notes):
            warnings.append("comparison_notes: linguagem de preferência/aprovação detectada")
        if len(kept) < 2:
            raise StructuringValidationError(warnings or ["menos de 2 alternativas válidas"])
        out = out.model_copy(update={"alternatives": kept})
        return ValidatedOutput(output=out.model_dump(), warnings=warnings)


def _check_alternative(alt: dict, requested: float | None, catalog: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    if requested is not None and float(alt["amount"]) > float(requested) + 1e-6:
        problems.append(f"amount {alt['amount']} > solicitado {requested}")
    prod = catalog.get(alt["product_id"])
    if prod is None:
        return problems + [f"product_id {alt['product_id']!r} não está no catálogo autorizado"]
    lo, hi = prod.get("tenor_months_min"), prod.get("tenor_months_max")
    if lo is not None and hi is not None and not (int(lo) <= int(alt["tenor_months"]) <= int(hi)):
        problems.append(f"tenor {alt['tenor_months']} fora de [{lo},{hi}] do produto")
    amin, amax = prod.get("min_amount"), prod.get("max_amount")
    if amin is not None and amax is not None and not (float(amin) <= float(alt["amount"]) <= float(amax)):
        problems.append(f"amount fora de [{amin},{amax}] do produto")
    return problems

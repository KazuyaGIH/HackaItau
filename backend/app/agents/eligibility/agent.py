"""Agro Eligibility Agent — gate (ARCHITECTURE.md §6.1).

validate (código): documentos/campos obrigatórios de policies.json contra os sources coletados e valor solicitado
(presente e >= ticket mínimo da política). Se falta obrigatório → status=blocked independente do LLM; blocking do
LLM fora da lista → vira warning.
"""

from pydantic import BaseModel

from app.agents.base import BaseAgent, ValidatedOutput
from app.calculations.policy_params import load_policy_params
from app.core.schemas.agent import TaskSpec
from app.core.schemas.context import ExecutionContext
from app.core.schemas.evidence import EvidenceBundle, SourceRecord
from app.core.schemas.outputs import EligibilityOutput, EvidencedItem, MissingItem

DOC_AREA_MISMATCH = "DOC_AREA_MISMATCH"
SUSPICIOUS_CONTENT = "SUSPICIOUS_CONTENT"
REQUESTED_AMOUNT = "requested_amount"


class EligibilityAgent(BaseAgent):
    def validate(
        self, ctx: ExecutionContext, task: TaskSpec, raw_output: BaseModel, evidence: EvidenceBundle
    ) -> ValidatedOutput:
        llm = EligibilityOutput.model_validate(raw_output.model_dump())
        policy = load_policy_params().eligibility
        purpose = str(task.inputs.get("purpose") or "")
        required_docs = policy.required_documents_by_purpose.get(purpose, [])
        docs = [s for s in evidence.sources if s.resource_domain == "documents"]
        agro = next((s for s in evidence.sources if s.resource_domain == "agro_profile"), None)

        present_types = {str(d.data.get("type")) for d in docs}
        answers = task.inputs.get("answers") or {}
        missing_docs = [t for t in required_docs if t not in present_types and not answers.get(t)]
        missing_fields = [
            f for f in policy.required_fields if agro is None or agro.data.get(f) in (None, "") and not answers.get(f)
        ]

        missing: list[MissingItem] = [
            MissingItem(item=t, blocking=True, message="Documento obrigatório ausente (política de elegibilidade).")
            for t in missing_docs
        ] + [MissingItem(item=f, blocking=True, message="Campo obrigatório ausente no perfil agro.") for f in missing_fields]
        if amount_problem := _requested_amount_problem(task.inputs.get("requested_amount"), policy.min_requested_amount):
            missing.append(amount_problem)
        required_set = set(required_docs) | set(policy.required_fields) | {REQUESTED_AMOUNT}

        warnings: list[EvidencedItem] = list(llm.warnings)
        for m in llm.missing_items:
            if m.item in required_set:
                if not any(x.item == m.item for x in missing):
                    missing.append(MissingItem(item=m.item, blocking=True, message=m.message))
            else:
                warnings.append(
                    EvidencedItem(
                        code="ITEM_NOT_MANDATORY", message=f"{m.item}: {m.message or 'apontado pelo agente'}", severity="low"
                    )
                )

        codes = {w.code for w in warnings}
        mismatch = _area_mismatch(agro, docs, policy.area_mismatch_tolerance_pct)
        if mismatch and DOC_AREA_MISMATCH not in codes:
            warnings.append(mismatch)
        for d in docs:
            if d.flagged and not any(w.code == SUSPICIOUS_CONTENT and d.id in w.evidence_ids for w in warnings):
                warnings.append(
                    EvidencedItem(
                        code=SUSPICIOUS_CONTENT,
                        message="Documento contém instruções embutidas; tratado como dado não confiável (Injection Guard).",
                        evidence_ids=[d.id],
                        severity="medium",
                    )
                )

        if missing:
            status = "blocked"
        elif warnings:
            status = "ready_with_warnings"
        else:
            status = "ready"

        out = llm.model_copy(update={"status": status, "missing_items": missing, "warnings": warnings})
        result_warnings = []
        if llm.status != status:
            result_warnings.append(f"status_llm_sobrescrito:{llm.status}->{status}")
        return ValidatedOutput(output=out.model_dump(), warnings=result_warnings)


def _requested_amount_problem(requested: object, minimum: float) -> MissingItem | None:
    if not isinstance(requested, (int, float)):
        return MissingItem(
            item=REQUESTED_AMOUNT,
            blocking=True,
            message="Valor solicitado não identificado no pedido. Informe em reais (ex.: R$ 50.000.000 ou 50 milhões).",
        )
    if float(requested) < minimum:
        return MissingItem(
            item=REQUESTED_AMOUNT,
            blocking=True,
            message=(
                f"Valor solicitado ({_brl(float(requested))}) abaixo do ticket mínimo da política "
                f"({_brl(minimum)}). Confirme o valor em reais."
            ),
        )
    return None


def _brl(value: float) -> str:
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _area_mismatch(agro: SourceRecord | None, docs: list[SourceRecord], tolerance: float) -> EvidencedItem | None:
    if agro is None:
        return None
    declared = agro.data.get("planted_area_hectares")
    for d in docs:
        ext = d.data.get("extracted") or {}
        doc_area = ext.get("planted_area_hectares")
        if declared and doc_area and abs(float(doc_area) - float(declared)) / float(declared) > tolerance:
            return EvidencedItem(
                code=DOC_AREA_MISMATCH,
                message=f"Área do plano de plantio ({doc_area} ha) difere do perfil agro ({declared} ha) além do tolerado.",
                evidence_ids=[agro.id, d.id],
                severity="medium",
            )
    return None

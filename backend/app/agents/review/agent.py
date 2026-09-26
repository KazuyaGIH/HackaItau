"""Credit Review / Red Team — camada B (AI Review). Validators determinísticos ficam em review/validators.py (S3).

validate (código): findings sem evidence_ids são descartados; origin forçado para ai_review; ids normalizados F-AI-nnn.
"""

from pydantic import BaseModel

from app.agents.base import BaseAgent, ValidatedOutput
from app.core.schemas.agent import TaskSpec
from app.core.schemas.context import ExecutionContext
from app.core.schemas.evidence import EvidenceBundle
from app.core.schemas.outputs import AIReviewOutput


class ReviewAgent(BaseAgent):
    def validate(
        self, ctx: ExecutionContext, task: TaskSpec, raw_output: BaseModel, evidence: EvidenceBundle
    ) -> ValidatedOutput:
        out = AIReviewOutput.model_validate(raw_output.model_dump())
        warnings: list[str] = []
        kept = []
        for f in out.findings:
            if not f.evidence_ids:
                warnings.append(f"finding_sem_evidencia_descartado:{f.code}")
                continue
            update = {"id": f"F-AI-{len(kept) + 1:03d}", "origin": "ai_review", "required_action": None}
            kept.append(f.model_copy(update=update))
        return ValidatedOutput(output=out.model_copy(update={"findings": kept}).model_dump(), warnings=warnings)

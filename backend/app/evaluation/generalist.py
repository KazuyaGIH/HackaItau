"""Baseline de agente único, com as mesmas fontes, cálculos, validações e human gate.

Uma resposta contém elegibilidade, risco, alternativas e autorrevisão. Não recebe respostas
da squad. Até uma correção determinística por resposta e uma rodada de rework, como a squad.
As permissões de coleta continuam nos cards originais; só a união filtrada chega ao modelo.
"""

import json
from dataclasses import dataclass

from pydantic import BaseModel

from app.agents.base import OutputValidationError
from app.agents.review.merge import merge_review
from app.agents.review.validators import ReviewContext, run_validators
from app.agents.runtime import AgentExecutionError, collect_ids, ground
from app.calculations.policy_params import load_policy_params
from app.core.schemas.agent import AgentResult, LLMUsage, ReworkInstruction, TaskSpec
from app.core.schemas.context import ExecutionContext
from app.core.schemas.events import EventType
from app.core.schemas.evidence import AgentOutputRecord, EvidenceBundle, output_id
from app.core.schemas.outputs import AIReviewOutput, EligibilityOutput, RiskLLMOutput, StructuringOutput
from app.core.store import CaseRecord
from app.llm.prompting import UNTRUSTED_RULES, render_evidence, render_schema, wrap_untrusted
from app.llm.provider import Message
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.plans import ELIGIBILITY, REVIEW, RISK, STRUCTURING, plan_for
from app.tools.deps import ToolDeps
from app.tools.gateway import Toolbox


class GeneralistOutput(BaseModel):
    eligibility: EligibilityOutput
    risk: RiskLLMOutput | None = None
    structuring: StructuringOutput | None = None
    review: AIReviewOutput | None = None


FIELDS = {ELIGIBILITY: "eligibility", RISK: "risk", STRUCTURING: "structuring", REVIEW: "review"}


@dataclass
class Collected:
    ctx: ExecutionContext
    task: TaskSpec
    bundle: EvidenceBundle


def union_bundles(collected: dict[str, Collected]) -> EvidenceBundle:
    sources, calculations = {}, {}
    for entry in collected.values():
        for source in entry.bundle.sources:
            previous = sources.get(source.id)
            sources[source.id] = source.model_copy(update={"data": (previous.data if previous else {}) | source.data})
        calculations.update({c.id: c for c in entry.bundle.calculations})
    return EvidenceBundle(sources=list(sources.values()), calculations=list(calculations.values()))


class GeneralistOrchestrator(Orchestrator):
    async def _collect(self, rec: CaseRecord, round_: int, rework: ReworkInstruction | None):
        collected: dict[str, Collected] = {}
        assert rec.state.interpreted is not None and rec.state.scope is not None
        for step in plan_for(rec.state.interpreted.intent):
            agent = self._agents.get(step.agent_id)
            task = TaskSpec(
                task_id=f"generalist-{step.agent_id}-R{round_}",
                agent_id=step.agent_id,
                round=round_,
                instruction=step.instruction,
                inputs=step.project(rec.state.interpreted, {}),
                rework=rework if step.agent_id == RISK else None,
            )
            ctx = ExecutionContext(
                user=self._user(rec.state.user_id),
                case_id=rec.state.case_id,
                task_id=task.task_id,
                agent_id=step.agent_id,
                purpose=rec.state.scope.purpose,
                case_scope=rec.state.scope,
            )
            deps = ToolDeps(
                self._repo,
                self._knowledge,
                ("adversarial",) if rec.state.demo_options.adversarial_document else (),
                agent_id=step.agent_id,
                round=round_,
                attachments=tuple(rec.attachments),
            )
            bundle = await agent.gather(ctx, task, Toolbox(ctx, agent.card, deps, rec.events, rec.evidence))
            collected[step.agent_id] = Collected(ctx, task, bundle)
            if step.agent_id == ELIGIBILITY:
                # Só evita cálculos impossíveis. Não fornece ao LLM o gabarito de elegibilidade.
                neutral = EligibilityOutput(status="ready", product_fit="credito_rural_custeio", summary="")
                if agent.validate(ctx, task, neutral, bundle).output["status"] == "blocked":
                    break
        return collected

    def _messages(self, rec: CaseRecord, collected: dict[str, Collected], feedback: str) -> list[Message]:
        bundle = union_bundles(collected)
        # Os playbooks são orientações por seção. Regras de separação entre agentes não se aplicam
        # ao agente único: ele pode usar a união de evidências em qualquer seção, sem inventar OUTs.
        system = (
            "Você é um analista generalista de crédito agro. Faça a análise completa e uma autorrevisão crítica. "
            "As orientações abaixo descrevem responsabilidades por seção, todas suas nesta execução. "
            "Referências a agentes anteriores significam as seções que você está escrevendo. "
            "Você pode usar TODAS as evidências fornecidas em qualquer seção. Não invente IDs OUT. "
            "Cálculos e premissas numéricas são do backend; não recalcule. "
            "Se faltar informação bloqueante, preencha eligibility e deixe risk, structuring e review nulos. "
            "Caso contrário, preencha as quatro seções. A decisão final continua humana.\n\n"
            + "\n\n".join(self._agents.get(a).playbook for a in collected)
            + "\n\n"
            + UNTRUSTED_RULES
        )
        user = (
            wrap_untrusted("demanda", rec.state.interpreted.model_dump())
            + "\n"
            + render_evidence(bundle)
            + "\nIDs disponíveis: "
            + ", ".join(sorted(bundle.allowed_ids()))
            + "\nSchema da resposta completa (substitui formatos individuais dos playbooks):\n"
            + render_schema(GeneralistOutput)
        )
        if feedback:
            user += "\nCorrija os problemas apontados pelo backend:\n" + wrap_untrusted("feedback", feedback)
        return [Message(role="system", content=system), Message(role="user", content=user)]

    def _validate(self, rec, raw, collected, round_):
        combined = union_bundles(collected)
        cleaned, rejected = ground(raw, combined.allowed_ids())
        if rejected:
            rec.events.emit(EventType.GROUNDING_REJECTED, {"rejected_ids": rejected}, agent_id="generalist")
        parsed = GeneralistOutput.model_validate(cleaned)
        results = {}
        for agent_id, entry in collected.items():
            section = getattr(parsed, FIELDS[agent_id])
            if section is None:
                raise OutputValidationError([f"Seção {FIELDS[agent_id]} obrigatória quando elegibilidade permite análise."])
            task = entry.task.model_copy(
                update={
                    "inputs": next(s for s in plan_for(rec.state.interpreted.intent) if s.agent_id == agent_id).project(
                        rec.state.interpreted, results
                    )
                }
            )
            validated = self._agents.get(agent_id).validate(entry.ctx, task, section, entry.bundle)
            oid = output_id(agent_id, round_)
            result = AgentResult(
                agent_id=agent_id,
                task_id=task.task_id,
                round=round_,
                output=validated.output,
                output_id=oid,
                evidence_ids=collect_ids(validated.output),
                calculation_ids=validated.calculation_ids,
                assumptions=validated.assumptions,
                warnings=validated.warnings,
                usage=LLMUsage(model=self._runtime.model),
            )
            rec.evidence.register(AgentOutputRecord(id=oid, agent_id=agent_id, round=round_, output=result.output))
            results[agent_id] = result
            if agent_id == ELIGIBILITY and result.output["status"] == "blocked":
                break
        return results

    async def _execute(self, rec: CaseRecord) -> None:
        feedback, previous, first = "", None, {}
        for round_ in (1, 2):
            rework = self._rework_instruction(previous) if previous else None
            collected = await self._collect(rec, round_, rework)
            messages = self._messages(rec, collected, feedback)
            task = TaskSpec(
                task_id=f"generalist-R{round_}", agent_id="generalist", round=round_, instruction="Análise completa"
            )
            for attempt in range(2):
                raw, _ = await self._runtime._reason("generalist", task, messages, GeneralistOutput, rec.events)
                try:
                    results = self._validate(rec, raw, collected, round_)
                    break
                except OutputValidationError as exc:
                    rec.events.emit(EventType.OUTPUT_REJECTED, {"problems": exc.problems}, agent_id="generalist")
                    if attempt == 1:
                        raise AgentExecutionError("generalist", "output_validation_failed") from exc
                    # Risk.validate consome seu baseline; reconstruir os mesmos cálculos não chama o LLM.
                    collected = await self._collect(rec, round_, rework)
                    messages += [
                        Message(role="assistant", content=json.dumps(raw, ensure_ascii=False)),
                        Message(role="user", content="Corrija e devolva o JSON completo: " + str(exc)),
                    ]
            rec.completed.update({f"{a}@R{round_}": r for a, r in results.items()})
            if self._eligibility_blocks(rec, results[ELIGIBILITY]):
                return
            if round_ == 1:
                first = dict(results)
            findings = run_validators(
                ReviewContext(
                    results,
                    rec.evidence,
                    rec.events,
                    load_policy_params(),
                    rec.state.interpreted.requested_amount,
                    rec.state.interpreted.crop,
                )
            )
            ai = AIReviewOutput.model_validate(results[REVIEW].output)
            review = merge_review(findings, ai.findings, ai.overall_assessment, rework_round=round_ - 1, previous=previous)
            if review.reexecution_required and round_ == 1:
                previous = review
                feedback = json.dumps([f.model_dump() for f in findings], ensure_ascii=False)
                rec.state.rework_rounds = 1
                continue
            if review.reexecution_required:
                review = review.model_copy(update={"reexecution_required": False, "reopen_agent": None})
            self._finish(rec, results, first, review)
            return

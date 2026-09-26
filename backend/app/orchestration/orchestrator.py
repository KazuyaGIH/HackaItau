"""Orchestrator (ARCHITECTURE.md §3, §4): máquina de estados determinística.

Bootstrap: create → interpret → resolve → SCOPE_FROZEN → planned (ou waiting_input).
Execução (`run`): Eligibility (gate) → Risk → Structuring → Review (validators + red team) → rework ≤ 1 →
consolidate → Output Guard → human_review_required. O LLM só interpreta a demanda e raciocina dentro dos agentes;
toda transição de estado, autorização e número material é código.
"""

import asyncio

from app.agents.registry import AgentRegistry
from app.agents.review.merge import merge_review
from app.agents.review.remediations import rework_for
from app.agents.review.validators import ReviewContext, run_validators
from app.agents.runtime import AgentExecutionError, AgentRuntime
from app.calculations.policy_params import load_policy_params
from app.config import Settings
from app.core.schemas.agent import AgentResult, ReworkInstruction, TaskSpec
from app.core.schemas.case import AgentCardState, AgentStatus, CaseStatus, DemoOptions, MissingInfoRequest
from app.core.schemas.context import CaseScope, ExecutionContext, UserIdentity
from app.core.schemas.events import EventType
from app.core.schemas.outputs import AIReviewOutput, EligibilityOutput, Finding, ReviewOutput
from app.core.schemas.report import HumanGateView
from app.core.store import CaseRecord, CaseStore
from app.data.repository import DataRepository, KnowledgeRetriever
from app.governance.bootstrap_resolver import BootstrapClientResolver
from app.governance.loader import load_identities
from app.governance.output_guard import OutputGuard
from app.orchestration.consolidator import consolidate
from app.orchestration.interpreter import interpret
from app.orchestration.plans import ELIGIBILITY, REVIEW, RISK, PlanStep, dependents_of, plan_for
from app.tools.deps import ToolDeps
from app.tools.gateway import Toolbox

PURPOSE = "credit_analysis_agro"
PRODUCT_FAMILY_BY_PURPOSE = {"custeio": "credito_rural_custeio"}
MAX_REWORK_ROUNDS = 1


class OrchestratorError(Exception):
    def __init__(self, code: str, detail: str, http_status: int = 409) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.http_status = http_status


class Orchestrator:
    def __init__(
        self,
        store: CaseStore,
        resolver: BootstrapClientResolver,
        settings: Settings,
        *,
        agents: AgentRegistry,
        runtime: AgentRuntime,
        repo: DataRepository,
        knowledge: KnowledgeRetriever,
        llm_mode: str,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._settings = settings
        self._agents = agents
        self._runtime = runtime
        self._repo = repo
        self._knowledge = knowledge
        self._llm_mode = llm_mode

    # ------------------------------------------------------------- bootstrap

    async def create_case(self, user_id: str, prompt: str, demo_options: DemoOptions) -> CaseRecord:
        user = self._user(user_id)
        rec = self._store.create(user_id=user.user_id, prompt=prompt, demo_options=demo_options, llm_mode=self._llm_mode)
        rec.events.emit(EventType.CASE_CREATED, {"user_id": user.user_id, "demo_options": demo_options.model_dump()})
        rec.events.emit(EventType.ORCHESTRATOR_STARTED, {"phase": "bootstrap"})
        rec.state.status = CaseStatus.interpreting
        rec.state.interpreted = await interpret(prompt, self._runtime.provider, self._runtime.model)
        self._bootstrap(rec, user, rec.state.interpreted.client_ref)
        rec.touch()
        return rec

    def provide_input(self, case_id: str, answers: dict) -> CaseRecord:
        rec = self._get(case_id)
        if rec.state.status != CaseStatus.waiting_input:
            raise OrchestratorError("not_waiting_input", f"case em '{rec.state.status.value}' não aceita input")
        rec.events.emit(EventType.INPUT_RECEIVED, {"keys": sorted(answers)})
        user = self._user(rec.state.user_id)
        if rec.state.scope is None:
            client_ref = str(answers.get("client_ref") or answers.get("client_id") or "")
            if rec.state.interpreted is not None:
                rec.state.interpreted = rec.state.interpreted.model_copy(update={"client_ref": client_ref or None})
            self._bootstrap(rec, user, client_ref)
        else:
            # scope já congelado: input só completa dados do case (UNTRUSTED, vai como task.inputs); nunca muda scope
            rec.answers.update({k: v for k, v in answers.items() if k not in ("client_ref", "client_id")})
            self._apply_demand_answers(rec, answers)
            rec.state.missing_info = None
            rec.state.status = CaseStatus.planned
        rec.touch()
        return rec

    @staticmethod
    def _apply_demand_answers(rec: CaseRecord, answers: dict) -> None:
        if rec.state.interpreted is None:
            return
        update = {}
        if isinstance(answers.get("requested_amount"), (int, float)):
            update["requested_amount"] = float(answers["requested_amount"])
        for key in ("purpose", "crop", "cycle"):
            if isinstance(answers.get(key), str) and answers[key]:
                update[key] = answers[key]
        if update:
            rec.state.interpreted = rec.state.interpreted.model_copy(update=update)

    def _bootstrap(self, rec: CaseRecord, user: UserIdentity, client_ref: str | None) -> None:
        result = self._resolver.resolve(user, client_ref, rec.events)
        if result.status == "denied":
            rec.events.emit(EventType.SECURITY_EVENT, {"kind": "BOOTSTRAP_DENIED", "reason": result.reason})
            rec.state.status = CaseStatus.failed
            rec.state.error = "user_not_authorized_to_resolve_client"
            rec.events.emit(EventType.EXECUTION_FAILED, {"error": rec.state.error})
            return
        if result.status != "ok" or result.client is None:
            reason = "client_ambiguous" if result.status == "ambiguous" else "client_unresolved"
            message = (
                f"Mais de um cliente corresponde à referência ({result.count}). Informe o ID exato (ex.: CLIENTE-001)."
                if result.status == "ambiguous"
                else "Não foi possível identificar o cliente. Informe o nome completo ou o ID (ex.: CLIENTE-001)."
            )
            rec.state.missing_info = MissingInfoRequest(reason=reason, items=["client_ref"], message=message)
            rec.events.emit(EventType.MISSING_INFO_REQUESTED, {"reason": reason, "items": ["client_ref"]})
            rec.state.status = CaseStatus.waiting_input
            return

        purpose_key = rec.state.interpreted.purpose if rec.state.interpreted else None
        scope = CaseScope(
            client_ids=(result.client.client_id,),
            purpose=PURPOSE,
            product_family=PRODUCT_FAMILY_BY_PURPOSE.get(purpose_key or ""),
        )
        rec.state.scope = scope
        rec.state.missing_info = None
        rec.events.emit(EventType.SCOPE_FROZEN, {"client_ids": list(scope.client_ids), "purpose": scope.purpose})

        intent = rec.state.interpreted.intent if rec.state.interpreted else "credito_agro"
        plan = plan_for(intent)
        rec.state.selected_agents = [s.agent_id for s in plan]
        rec.state.agents = []
        for step in plan:
            card = self._agents.card(step.agent_id)
            rec.state.agents.append(AgentCardState(agent_id=card.agent_id, name=card.name, status=AgentStatus.selected))
            rec.events.emit(
                EventType.AGENT_SELECTED, {"agent_id": card.agent_id, "version": card.version}, agent_id=card.agent_id
            )
        rec.state.status = CaseStatus.planned

    # ------------------------------------------------------------- execution

    def start_run(self, case_id: str) -> CaseRecord:
        """Valida e dispara `run` em background (asyncio.Task); o frontend acompanha por polling."""
        rec = self._runnable(case_id)
        rec.state.status = CaseStatus.running
        rec.touch()
        rec.run_task = asyncio.get_running_loop().create_task(self._run_guarded(rec))
        return rec

    async def run(self, case_id: str) -> CaseRecord:
        rec = self._runnable(case_id)
        rec.state.status = CaseStatus.running
        await self._run_guarded(rec)
        return rec

    def _runnable(self, case_id: str) -> CaseRecord:
        rec = self._get(case_id)
        if rec.state.status != CaseStatus.planned:
            raise OrchestratorError("not_runnable", f"case em '{rec.state.status.value}' não pode ser executado")
        if rec.state.scope is None or rec.state.interpreted is None:
            raise OrchestratorError("scope_missing", "case sem CaseScope congelado", 500)
        if self._runtime.provider is None:
            raise OrchestratorError("llm_not_configured", "LLM não configurado: defina LLM_API_KEY no .env", 503)
        return rec

    async def _run_guarded(self, rec: CaseRecord) -> None:
        try:
            await self._execute(rec)
        except AgentExecutionError as exc:
            self._fail(rec, f"{exc.agent_id}:{exc.reason}", exc.agent_id)
        except Exception as exc:  # noqa: BLE001 — falha inesperada vira estado auditável, nunca traceback ao usuário
            self._fail(rec, f"unexpected:{type(exc).__name__}", None)
        finally:
            rec.touch()

    def _fail(self, rec: CaseRecord, error: str, agent_id: str | None) -> None:
        rec.state.status = CaseStatus.failed
        rec.state.error = error
        if agent_id:
            self._set_agent(rec, agent_id, AgentStatus.failed)
        rec.events.emit(EventType.EXECUTION_FAILED, {"error": error}, agent_id=agent_id)

    async def _execute(self, rec: CaseRecord) -> None:
        user = self._user(rec.state.user_id)
        assert rec.state.interpreted is not None
        plan = plan_for(rec.state.interpreted.intent)
        steps = {s.agent_id: s for s in plan}
        rec.events.emit(EventType.ORCHESTRATOR_STARTED, {"phase": "execution", "plan": [s.agent_id for s in plan]})

        results: dict[str, AgentResult] = {}
        for step in plan:
            if step.agent_id == REVIEW:
                continue
            results[step.agent_id] = await self._run_agent(rec, user, step, results, round_=1)
            if step.agent_id == ELIGIBILITY and self._eligibility_blocks(rec, results[step.agent_id]):
                return
        first_round = dict(results)

        review = await self._review(rec, user, steps[REVIEW], results, round_=1, previous=None)

        if review.reexecution_required and review.reopen_agent and rec.state.rework_rounds < MAX_REWORK_ROUNDS:
            rec.state.rework_rounds += 1
            rework = self._rework_instruction(review)
            reopen = [review.reopen_agent, *dependents_of(plan, review.reopen_agent)]
            for agent_id in reopen:
                rec.events.emit(
                    EventType.TASK_REOPENED,
                    {"round": 2, "finding_ids": rework.finding_ids if rework else [], "action": review.reopen_agent},
                    agent_id=agent_id,
                )
                self._set_agent(rec, agent_id, AgentStatus.reopened)
                results[agent_id] = await self._run_agent(
                    rec, user, steps[agent_id], results, round_=2, rework=rework if agent_id == review.reopen_agent else None
                )
            review = await self._review(rec, user, steps[REVIEW], results, round_=2, previous=review)
            if review.reexecution_required:
                # limite de rework atingido: findings seguem abertos no relatório; humano decide
                review = review.model_copy(update={"reexecution_required": False, "reopen_agent": None})

        rec.state.review = review
        report = consolidate(rec.state, rec.events, rec.evidence, results, first_round, review)
        rec.events.emit(
            EventType.RESULT_CONSOLIDATED,
            {
                "findings": len(review.findings),
                "alternatives": len(report.alternatives),
                "rework_rounds": rec.state.rework_rounds,
            },
        )

        assert rec.state.scope is not None
        guard = OutputGuard(self._repo, self._settings.secret_values(), rec.state.scope)
        result = guard.apply(report, rec.evidence, next_finding_seq=len(review.findings) + 1)
        if result.applied:
            rec.events.emit(
                EventType.OUTPUT_GUARD_APPLIED,
                {"codes": [f.code for f in result.findings], "redactions": result.redactions},
            )
            merged = review.model_copy(update={"findings": review.findings + result.findings})
            rec.state.review = merged
            result.report.review.findings = merged.findings
        rec.state.report = result.report
        rec.state.status = CaseStatus.human_review_required
        rec.events.emit(EventType.HUMAN_REVIEW_REQUIRED, {"actions": ["approve_next_step", "request_adjustment"]})

    async def _run_agent(
        self,
        rec: CaseRecord,
        user: UserIdentity,
        step: PlanStep,
        results: dict[str, AgentResult],
        *,
        round_: int,
        rework: ReworkInstruction | None = None,
    ) -> AgentResult:
        assert rec.state.scope is not None and rec.state.interpreted is not None
        agent = self._agents.get(step.agent_id)
        task_id = f"task-{step.agent_id}-R{round_}"
        inputs = step.project(rec.state.interpreted, results) | {"answers": dict(rec.answers)}
        task = TaskSpec(
            task_id=task_id,
            agent_id=step.agent_id,
            round=round_,
            instruction=step.instruction,
            inputs=inputs,
            upstream_output_ids=[results[u].output_id for u in step.upstream if u in results],
            rework=rework,
        )
        ctx = ExecutionContext(
            user=user,
            case_id=rec.state.case_id,
            task_id=task_id,
            agent_id=step.agent_id,
            purpose=rec.state.scope.purpose,
            case_scope=rec.state.scope,
        )
        tags = ("adversarial",) if rec.state.demo_options.adversarial_document else ()
        deps = ToolDeps(self._repo, self._knowledge, tags, agent_id=step.agent_id, round=round_)
        toolbox = Toolbox(ctx, agent.card, deps, rec.events, rec.evidence)

        self._set_agent(rec, step.agent_id, AgentStatus.running, round_)
        try:
            result = await self._runtime.run(agent, ctx, task, toolbox, rec.events, rec.evidence)
        except AgentExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 — falha do agente vira erro auditável atribuído a ele
            raise AgentExecutionError(step.agent_id, f"{type(exc).__name__}: {str(exc)[:300]}") from exc
        self._set_agent(rec, step.agent_id, AgentStatus.completed, round_, summary=_summary(result), result=result)
        self._refresh_counters(rec, result)
        rec.touch()
        return result

    @staticmethod
    def _refresh_counters(rec: CaseRecord, result: AgentResult) -> None:
        c = rec.state.counters
        c.llm_calls += 1
        c.tool_calls += result.tool_calls
        c.tokens_in += result.usage.tokens_in
        c.tokens_out += result.usage.tokens_out
        c.sources = len(rec.evidence.sources())
        c.permission_checks = len(rec.events.of_type(EventType.PERMISSION_CHECKED))
        c.permission_denials = len(rec.events.of_type(EventType.PERMISSION_DENIED))
        c.security_events = len(rec.events.of_type(EventType.SECURITY_EVENT))

    def _eligibility_blocks(self, rec: CaseRecord, result: AgentResult) -> bool:
        out = EligibilityOutput.model_validate(result.output)
        if out.status != "blocked":
            return False
        items = [m.item for m in out.missing_items if m.blocking] or ["informacao_bloqueante"]
        rec.state.missing_info = MissingInfoRequest(
            reason="eligibility_blocked",
            items=items,
            message="Eligibility identificou informação bloqueante ausente. Risk não foi executado. " + out.summary,
        )
        rec.events.emit(
            EventType.MISSING_INFO_REQUESTED, {"reason": "eligibility_blocked", "items": items}, agent_id=ELIGIBILITY
        )
        self._set_agent(rec, ELIGIBILITY, AgentStatus.blocked, 1, summary=out.summary)
        for agent_id in (RISK, *[a for a in rec.state.selected_agents if a not in (ELIGIBILITY, RISK)]):
            self._set_agent(rec, agent_id, AgentStatus.waiting)
        rec.state.status = CaseStatus.waiting_input
        return True

    async def _review(
        self,
        rec: CaseRecord,
        user: UserIdentity,
        step: PlanStep,
        results: dict[str, AgentResult],
        *,
        round_: int,
        previous: ReviewOutput | None,
    ) -> ReviewOutput:
        assert rec.state.interpreted is not None
        rec.events.emit(EventType.REVIEW_STARTED, {"round": round_}, agent_id=REVIEW)
        ctx = ReviewContext(
            results=results,
            evidence=rec.evidence,
            events=rec.events,
            policy=load_policy_params(),
            requested_amount=rec.state.interpreted.requested_amount,
        )
        validator_findings = _tag_round(run_validators(ctx), round_)

        ai_result = await self._run_agent(rec, user, step, results, round_=round_)
        results[REVIEW] = ai_result
        ai_out = AIReviewOutput.model_validate(ai_result.output)
        ai_findings = _tag_round(ai_out.findings, round_)

        for f in validator_findings + ai_findings:
            rec.events.emit(
                EventType.REVIEW_ISSUE_FOUND,
                {"finding_id": f.id, "code": f.code, "severity": f.severity, "origin": f.origin, "owner": f.owner_agent},
                agent_id=REVIEW,
            )
        review = merge_review(
            validator_findings, ai_findings, ai_out.overall_assessment, rework_round=round_ - 1, previous=previous
        )
        rec.state.review = review
        rec.events.emit(
            EventType.REVIEW_COMPLETED,
            {
                "round": round_,
                "review_status": review.review_status,
                "findings": len(review.findings),
                "reexecution_required": review.reexecution_required,
                "reopen_agent": review.reopen_agent,
            },
            agent_id=REVIEW,
        )
        rec.touch()
        return review

    @staticmethod
    def _rework_instruction(review: ReviewOutput) -> ReworkInstruction | None:
        rw = rework_for([f for f in review.findings if f.owner_agent == review.reopen_agent])
        return rw[1] if rw else None

    # ------------------------------------------------------------- human gate

    def human_review(self, case_id: str, decision: str, comment: str) -> CaseRecord:
        rec = self._get(case_id)
        if rec.state.status != CaseStatus.human_review_required:
            raise OrchestratorError("not_in_human_review", f"case em '{rec.state.status.value}' não está em revisão humana")
        report = rec.state.report
        if decision == "approve_next_step":
            rec.events.emit(EventType.HUMAN_APPROVED, {"comment_len": len(comment)})
            rec.events.emit(EventType.CASE_COMPLETED, {"note": "aprovação para próxima etapa; NÃO é aprovação de crédito"})
            rec.state.status = CaseStatus.completed_demo
            if report:
                report.human_gate = HumanGateView(
                    status="approved_next_step",
                    available_actions=[],
                    comments=report.human_gate.comments + ([comment] if comment else []),
                )
        elif decision == "request_adjustment":
            rec.events.emit(EventType.HUMAN_ADJUSTMENT_REQUESTED, {"comment_len": len(comment)})
            if report:
                report.human_gate = HumanGateView(
                    status="adjustment_requested",
                    available_actions=["approve_next_step", "request_adjustment"],
                    comments=report.human_gate.comments + ([comment] if comment else []),
                )
        else:
            raise OrchestratorError("invalid_decision", "decision deve ser approve_next_step | request_adjustment", 422)
        rec.touch()
        return rec

    # ------------------------------------------------------------- helpers

    def get(self, case_id: str) -> CaseRecord:
        return self._get(case_id)

    def _get(self, case_id: str) -> CaseRecord:
        rec = self._store.get(case_id)
        if rec is None:
            raise OrchestratorError("case_not_found", "case não encontrado", 404)
        return rec

    @staticmethod
    def _set_agent(
        rec: CaseRecord,
        agent_id: str,
        status: AgentStatus,
        round_: int | None = None,
        summary: str | None = None,
        result: AgentResult | None = None,
    ) -> None:
        for a in rec.state.agents:
            if a.agent_id == agent_id:
                a.status = status
                if round_ is not None:
                    a.round = round_
                if summary is not None:
                    a.summary = summary
                if result is not None:
                    a.data_domains_accessed = list(result.data_domains_accessed)
                    a.tool_calls = result.tool_calls
                    a.source_count = len(result.evidence_ids)
                    a.denied_calls = len(
                        [e for e in rec.events.of_type(EventType.PERMISSION_DENIED) if e.agent_id == agent_id]
                    )
                    a.output = result.output
                return

    @staticmethod
    def _user(user_id: str) -> UserIdentity:
        user = load_identities().get(user_id)
        if user is None:
            raise OrchestratorError("unknown_user", "usuário não encontrado em identities.json", 403)
        return user


def _tag_round(findings: list[Finding], round_: int) -> list[Finding]:
    if round_ == 1:
        return findings
    return [f.model_copy(update={"id": f"{f.id}-R{round_}"}) for f in findings]


def _summary(result: AgentResult) -> str:
    out = result.output
    for key in ("summary", "risk_narrative", "comparison_notes", "overall_assessment"):
        value = out.get(key)
        if isinstance(value, str) and value:
            return value[:200]
    return ""

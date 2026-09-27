"""Orchestrator (ARCHITECTURE.md §3, §4): máquina de estados determinística.

Bootstrap: create → interpret → resolve → SCOPE_FROZEN → planned (ou waiting_input).
Execução (`run`): Eligibility (gate) → Risk → Structuring → Review (validators + red team) → rework ≤ 1 →
consolidate → Output Guard → human_review_required. O LLM só interpreta a demanda e raciocina dentro dos agentes;
toda transição de estado, autorização e número material é código.
Ajuste humano: o analista reabre um agente com um comentário → ele e seus dependentes rodam numa nova rodada →
Review → consolidate → human gate de novo. Retry: um case `failed` retoma do ponto em que parou (checkpoints).
"""

import asyncio
from datetime import datetime, timezone

from app.agents.registry import AgentRegistry
from app.agents.review.merge import merge_review
from app.agents.review.remediations import rework_for
from app.agents.review.validators import ReviewContext, run_validators
from app.agents.runtime import AgentExecutionError, AgentRuntime
from app.calculations.policy_params import load_policy_params
from app.config import Settings
from app.core.schemas.agent import CARRY_OVER_ACTION, HUMAN_ADJUSTMENT_ACTION, AgentResult, ReworkInstruction, TaskSpec
from app.core.schemas.case import (
    AgentCardState,
    AgentStatus,
    AttachmentView,
    CaseStatus,
    DemoOptions,
    MissingInfoRequest,
)
from app.core.schemas.context import CaseScope, ExecutionContext, UserIdentity
from app.core.schemas.events import EventType
from app.core.schemas.outputs import AIReviewOutput, EligibilityOutput, Finding, ReviewOutput
from app.core.schemas.report import HumanGateView
from app.core.store import CaseRecord, CaseStore, RunJob
from app.data.repository import DataRepository, KnowledgeRetriever
from app.documents.attachments import MAX_PER_CASE, AttachmentError, extract_text, infer_type
from app.governance.bootstrap_resolver import BootstrapClientResolver
from app.governance.injection_guard import scan_record
from app.governance.loader import load_identities
from app.governance.output_guard import OutputGuard
from app.orchestration.clarify import answers_from_text, context_from, describe_context, open_questions
from app.orchestration.consolidator import consolidate
from app.orchestration.interpreter import heuristic_interpret, interpret, parse_amount
from app.orchestration.plans import ELIGIBILITY, REVIEW, RISK, PlanStep, dependents_of, plan_for
from app.tools.deps import ToolDeps
from app.tools.gateway import Toolbox

PURPOSE = "credit_analysis_agro"
PRODUCT_FAMILY_BY_PURPOSE = {"custeio": "credito_rural_custeio"}
MAX_REWORK_ROUNDS = 1
MAX_HUMAN_ADJUSTMENTS = 3


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
        rec.state.open_questions = open_questions(rec.state.interpreted)
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
            rec.state.missing_info = None
            rec.state.status = CaseStatus.planned
        self._apply_answers(rec, answers)
        rec.touch()
        return rec

    def provide_text(self, case_id: str, text: str) -> CaseRecord:
        """Resposta do analista em texto livre (chat). Pedido de informação pendente → answers do que foi pedido;
        case planejado → contexto extra para a squad (prazo, garantias, observações). Nunca muda escopo."""
        rec = self._get(case_id)
        text = text.strip()
        if not text:
            raise OrchestratorError("empty_text", "mensagem vazia", 422)
        if rec.state.status == CaseStatus.waiting_input and rec.state.missing_info is not None:
            return self.provide_input(case_id, answers_from_text(text, rec.state.missing_info.items))
        if rec.state.status != CaseStatus.planned:
            raise OrchestratorError("not_accepting_text", f"case em '{rec.state.status.value}' não recebe contexto agora")
        h = heuristic_interpret(text)
        it = rec.state.interpreted
        answers: dict = context_from(h)
        # se o valor ainda não era conhecido, um número solto na resposta é o valor
        if (amount := parse_amount(text, bare_number_ok=it is not None and it.requested_amount is None)) is not None:
            answers["requested_amount"] = amount
        answers |= {k: v for k in ("purpose", "crop", "cycle") if (v := getattr(h, k))}
        previous = str(rec.answers.get("observacoes_do_analista") or "")
        answers["observacoes_do_analista"] = f"{previous}\n{text}".strip()
        rec.events.emit(EventType.INPUT_RECEIVED, {"keys": sorted(answers), "source": "text"})
        self._apply_answers(rec, answers)
        rec.touch()
        return rec

    def _apply_answers(self, rec: CaseRecord, answers: dict) -> None:
        """Respostas completam a leitura da demanda e viram contexto (answers → task.inputs, UNTRUSTED)."""
        rec.answers.update({k: v for k, v in answers.items() if k not in ("client_ref", "client_id")})
        self._apply_demand_answers(rec, answers)
        it = rec.state.interpreted
        if it is not None:
            update: dict = {}
            if isinstance(answers.get("prazo_desejado_meses"), int):
                update["tenor_months"] = answers["prazo_desejado_meses"]
            if isinstance(answers.get("garantias_oferecidas"), str):
                update["guarantees"] = sorted(set(it.guarantees) | set(answers["garantias_oferecidas"].split(", ")))
            for key, field in (("regiao", "region"), ("area_hectares", "area_hectares")):
                if answers.get(key):
                    update[field] = answers[key]
            if answers.get("tipo_de_operacao"):
                update["request_kind"] = answers["tipo_de_operacao"]
            if update:
                rec.state.interpreted = it.model_copy(update=update)
        rec.state.analyst_context = describe_context(rec.answers)
        rec.state.open_questions = open_questions(rec.state.interpreted)

    # ------------------------------------------------------------- attachments

    def attach_document(self, case_id: str, user_id: str, filename: str, data: bytes) -> CaseRecord:
        """Documento anexado na conversa: vira documento do case (UNTRUSTED), lido pelos agentes via Gateway."""
        rec = self._get(case_id)
        if rec.state.user_id != user_id:
            raise OrchestratorError("forbidden", "só quem abriu o case pode anexar documentos", 403)
        if rec.state.status in (CaseStatus.running, CaseStatus.interpreting, CaseStatus.completed_demo):
            raise OrchestratorError("not_accepting_documents", f"case em '{rec.state.status.value}' não recebe anexos agora")
        if len(rec.attachments) >= MAX_PER_CASE:
            raise OrchestratorError("attachment_limit", f"limite de {MAX_PER_CASE} anexos por case", 422)
        try:
            text, truncated = extract_text(filename, data)
        except AttachmentError as exc:
            raise OrchestratorError("invalid_attachment", str(exc), 422) from exc

        doc_id = f"ANX-{len(rec.attachments) + 1:03d}"
        now = datetime.now(timezone.utc)
        record = {
            "doc_id": doc_id,
            "type": infer_type(filename, text),
            "title": f"Anexo do analista: {filename}",
            "issued_at": now.date().isoformat(),
            "extracted": {},
            "content": text,
        }
        flagged = bool(rec.state.scope and scan_record(record, rec.state.scope).flagged)
        rec.attachments.append(record)
        rec.state.attachments.append(
            AttachmentView(
                doc_id=doc_id,
                filename=filename,
                doc_type=record["type"],
                size_bytes=len(data),
                chars=len(text),
                truncated=truncated,
                flagged=flagged,
                uploaded_at=now,
            )
        )
        rec.events.emit(
            EventType.DOCUMENT_ATTACHED,
            {"doc_id": doc_id, "doc_type": record["type"], "chars": len(text), "truncated": truncated, "flagged": flagged},
        )
        # a Elegibilidade tinha bloqueado por este tipo de documento: o anexo cumpre o pedido
        info = rec.state.missing_info
        if rec.state.status == CaseStatus.waiting_input and info is not None and info.reason == "eligibility_blocked":
            remaining = [i for i in info.items if i != record["type"]]
            if len(remaining) < len(info.items):
                if remaining:
                    rec.state.missing_info = info.model_copy(update={"items": remaining})
                else:
                    rec.events.emit(EventType.INPUT_RECEIVED, {"keys": [record["type"]], "source": "attachment"})
                    rec.state.missing_info = None
                    rec.state.status = CaseStatus.planned
        rec.touch()
        return rec

    @staticmethod
    def _apply_demand_answers(rec: CaseRecord, answers: dict) -> None:
        if rec.state.interpreted is None:
            return
        update = {}
        amount = answers.get("requested_amount")
        if isinstance(amount, (int, float)):
            update["requested_amount"] = float(amount)
        elif isinstance(amount, str) and (parsed := parse_amount(amount, bare_number_ok=True)) is not None:
            update["requested_amount"] = parsed
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
        self._begin_execution(rec)
        rec.run_task = asyncio.get_running_loop().create_task(self._run_guarded(rec))
        return rec

    async def run(self, case_id: str) -> CaseRecord:
        rec = self._runnable(case_id)
        self._begin_execution(rec)
        await self._run_guarded(rec)
        return rec

    def _begin_execution(self, rec: CaseRecord) -> None:
        """Execução nova (inclusive depois de um input): descarta checkpoints de tentativas anteriores."""
        assert rec.state.interpreted is not None
        rec.job = RunJob(kind="execution")
        rec.completed.clear()
        rec.reviews.clear()
        rec.results.clear()
        rec.first_round.clear()
        rec.sticky_params.clear()
        rec.state.rework_rounds = 0
        rec.state.status = CaseStatus.running
        plan = plan_for(rec.state.interpreted.intent)
        rec.events.emit(EventType.ORCHESTRATOR_STARTED, {"phase": "execution", "plan": [s.agent_id for s in plan]})
        rec.touch()

    def start_retry(self, case_id: str) -> CaseRecord:
        """Retoma em background uma execução que falhou, a partir do agente em que parou."""
        rec = self._retryable(case_id)
        rec.run_task = asyncio.get_running_loop().create_task(self._run_guarded(rec))
        return rec

    async def retry(self, case_id: str) -> CaseRecord:
        rec = self._retryable(case_id)
        await self._run_guarded(rec)
        return rec

    def _retryable(self, case_id: str) -> CaseRecord:
        rec = self._get(case_id)
        # sem job = falhou antes de executar (ex.: bootstrap negado): não há o que retomar
        if rec.state.status != CaseStatus.failed or rec.job is None:
            raise OrchestratorError("not_retryable", f"case em '{rec.state.status.value}' não pode ser retomado")
        if self._runtime.provider is None:
            raise OrchestratorError("llm_not_configured", "LLM não configurado: defina LLM_API_KEY no .env", 503)
        failed_agent = next((a.agent_id for a in rec.state.agents if a.status == AgentStatus.failed), None)
        rec.events.emit(
            EventType.ORCHESTRATOR_STARTED,
            {"phase": "retry", "job": rec.job.kind, "round": rec.job.round, "failed_agent": failed_agent},
        )
        rec.state.status = CaseStatus.running
        rec.state.error = None
        rec.touch()
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
            if rec.job is not None and rec.job.kind == "human_adjustment":
                await self._execute_adjustment(rec, rec.job)
            else:
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

        results: dict[str, AgentResult] = {}
        for step in plan:
            if step.agent_id == REVIEW:
                continue
            results[step.agent_id] = await self._run_step(rec, user, step, results, round_=1)
            if step.agent_id == ELIGIBILITY and self._eligibility_blocks(rec, results[step.agent_id]):
                return
        first_round = dict(results)
        rec.first_round = dict(first_round)

        review = await self._review(rec, user, steps[REVIEW], results, round_=1, previous=None)

        # só existe uma rodada automática (a 2); a condição não depende de contador para que um retry a retome
        if review.reexecution_required and review.reopen_agent and MAX_REWORK_ROUNDS > 0:
            rec.state.rework_rounds = 1
            rework = self._rework_instruction(review)
            reopen = [review.reopen_agent, *dependents_of(plan, review.reopen_agent)]
            for agent_id in reopen:
                finding_ids = rework.finding_ids if rework else []
                self._reopen(rec, agent_id, round_=2, finding_ids=finding_ids, action=review.reopen_agent)
                results[agent_id] = await self._run_step(
                    rec, user, steps[agent_id], results, round_=2, rework=rework if agent_id == review.reopen_agent else None
                )
            review = await self._review(rec, user, steps[REVIEW], results, round_=2, previous=review)
            if review.reexecution_required:
                # limite de rework atingido: findings seguem abertos no relatório; humano decide
                review = review.model_copy(update={"reexecution_required": False, "reopen_agent": None})

        self._finish(rec, results, first_round, review)

    async def _execute_adjustment(self, rec: CaseRecord, job: RunJob) -> None:
        """Ajuste pedido no human gate: reabre o agente escolhido e seus dependentes numa nova rodada."""
        user = self._user(rec.state.user_id)
        assert rec.state.interpreted is not None and job.target_agent is not None
        plan = plan_for(rec.state.interpreted.intent)
        steps = {s.agent_id: s for s in plan}

        results = dict(rec.results)
        for agent_id in [job.target_agent, *dependents_of(plan, job.target_agent)]:
            self._reopen(rec, agent_id, round_=job.round, finding_ids=[], action=job.target_agent, source="human")
            results[agent_id] = await self._run_step(
                rec, user, steps[agent_id], results, round_=job.round, rework=self._adjustment_rework(rec, job, agent_id)
            )
            if agent_id == ELIGIBILITY and self._eligibility_blocks(rec, results[agent_id]):
                return

        review = await self._review(rec, user, steps[REVIEW], results, round_=job.round, previous=rec.state.review)
        if review.reexecution_required:
            # sem rework automático depois de um ajuste humano: o finding fica aberto e o humano decide
            review = review.model_copy(update={"reexecution_required": False, "reopen_agent": None})
        self._finish(rec, results, rec.first_round or results, review)

    @staticmethod
    def _adjustment_rework(rec: CaseRecord, job: RunJob, agent_id: str) -> ReworkInstruction | None:
        # params de reworks anteriores continuam valendo (ex.: baseline histórico no Risk), senão o erro corrigido voltaria
        params = dict(rec.sticky_params.get(agent_id, {}))
        if agent_id == job.target_agent:
            return ReworkInstruction(
                finding_ids=[], required_action=HUMAN_ADJUSTMENT_ACTION, params=params, message=job.comment
            )
        if params:
            return ReworkInstruction(finding_ids=[], required_action=CARRY_OVER_ACTION, params=params, message="")
        return None

    def _reopen(
        self, rec: CaseRecord, agent_id: str, *, round_: int, finding_ids: list[str], action: str, source: str = "review"
    ) -> None:
        already = any(
            e.agent_id == agent_id and e.payload.get("round") == round_ for e in rec.events.of_type(EventType.TASK_REOPENED)
        )
        if already:  # retomada: essa reabertura já foi registrada na tentativa anterior
            return
        payload: dict = {"round": round_, "finding_ids": finding_ids, "action": action}
        if source != "review":
            payload["source"] = source
        rec.events.emit(EventType.TASK_REOPENED, payload, agent_id=agent_id)
        self._set_agent(rec, agent_id, AgentStatus.reopened)

    def _finish(
        self,
        rec: CaseRecord,
        results: dict[str, AgentResult],
        first_round: dict[str, AgentResult],
        review: ReviewOutput,
    ) -> None:
        previous_comments = rec.state.report.human_gate.comments if rec.state.report else []
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
        result.report.human_gate.comments = list(previous_comments)
        rec.state.report = result.report
        rec.results = dict(results)
        rec.state.status = CaseStatus.human_review_required
        rec.events.emit(EventType.HUMAN_REVIEW_REQUIRED, {"actions": ["approve_next_step", "request_adjustment"]})

    async def _run_step(
        self,
        rec: CaseRecord,
        user: UserIdentity,
        step: PlanStep,
        results: dict[str, AgentResult],
        *,
        round_: int,
        rework: ReworkInstruction | None = None,
    ) -> AgentResult:
        """Roda o agente — ou devolve o checkpoint, se essa rodada já concluiu numa tentativa anterior (retry)."""
        key = f"{step.agent_id}@R{round_}"
        if key in rec.completed:
            return rec.completed[key]
        if rework is not None and rework.params:
            rec.sticky_params.setdefault(step.agent_id, {}).update(rework.params)
        result = await self._run_agent(rec, user, step, results, round_=round_, rework=rework)
        rec.completed[key] = result
        return result

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
        deps = ToolDeps(
            self._repo, self._knowledge, tags, agent_id=step.agent_id, round=round_, attachments=tuple(rec.attachments)
        )
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
        blocking = [m for m in out.missing_items if m.blocking]
        items = [m.item for m in blocking] or ["informacao_bloqueante"]
        details = " ".join(f"{m.item}: {m.message}" for m in blocking if m.message) or out.summary
        rec.state.missing_info = MissingInfoRequest(
            reason="eligibility_blocked",
            items=items,
            message="Eligibility identificou informação bloqueante. Risk não foi executado. " + details,
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
        cached = rec.reviews.get(round_)
        if cached is not None:  # retomada: essa revisão já concluiu
            results[REVIEW] = rec.completed[f"{REVIEW}@R{round_}"]
            return cached
        rec.events.emit(EventType.REVIEW_STARTED, {"round": round_}, agent_id=REVIEW)
        ctx = ReviewContext(
            results=results,
            evidence=rec.evidence,
            events=rec.events,
            policy=load_policy_params(),
            requested_amount=rec.state.interpreted.requested_amount,
            requested_crop=rec.state.interpreted.crop,
        )
        validator_findings = _tag_round(run_validators(ctx), round_)

        ai_result = await self._run_step(rec, user, step, results, round_=round_)
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
        rec.reviews[round_] = review
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

    def human_review(self, case_id: str, decision: str, comment: str, target_agent: str | None = None) -> CaseRecord:
        """Decisão humana. `request_adjustment` com `target_agent` reexecuta a squad em background;
        sem `target_agent`, só registra o comentário."""
        rec = self._in_human_review(case_id)
        if decision == "request_adjustment" and target_agent:
            job = self._adjustment_job(rec, comment, target_agent)
            self._record_adjustment(rec, comment, target_agent)
            self._begin_adjustment(rec, job)
            rec.run_task = asyncio.get_running_loop().create_task(self._run_guarded(rec))
            return rec
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
            self._record_adjustment(rec, comment, None)
        else:
            raise OrchestratorError("invalid_decision", "decision deve ser approve_next_step | request_adjustment", 422)
        rec.touch()
        return rec

    async def adjust(self, case_id: str, comment: str, target_agent: str) -> CaseRecord:
        """Variante aguardada do ajuste humano (testes e scripts)."""
        rec = self._in_human_review(case_id)
        job = self._adjustment_job(rec, comment, target_agent)
        self._record_adjustment(rec, comment, target_agent)
        self._begin_adjustment(rec, job)
        await self._run_guarded(rec)
        return rec

    def _in_human_review(self, case_id: str) -> CaseRecord:
        rec = self._get(case_id)
        if rec.state.status != CaseStatus.human_review_required:
            raise OrchestratorError("not_in_human_review", f"case em '{rec.state.status.value}' não está em revisão humana")
        return rec

    def _adjustment_job(self, rec: CaseRecord, comment: str, target_agent: str) -> RunJob:
        assert rec.state.interpreted is not None
        adjustable = [s.agent_id for s in plan_for(rec.state.interpreted.intent) if s.agent_id != REVIEW]
        if target_agent not in adjustable:
            raise OrchestratorError("invalid_target_agent", f"target_agent deve ser um de: {', '.join(adjustable)}", 422)
        if not comment.strip():
            raise OrchestratorError("comment_required", "descreva o ajuste que a squad deve fazer", 422)
        if rec.human_adjustments >= MAX_HUMAN_ADJUSTMENTS:
            raise OrchestratorError("adjustment_limit", f"limite de {MAX_HUMAN_ADJUSTMENTS} ajustes por case atingido")
        if self._runtime.provider is None:
            raise OrchestratorError("llm_not_configured", "LLM não configurado: defina LLM_API_KEY no .env", 503)
        next_round = max((r.round for r in rec.completed.values()), default=1) + 1
        return RunJob(kind="human_adjustment", round=next_round, target_agent=target_agent, comment=comment)

    @staticmethod
    def _record_adjustment(rec: CaseRecord, comment: str, target_agent: str | None) -> None:
        payload: dict = {"comment_len": len(comment)}
        if target_agent:
            payload["target_agent"] = target_agent
        rec.events.emit(EventType.HUMAN_ADJUSTMENT_REQUESTED, payload)
        report = rec.state.report
        if report:
            report.human_gate = HumanGateView(
                status="adjustment_requested",
                available_actions=["approve_next_step", "request_adjustment"],
                comments=report.human_gate.comments + ([comment] if comment else []),
            )

    def _begin_adjustment(self, rec: CaseRecord, job: RunJob) -> None:
        assert rec.state.interpreted is not None and job.target_agent is not None
        plan = plan_for(rec.state.interpreted.intent)
        rec.job = job
        rec.human_adjustments += 1
        rec.state.status = CaseStatus.running
        rec.events.emit(
            EventType.ORCHESTRATOR_STARTED,
            {
                "phase": "human_adjustment",
                "round": job.round,
                "target_agent": job.target_agent,
                "plan": [job.target_agent, *dependents_of(plan, job.target_agent), REVIEW],
            },
        )
        rec.touch()

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

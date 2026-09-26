"""Orchestrator (ARCHITECTURE.md §3, §4): máquina de estados determinística.

S1 entrega a fase de bootstrap: create → interpret → resolve → SCOPE_FROZEN → planned (ou waiting_input).
`run` (execução dos agentes, review, consolidação) e o human gate completo chegam em S3.
"""

from app.core.schemas.case import CaseStatus, DemoOptions, MissingInfoRequest
from app.core.schemas.context import CaseScope, UserIdentity
from app.core.schemas.events import EventType
from app.core.store import CaseRecord, CaseStore
from app.governance.bootstrap_resolver import BootstrapClientResolver
from app.governance.loader import load_agent_cards, load_identities
from app.orchestration.interpreter import heuristic_interpret

PURPOSE = "credit_analysis_agro"
PRODUCT_FAMILY_BY_PURPOSE = {"custeio": "credito_rural_custeio"}
# ordem fixa do P0; S3 troca por PlanTemplate[intent] + lookup por capability
P0_PLAN = ("agro_eligibility", "agro_credit_risk", "agro_structuring", "credit_review")


class OrchestratorError(Exception):
    def __init__(self, code: str, detail: str, http_status: int = 409) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.http_status = http_status


class Orchestrator:
    def __init__(self, store: CaseStore, resolver: BootstrapClientResolver, llm_mode: str) -> None:
        self._store = store
        self._resolver = resolver
        self._llm_mode = llm_mode

    # ------------------------------------------------------------- bootstrap

    def create_case(self, user_id: str, prompt: str, demo_options: DemoOptions) -> CaseRecord:
        user = self._user(user_id)
        rec = self._store.create(user_id=user.user_id, prompt=prompt, demo_options=demo_options, llm_mode=self._llm_mode)
        rec.events.emit(EventType.CASE_CREATED, {"user_id": user.user_id, "demo_options": demo_options.model_dump()})
        rec.events.emit(EventType.ORCHESTRATOR_STARTED, {})
        rec.state.status = CaseStatus.interpreting
        rec.state.interpreted = heuristic_interpret(prompt)
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
            # scope já congelado: input só pode completar dados do case (ex.: eligibility_blocked, S3); nunca muda scope
            rec.state.missing_info = None
            rec.state.status = CaseStatus.planned
        rec.touch()
        return rec

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

        cards = load_agent_cards()
        rec.state.selected_agents = [a for a in P0_PLAN if a in cards]
        for agent_id in rec.state.selected_agents:
            rec.events.emit(
                EventType.AGENT_SELECTED, {"agent_id": agent_id, "version": cards[agent_id].version}, agent_id=agent_id
            )
        rec.state.status = CaseStatus.planned

    # ------------------------------------------------------------- execution (S3)

    async def run(self, case_id: str) -> CaseRecord:
        rec = self._get(case_id)
        if rec.state.status != CaseStatus.planned:
            raise OrchestratorError("not_runnable", f"case em '{rec.state.status.value}' não pode ser executado")
        raise OrchestratorError("not_implemented", "execução dos agentes chega em S2/S3", http_status=501)

    def human_review(self, case_id: str, decision: str, comment: str) -> CaseRecord:
        rec = self._get(case_id)
        if rec.state.status != CaseStatus.human_review_required:
            raise OrchestratorError("not_in_human_review", f"case em '{rec.state.status.value}' não está em revisão humana")
        if decision == "approve_next_step":
            rec.events.emit(EventType.HUMAN_APPROVED, {"comment_len": len(comment)})
            rec.events.emit(EventType.CASE_COMPLETED, {"note": "aprovação para próxima etapa; NÃO é aprovação de crédito"})
            rec.state.status = CaseStatus.completed_demo
        elif decision == "request_adjustment":
            rec.events.emit(EventType.HUMAN_ADJUSTMENT_REQUESTED, {"comment_len": len(comment)})
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
    def _user(user_id: str) -> UserIdentity:
        user = load_identities().get(user_id)
        if user is None:
            raise OrchestratorError("unknown_user", "usuário não encontrado em identities.json", 403)
        return user

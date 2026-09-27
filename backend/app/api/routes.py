"""Endpoints P0 (ARCHITECTURE.md §19.9). /api/agents é P1."""

import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.container import Container, get_container, llm_mode
from app.core.schemas.case import (
    AttachmentRequest,
    CaseState,
    CreateCaseRequest,
    HumanReviewRequest,
    InputRequest,
    ReplyRequest,
)
from app.core.schemas.events import Event
from app.core.schemas.evidence import AgentOutputRecord, CalculationRecord, SourceRecord
from app.core.schemas.report import Report
from app.evaluation.results import latest_summary
from app.governance.loader import load_identities
from app.orchestration.assist import AssistReply, AssistRequest, assist
from app.orchestration.metrics import compute_metrics
from app.orchestration.orchestrator import OrchestratorError

router = APIRouter()
Deps = Annotated[Container, Depends(get_container)]


def _handle(exc: OrchestratorError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": exc.detail})


@router.get("/health")
def health(c: Deps) -> dict:
    return {"ok": True, "llm_mode": llm_mode(c.settings), "demo_mode": c.settings.demo_mode}


@router.get("/identities")
def identities() -> list[dict]:
    """Usuários fictícios da demo, para a tela de login. P1: IAM real (ARCHITECTURE.md §22)."""
    return [u.model_dump() for u in load_identities().values()]


@router.post("/assist", response_model=AssistReply)
def assist_message(body: AssistRequest, c: Deps) -> AssistReply:
    """Lê a mensagem do analista: demanda (abrir case), dúvida de política, pergunta sobre o case, ajuste…"""
    user = load_identities().get(body.user_id)
    if user is None:
        raise HTTPException(status_code=403, detail={"code": "unknown_user", "message": "usuário não encontrado"})
    state = None
    if body.case_id:
        try:
            state = c.orchestrator.get(body.case_id).state
        except OrchestratorError as exc:
            raise _handle(exc) from exc
        if state.user_id != user.user_id:
            raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "case de outro usuário"})
    return assist(body.text, user, state, c.knowledge)


@router.get("/metrics")
def metrics(c: Deps) -> dict:
    """Desempenho dos agentes desde que o servidor subiu (estado em memória)."""
    return compute_metrics(c.store, c.agents)


@router.get("/benchmarks/latest")
def benchmark_latest(c: Deps) -> dict:
    """Resumo do comparativo executado pelo CLI, independente dos cases em memória."""
    return {"benchmark": latest_summary(c.settings.benchmark_results_dir)}


@router.post("/cases", response_model=CaseState, status_code=201)
async def create_case(body: CreateCaseRequest, c: Deps) -> CaseState:
    try:
        return (await c.orchestrator.create_case(body.user_id, body.prompt, body.demo_options)).state
    except OrchestratorError as exc:
        raise _handle(exc) from exc


@router.get("/cases/{case_id}", response_model=CaseState)
def get_case(case_id: str, c: Deps) -> CaseState:
    try:
        return c.orchestrator.get(case_id).state
    except OrchestratorError as exc:
        raise _handle(exc) from exc


@router.get("/cases/{case_id}/events", response_model=list[Event])
def list_events(case_id: str, c: Deps, after: Annotated[int, Query(ge=0)] = 0) -> list[Event]:
    try:
        return c.orchestrator.get(case_id).events.list_after(after)
    except OrchestratorError as exc:
        raise _handle(exc) from exc


@router.post("/cases/{case_id}/input", response_model=CaseState)
def provide_input(case_id: str, body: InputRequest, c: Deps) -> CaseState:
    try:
        return c.orchestrator.provide_input(case_id, body.answers).state
    except OrchestratorError as exc:
        raise _handle(exc) from exc


@router.post("/cases/{case_id}/reply", response_model=CaseState)
def reply(case_id: str, body: ReplyRequest, c: Deps) -> CaseState:
    """Resposta em texto livre: completa um pedido de informação ou acrescenta contexto antes de rodar a squad."""
    try:
        return c.orchestrator.provide_text(case_id, body.text).state
    except OrchestratorError as exc:
        raise _handle(exc) from exc


@router.post("/cases/{case_id}/attachments", response_model=CaseState, status_code=201)
def attach(case_id: str, body: AttachmentRequest, c: Deps) -> CaseState:
    """Documento anexado na conversa (base64). Vira documento do case, lido pelos agentes via Gateway."""
    try:
        data = base64.b64decode(body.data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_base64", "message": "arquivo inválido"}) from exc
    try:
        return c.orchestrator.attach_document(case_id, body.user_id, body.filename, data).state
    except OrchestratorError as exc:
        raise _handle(exc) from exc


@router.post("/cases/{case_id}/run", response_model=CaseState, status_code=202)
async def run_case(case_id: str, c: Deps) -> CaseState:
    """Dispara a execução em background; acompanhe por GET /cases/{id} e /events."""
    try:
        return c.orchestrator.start_run(case_id).state
    except OrchestratorError as exc:
        raise _handle(exc) from exc


@router.post("/cases/{case_id}/retry", response_model=CaseState, status_code=202)
async def retry_case(case_id: str, c: Deps) -> CaseState:
    """Retoma um case `failed` a partir do agente que falhou (os que já concluíram não rodam de novo)."""
    try:
        return c.orchestrator.start_retry(case_id).state
    except OrchestratorError as exc:
        raise _handle(exc) from exc


@router.get("/cases/{case_id}/report", response_model=Report)
def get_report(case_id: str, c: Deps) -> Report:
    try:
        report = c.orchestrator.get(case_id).state.report
    except OrchestratorError as exc:
        raise _handle(exc) from exc
    if report is None:
        raise HTTPException(
            status_code=409, detail={"code": "report_not_ready", "message": "relatório ainda não consolidado"}
        )
    return report


@router.get("/cases/{case_id}/evidence/{evidence_id}", response_model=SourceRecord | CalculationRecord | AgentOutputRecord)
def get_evidence(case_id: str, evidence_id: str, c: Deps) -> SourceRecord | CalculationRecord | AgentOutputRecord:
    """Payload por trás de um source/calculation/output ID citado no relatório (já filtrado pelo Gateway)."""
    try:
        item = c.orchestrator.get(case_id).evidence.get(evidence_id)
    except OrchestratorError as exc:
        raise _handle(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "evidence_not_found", "message": evidence_id})
    return item


@router.post("/cases/{case_id}/human-review", response_model=CaseState)
async def human_review(case_id: str, body: HumanReviewRequest, c: Deps) -> CaseState:
    """async: um ajuste com target_agent dispara a reexecução em background no event loop."""
    try:
        return c.orchestrator.human_review(case_id, body.decision, body.comment, body.target_agent).state
    except OrchestratorError as exc:
        raise _handle(exc) from exc

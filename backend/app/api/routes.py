"""Endpoints P0 (ARCHITECTURE.md §19.9). /api/agents é P1."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.container import Container, get_container, llm_mode
from app.core.schemas.case import CaseState, CreateCaseRequest, HumanReviewRequest, InputRequest
from app.core.schemas.events import Event
from app.core.schemas.evidence import AgentOutputRecord, CalculationRecord, SourceRecord
from app.core.schemas.report import Report
from app.orchestration.orchestrator import OrchestratorError

router = APIRouter()
Deps = Annotated[Container, Depends(get_container)]


def _handle(exc: OrchestratorError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": exc.detail})


@router.get("/health")
def health(c: Deps) -> dict:
    return {"ok": True, "llm_mode": llm_mode(c.settings), "demo_mode": c.settings.demo_mode}


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

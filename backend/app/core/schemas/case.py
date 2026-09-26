"""Estado do case (ARCHITECTURE.md §4, §19.9). É o que GET /api/cases/{id} devolve."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.schemas.context import CaseScope
from app.core.schemas.outputs import InterpretedDemand, ReviewOutput
from app.core.schemas.report import Report


class CaseStatus(str, Enum):
    created = "created"
    interpreting = "interpreting"
    waiting_input = "waiting_input"
    planned = "planned"
    running = "running"
    reviewing = "reviewing"
    consolidating = "consolidating"
    human_review_required = "human_review_required"
    completed_demo = "completed_demo"
    failed = "failed"


class AgentStatus(str, Enum):
    selected = "selected"
    waiting = "waiting"
    running = "running"
    completed = "completed"
    reopened = "reopened"
    blocked = "blocked"
    failed = "failed"


class DemoOptions(BaseModel):
    adversarial_document: bool = False


class CreateCaseRequest(BaseModel):
    user_id: str
    prompt: str
    demo_options: DemoOptions = Field(default_factory=DemoOptions)


class InputRequest(BaseModel):
    answers: dict[str, Any]


class HumanReviewRequest(BaseModel):
    decision: str  # "approve_next_step" | "request_adjustment"
    comment: str = ""


class MissingInfoRequest(BaseModel):
    reason: str  # "client_unresolved" | "client_ambiguous" | "eligibility_blocked" | "amount_missing"
    items: list[str]
    message: str


class AgentCardState(BaseModel):
    agent_id: str
    name: str
    status: AgentStatus
    round: int = 0
    summary: str = ""
    data_domains_accessed: list[str] = Field(default_factory=list)
    tool_calls: int = 0
    source_count: int = 0
    denied_calls: int = 0
    output: dict[str, Any] | None = None  # output compacto (dump do output_schema)


class CaseCounters(BaseModel):
    tool_calls: int = 0
    sources: int = 0
    permission_checks: int = 0
    permission_denials: int = 0
    security_events: int = 0
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_ms: int = 0


class CaseState(BaseModel):
    case_id: str
    status: CaseStatus
    user_id: str
    prompt: str
    demo_options: DemoOptions
    created_at: datetime
    updated_at: datetime
    interpreted: InterpretedDemand | None = None
    scope: CaseScope | None = None
    selected_agents: list[str] = Field(default_factory=list)
    agents: list[AgentCardState] = Field(default_factory=list)
    missing_info: MissingInfoRequest | None = None
    review: ReviewOutput | None = None
    rework_rounds: int = 0
    report: Report | None = None
    counters: CaseCounters = Field(default_factory=CaseCounters)
    llm_mode: str = "real"
    error: str | None = None
    last_event_seq: int = 0

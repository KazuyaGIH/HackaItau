"""Event Log append-only por case (ARCHITECTURE.md §15). Audit é uma visão filtrada deste log."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    CASE_CREATED = "CASE_CREATED"
    ORCHESTRATOR_STARTED = "ORCHESTRATOR_STARTED"
    BOOTSTRAP_RESOLVED = "BOOTSTRAP_RESOLVED"
    MISSING_INFO_REQUESTED = "MISSING_INFO_REQUESTED"
    INPUT_RECEIVED = "INPUT_RECEIVED"
    SCOPE_FROZEN = "SCOPE_FROZEN"
    AGENT_SELECTED = "AGENT_SELECTED"
    AGENT_STARTED = "AGENT_STARTED"
    PERMISSION_CHECKED = "PERMISSION_CHECKED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    SECURITY_EVENT = "SECURITY_EVENT"
    TOOL_CALLED = "TOOL_CALLED"
    LLM_CALLED = "LLM_CALLED"
    GROUNDING_REJECTED = "GROUNDING_REJECTED"
    OUTPUT_REJECTED = "OUTPUT_REJECTED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    DOCUMENT_ATTACHED = "DOCUMENT_ATTACHED"
    REVIEW_STARTED = "REVIEW_STARTED"
    REVIEW_ISSUE_FOUND = "REVIEW_ISSUE_FOUND"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    TASK_REOPENED = "TASK_REOPENED"
    RESULT_CONSOLIDATED = "RESULT_CONSOLIDATED"
    OUTPUT_GUARD_APPLIED = "OUTPUT_GUARD_APPLIED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_ADJUSTMENT_REQUESTED = "HUMAN_ADJUSTMENT_REQUESTED"
    CASE_COMPLETED = "CASE_COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


AUDIT_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.BOOTSTRAP_RESOLVED,
        EventType.SCOPE_FROZEN,
        EventType.PERMISSION_CHECKED,
        EventType.PERMISSION_DENIED,
        EventType.SECURITY_EVENT,
        EventType.TOOL_CALLED,
        EventType.GROUNDING_REJECTED,
        EventType.OUTPUT_REJECTED,
        EventType.DOCUMENT_ATTACHED,
        EventType.OUTPUT_GUARD_APPLIED,
        EventType.HUMAN_REVIEW_REQUIRED,
        EventType.HUMAN_APPROVED,
        EventType.HUMAN_ADJUSTMENT_REQUESTED,
    }
)


class SecurityEventKind(str, Enum):
    INJECTION_SUSPECTED = "INJECTION_SUSPECTED"
    SCOPE_VIOLATION_BLOCKED = "SCOPE_VIOLATION_BLOCKED"
    SECRET_LEAK_BLOCKED = "SECRET_LEAK_BLOCKED"


class Event(BaseModel):
    seq: int
    ts: datetime
    case_id: str
    type: EventType
    agent_id: str | None = None
    task_id: str | None = None
    # pequeno, sem dados de cliente: só ids, códigos, contagens, flags
    payload: dict[str, Any] = Field(default_factory=dict)
    audit: bool = False


class ToolEventPayload(BaseModel):
    """Payload de PERMISSION_CHECKED / PERMISSION_DENIED / TOOL_CALLED (ESPECIFICACAO §32)."""

    action: str
    resource_domain: str
    resource_key: str | None = None
    allowed: bool
    reason: str | None = None
    purpose: str
    source_ids: list[str] = Field(default_factory=list)
    fields_hidden: int = 0
    probe: bool = False


class LLMEventPayload(BaseModel):
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    retry: bool = False

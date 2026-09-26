"""EventLog append-only por case (ARCHITECTURE.md §15). Payloads pequenos: ids, códigos, contagens, flags."""

from datetime import datetime, timezone
from typing import Any

from app.core.schemas.events import AUDIT_EVENT_TYPES, Event, EventType


class EventLog:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self._events: list[Event] = []

    def emit(
        self,
        type_: EventType,
        payload: dict[str, Any] | None = None,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> Event:
        ev = Event(
            seq=len(self._events) + 1,
            ts=datetime.now(timezone.utc),
            case_id=self.case_id,
            type=type_,
            agent_id=agent_id,
            task_id=task_id,
            payload=payload or {},
            audit=type_ in AUDIT_EVENT_TYPES,
        )
        self._events.append(ev)
        return ev

    def all(self) -> list[Event]:
        return list(self._events)

    def list_after(self, seq: int) -> list[Event]:
        return [e for e in self._events if e.seq > seq]

    def of_type(self, *types: EventType) -> list[Event]:
        wanted = set(types)
        return [e for e in self._events if e.type in wanted]

    @property
    def last_seq(self) -> int:
        return len(self._events)

    def __len__(self) -> int:
        return len(self._events)

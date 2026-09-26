"""CaseStore em memória (TASKS.md: estado inicial = dicionário). Um CaseRecord agrupa estado, eventos e evidências."""

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.events import EventLog
from app.core.evidence import EvidenceRegistry
from app.core.schemas.case import CaseState, CaseStatus, DemoOptions


@dataclass
class CaseRecord:
    state: CaseState
    events: EventLog
    evidence: EvidenceRegistry = field(default_factory=EvidenceRegistry)

    def touch(self) -> None:
        self.state.updated_at = datetime.now(timezone.utc)
        self.state.last_event_seq = self.events.last_seq


class CaseStore:
    def __init__(self) -> None:
        self._cases: dict[str, CaseRecord] = {}

    def create(self, user_id: str, prompt: str, demo_options: DemoOptions, llm_mode: str) -> CaseRecord:
        case_id = f"case-{secrets.token_hex(4)}"
        now = datetime.now(timezone.utc)
        state = CaseState(
            case_id=case_id,
            status=CaseStatus.created,
            user_id=user_id,
            prompt=prompt,
            demo_options=demo_options,
            created_at=now,
            updated_at=now,
            llm_mode=llm_mode,
        )
        record = CaseRecord(state=state, events=EventLog(case_id))
        self._cases[case_id] = record
        return record

    def get(self, case_id: str) -> CaseRecord | None:
        return self._cases.get(case_id)

    def __contains__(self, case_id: object) -> bool:
        return case_id in self._cases

    def __len__(self) -> int:
        return len(self._cases)

"""CaseStore em memória (TASKS.md: estado inicial = dicionário). Um CaseRecord agrupa estado, eventos e evidências."""

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.events import EventLog
from app.core.evidence import EvidenceRegistry
from app.core.schemas.agent import AgentResult
from app.core.schemas.case import CaseState, CaseStatus, DemoOptions
from app.core.schemas.outputs import ReviewOutput


@dataclass
class RunJob:
    """O que o Orchestrator está executando — é o que um retry retoma."""

    kind: str  # "execution" | "human_adjustment"
    round: int = 1
    target_agent: str | None = None
    comment: str = ""  # comentário do analista (UNTRUSTED no prompt)


@dataclass
class CaseRecord:
    state: CaseState
    events: EventLog
    evidence: EvidenceRegistry = field(default_factory=EvidenceRegistry)
    answers: dict[str, Any] = field(default_factory=dict)  # respostas do usuário após scope congelado (UNTRUSTED)
    run_task: asyncio.Task[None] | None = field(default=None, repr=False)
    # checkpoints da execução: um retry reaproveita o que já concluiu em vez de repetir chamadas ao LLM
    job: RunJob | None = None
    completed: dict[str, AgentResult] = field(default_factory=dict)  # "agent_id@R<n>" → resultado
    reviews: dict[int, ReviewOutput] = field(default_factory=dict)  # rodada → review consolidado
    results: dict[str, AgentResult] = field(default_factory=dict)  # último resultado de cada agente (base de ajustes)
    first_round: dict[str, AgentResult] = field(default_factory=dict)
    # params de rework que continuam valendo nas rodadas seguintes (ex.: baseline histórico do Risk)
    sticky_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    human_adjustments: int = 0
    attachments: list[dict[str, Any]] = field(default_factory=list)  # documentos anexados (registros como documents.json)

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

    def all(self) -> list[CaseRecord]:
        return list(self._cases.values())

    def __contains__(self, case_id: object) -> bool:
        return case_id in self._cases

    def __len__(self) -> int:
        return len(self._cases)

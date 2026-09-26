"""EvidenceRegistry por case (ARCHITECTURE.md §12). Populado só pelo Gateway (SRC/KB/CALC) e pelo runtime (OUT)."""

from app.core.schemas.evidence import (
    EVIDENCE_ID_RE,
    AgentOutputRecord,
    CalculationRecord,
    EvidenceItem,
    EvidenceRef,
    SourceRecord,
    evidence_kind,
)


class EvidenceRegistry:
    def __init__(self) -> None:
        self._items: dict[str, EvidenceItem] = {}

    def register(self, item: EvidenceItem) -> EvidenceItem:
        if not EVIDENCE_ID_RE.match(item.id):
            raise ValueError(f"evidence id inválido: {item.id}")
        # IDs são determinísticos: o mesmo registro re-coletado (rework) substitui a entrada sem duplicar
        self._items[item.id] = item
        return item

    def get(self, evidence_id: str) -> EvidenceItem | None:
        return self._items.get(evidence_id)

    def __contains__(self, evidence_id: object) -> bool:
        return evidence_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    def ids(self) -> set[str]:
        return set(self._items)

    def missing(self, ids: list[str]) -> list[str]:
        return [i for i in ids if i not in self._items]

    def sources(self) -> list[SourceRecord]:
        return [i for i in self._items.values() if isinstance(i, SourceRecord)]

    def calculations(self) -> list[CalculationRecord]:
        return [i for i in self._items.values() if isinstance(i, CalculationRecord)]

    def outputs(self) -> list[AgentOutputRecord]:
        return [i for i in self._items.values() if isinstance(i, AgentOutputRecord)]

    def ref(self, evidence_id: str) -> EvidenceRef | None:
        item = self._items.get(evidence_id)
        if item is None:
            return None
        if isinstance(item, SourceRecord):
            label = item.title or f"{item.resource_domain}:{item.resource_key}"
            return EvidenceRef(id=item.id, kind=item.kind, label=label, agent_id=item.accessed_by_agent, mock=item.mock)
        if isinstance(item, CalculationRecord):
            return EvidenceRef(id=item.id, kind="calculation", label=item.name, agent_id=item.computed_by_agent)
        return EvidenceRef(
            id=item.id, kind=evidence_kind(item.id), label=f"output {item.agent_id} R{item.round}", agent_id=item.agent_id
        )

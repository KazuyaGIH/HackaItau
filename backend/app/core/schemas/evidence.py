"""Evidence / source model (ARCHITECTURE.md §12).

Prefixos: SRC-<DOMAIN>-<KEY> (read), KB-<DOC>-c<n> (search), CALC-<NAME>-R<n> (calc), OUT-<agent_id>-R<n> (runtime).
Só o Gateway cria SRC/KB/CALC; só o runtime cria OUT. O LLM nunca cria IDs.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

EvidenceKind = Literal["source", "knowledge", "calculation", "agent_output"]

EVIDENCE_ID_RE = re.compile(r"^(SRC|KB|CALC|OUT)-[A-Za-z0-9_\-]+$")


def evidence_kind(evidence_id: str) -> EvidenceKind:
    prefix = evidence_id.split("-", 1)[0]
    return {"SRC": "source", "KB": "knowledge", "CALC": "calculation", "OUT": "agent_output"}[prefix]


def source_id(domain: str, key: str) -> str:
    return f"SRC-{domain.upper().replace('_', '-')}-{key}"


def knowledge_id(doc_id: str, chunk_index: int) -> str:
    return f"KB-{doc_id}-c{chunk_index}"


def calculation_id(name: str, round_: int) -> str:
    return f"CALC-{name.upper().replace('_', '-')}-R{round_}"


def output_id(agent_id: str, round_: int) -> str:
    return f"OUT-{agent_id}-R{round_}"


class SourceRecord(BaseModel):
    """Um registro de dados (ou chunk de conhecimento) já filtrado por row/field policy. Conteúdo é UNTRUSTED."""

    id: str
    kind: Literal["source", "knowledge"]
    resource_domain: str
    resource_key: str
    data: dict[str, Any]
    mock: bool = True
    accessed_by_agent: str
    fields_hidden: int = 0
    flagged: bool = False  # Injection Guard marcou como suspeito (não bloqueia)
    out_of_scope_refs: list[str] = Field(default_factory=list)  # client_ids fora do scope citados no conteúdo
    title: str | None = None  # knowledge: título do documento/seção


class CalculationRecord(BaseModel):
    id: str
    kind: Literal["calculation"] = "calculation"
    name: str
    formula: str
    inputs: dict[str, Any]  # nome → valor
    input_sources: dict[str, str]  # nome → source_id da premissa/dado
    thresholds_source_ids: list[str] = Field(default_factory=list)  # KB-* usados para classificar
    outputs: dict[str, Any]
    classification: str | None = None
    computed_by_agent: str
    round: int


class AgentOutputRecord(BaseModel):
    id: str
    kind: Literal["agent_output"] = "agent_output"
    agent_id: str
    round: int
    output: dict[str, Any]


EvidenceItem = SourceRecord | CalculationRecord | AgentOutputRecord


class EvidenceRef(BaseModel):
    """Referência compacta para o relatório/UI."""

    id: str
    kind: EvidenceKind
    label: str
    agent_id: str | None = None
    mock: bool = True


class EvidenceBundle(BaseModel):
    """Tudo que um agente recebe na fase reason. Fechado antes da chamada LLM; o LLM só pode citar estes IDs."""

    sources: list[SourceRecord] = Field(default_factory=list)
    calculations: list[CalculationRecord] = Field(default_factory=list)
    upstream_outputs: list[AgentOutputRecord] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)  # tools negadas na fase gather (razões), para transparência

    def allowed_ids(self) -> set[str]:
        return {s.id for s in self.sources} | {c.id for c in self.calculations} | {o.id for o in self.upstream_outputs}

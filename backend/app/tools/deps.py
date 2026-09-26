"""Dependências injetadas pelo Gateway nos handlers de tool. Handlers nunca importam a fonte física diretamente."""

from dataclasses import dataclass, field

from app.data.repository import DataRepository, KnowledgeRetriever


@dataclass(frozen=True)
class ToolDeps:
    repo: DataRepository
    knowledge: KnowledgeRetriever
    scenario_tags: tuple[str, ...] = field(default=())  # ex.: ("adversarial",) via demo_options

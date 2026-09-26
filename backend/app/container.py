"""Composição das dependências do processo (um backend, estado em memória). Trocar fonte de dados = trocar aqui."""

from dataclasses import dataclass
from functools import lru_cache

from app.config import Settings, get_settings
from app.core.store import CaseStore
from app.data.json_repository import JsonMockRepository
from app.governance.bootstrap_resolver import BootstrapClientResolver
from app.knowledge.retriever import KeywordKnowledgeRetriever
from app.orchestration.orchestrator import Orchestrator
from app.tools.data_tools import install_data_handlers


def llm_mode(s: Settings) -> str:
    if s.llm_configured:
        return "real"
    if s.llm_fallback_enabled:
        return "fallback"
    return "unconfigured"


@dataclass
class Container:
    settings: Settings
    store: CaseStore
    repo: JsonMockRepository
    knowledge: KeywordKnowledgeRetriever
    resolver: BootstrapClientResolver
    orchestrator: Orchestrator


def build_container(settings: Settings | None = None) -> Container:
    s = settings or get_settings()
    install_data_handlers()
    store = CaseStore()
    repo = JsonMockRepository(s.mock_data_dir)
    knowledge = KeywordKnowledgeRetriever(s.knowledge_corpus_dir)
    resolver = BootstrapClientResolver(repo)
    orchestrator = Orchestrator(store, resolver, llm_mode(s))
    return Container(s, store, repo, knowledge, resolver, orchestrator)


@lru_cache
def get_container() -> Container:
    return build_container()

"""Composição das dependências do processo (um backend, estado em memória). Trocar fonte de dados = trocar aqui."""

from dataclasses import dataclass
from functools import lru_cache

from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRuntime
from app.config import Settings, get_settings
from app.core.store import CaseStore
from app.data.json_repository import JsonMockRepository
from app.governance.bootstrap_resolver import BootstrapClientResolver
from app.knowledge.retriever import KeywordKnowledgeRetriever
from app.llm.openai_compat import OpenAICompatProvider
from app.llm.provider import LLMProvider
from app.orchestration.orchestrator import Orchestrator
from app.tools.calc_tools import install_calc_handlers
from app.tools.data_tools import install_data_handlers


def llm_mode(s: Settings) -> str:
    return "real" if s.llm_configured else "unconfigured"


def build_provider(s: Settings) -> LLMProvider | None:
    """Único ponto que lê LLM_API_KEY. Sem chave → None (a execução dos agentes falha de forma auditável)."""
    if not s.llm_configured:
        return None
    return OpenAICompatProvider(
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        timeout_seconds=s.llm_timeout_seconds,
        secret_values=s.secret_values(),
        max_retries=s.llm_max_retries,
        backoff_seconds=s.llm_retry_backoff_seconds,
    )


@dataclass
class Container:
    settings: Settings
    store: CaseStore
    repo: JsonMockRepository
    knowledge: KeywordKnowledgeRetriever
    resolver: BootstrapClientResolver
    agents: AgentRegistry
    runtime: AgentRuntime
    orchestrator: Orchestrator


def build_container(settings: Settings | None = None) -> Container:
    s = settings or get_settings()
    install_data_handlers()
    install_calc_handlers()
    store = CaseStore()
    repo = JsonMockRepository(s.mock_data_dir)
    knowledge = KeywordKnowledgeRetriever(s.knowledge_corpus_dir)
    resolver = BootstrapClientResolver(repo)
    agents = AgentRegistry()
    runtime = AgentRuntime(build_provider(s), s.llm_model)
    orchestrator = Orchestrator(
        store, resolver, s, agents=agents, runtime=runtime, repo=repo, knowledge=knowledge, llm_mode=llm_mode(s)
    )
    return Container(s, store, repo, knowledge, resolver, agents, runtime, orchestrator)


@lru_cache
def get_container() -> Container:
    return build_container()

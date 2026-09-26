import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.core.events import EventLog
from app.core.evidence import EvidenceRegistry
from app.core.schemas.context import CaseScope, ExecutionContext, UserIdentity
from app.data.json_repository import JsonMockRepository
from app.governance.loader import load_agent_cards, load_identities
from app.knowledge.retriever import KeywordKnowledgeRetriever
from app.tools.data_tools import install_data_handlers
from app.tools.deps import ToolDeps
from app.tools.gateway import Toolbox

FIXTURES = Path(__file__).parent / "fixtures"
PURPOSE = "credit_analysis_agro"


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def golden_case() -> dict:
    return json.loads((FIXTURES / "golden_case.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def mock_data(settings) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in settings.mock_data_dir.glob("*.json")}


@pytest.fixture(scope="session")
def repo() -> JsonMockRepository:
    return JsonMockRepository()


@pytest.fixture(scope="session")
def knowledge() -> KeywordKnowledgeRetriever:
    return KeywordKnowledgeRetriever()


@pytest.fixture(scope="session")
def cards():
    return load_agent_cards()


@pytest.fixture(scope="session")
def analyst() -> UserIdentity:
    return load_identities()["analyst-001"]


@pytest.fixture(scope="session")
def manager() -> UserIdentity:
    return load_identities()["manager-001"]


@pytest.fixture
def scope_001() -> CaseScope:
    return CaseScope(client_ids=("CLIENTE-001",), purpose=PURPOSE)


def make_ctx(user: UserIdentity, agent_id: str, scope: CaseScope, purpose: str = PURPOSE) -> ExecutionContext:
    return ExecutionContext(
        user=user, case_id="case-test", task_id="t-1", agent_id=agent_id, purpose=purpose, case_scope=scope
    )


@pytest.fixture
def toolbox_factory(repo, knowledge, cards, analyst, scope_001):
    install_data_handlers()

    def make(agent_id: str, *, user: UserIdentity = analyst, adversarial: bool = False, scope: CaseScope = scope_001):
        events = EventLog("case-test")
        evidence = EvidenceRegistry()
        deps = ToolDeps(repo, knowledge, ("adversarial",) if adversarial else ())
        return Toolbox(make_ctx(user, agent_id, scope), cards[agent_id], deps, events, evidence)

    return make

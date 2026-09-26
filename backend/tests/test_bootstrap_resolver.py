"""Bootstrap Client Resolver: só permissão do usuário; saída mínima; sem listagem/search irrestrito."""

from app.core.events import EventLog
from app.core.schemas.context import UserIdentity
from app.core.schemas.events import EventType
from app.governance.bootstrap_resolver import BootstrapClientResolver, ClientRef


def _resolver(repo):
    return BootstrapClientResolver(repo)


def test_exact_id_resolves_with_minimal_output(repo, analyst):
    events = EventLog("case-t")
    r = _resolver(repo).resolve(analyst, "CLIENTE-001", events)
    assert r.status == "ok" and r.client == ClientRef(client_id="CLIENTE-001", name="Fazenda Horizonte S.A.")
    assert set(ClientRef.model_fields) == {"client_id", "name"}
    ev = events.of_type(EventType.BOOTSTRAP_RESOLVED)
    assert len(ev) == 1 and ev[0].payload["matched"] is True and "financ" not in str(ev[0].payload)


def test_exact_name_normalized_resolves(repo, analyst):
    r = _resolver(repo).resolve(analyst, "  fazenda horizonte s.a. ")
    assert r.status == "ok" and r.client is not None and r.client.client_id == "CLIENTE-001"


def test_lowercase_id_resolves(repo, analyst):
    assert _resolver(repo).resolve(analyst, "cliente-001").status == "ok"


def test_user_without_profile_permission_is_denied(repo):
    user = UserIdentity(user_id="u", name="x", role="r", permissions_read=("market_data",))
    events = EventLog("case-t")
    r = _resolver(repo).resolve(user, "CLIENTE-001", events)
    assert r.status == "denied" and r.client is None
    assert events.of_type(EventType.BOOTSTRAP_RESOLVED)[0].payload["denied"] is True


def test_short_name_and_wildcards_are_not_found(repo, analyst):
    res = _resolver(repo)
    for ref in ("Faz", "*", "Fazenda%", "", None, "CLIENTE-*"):
        r = res.resolve(analyst, ref)
        assert r.status == "not_found" and r.client is None, ref


def test_prefix_and_partial_names_do_not_match(repo, analyst):
    res = _resolver(repo)
    assert res.resolve(analyst, "Fazenda Horizonte").status == "not_found"
    assert res.resolve(analyst, "Horizonte S.A.").status == "not_found"


def test_ambiguous_returns_count_without_candidates(analyst):
    class Repo:
        def find_clients_exact(self, ref):
            return [{"client_id": "CLIENTE-010", "name": "Agro X"}, {"client_id": "CLIENTE-011", "name": "Agro X"}]

    r = BootstrapClientResolver(Repo()).resolve(analyst, "Agro X Ltda")
    assert r.status == "ambiguous" and r.count == 2 and r.client is None


def test_unknown_client_not_found(repo, analyst):
    assert _resolver(repo).resolve(analyst, "CLIENTE-777").status == "not_found"

"""API S1: ciclo de bootstrap do case (create → resolve → SCOPE_FROZEN | waiting_input → input)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

PROMPT = "O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2026/27."


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_create_case_freezes_scope_and_selects_agents(client):
    r = client.post("/api/cases", json={"user_id": "analyst-001", "prompt": PROMPT})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "planned"
    assert body["scope"]["client_ids"] == ["CLIENTE-001"] and body["scope"]["purpose"] == "credit_analysis_agro"
    assert body["interpreted"]["requested_amount"] == 50_000_000
    assert body["selected_agents"] == ["agro_eligibility", "agro_credit_risk", "agro_structuring", "credit_review"]
    assert body["llm_mode"] in ("real", "fallback", "unconfigured")

    events = client.get(f"/api/cases/{body['case_id']}/events", params={"after": 0}).json()
    types = [e["type"] for e in events]
    assert types[:4] == ["CASE_CREATED", "ORCHESTRATOR_STARTED", "BOOTSTRAP_RESOLVED", "SCOPE_FROZEN"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    after = client.get(f"/api/cases/{body['case_id']}/events", params={"after": events[-1]["seq"]}).json()
    assert after == []


def test_unresolved_client_waits_for_input_then_freezes(client):
    r = client.post("/api/cases", json={"user_id": "analyst-001", "prompt": "quero crédito para a safra"})
    body = r.json()
    assert body["status"] == "waiting_input" and body["missing_info"]["reason"] == "client_unresolved"
    cid = body["case_id"]

    r = client.post(f"/api/cases/{cid}/input", json={"answers": {"client_ref": "CLIENTE-777"}})
    assert r.json()["status"] == "waiting_input"  # não existe → continua pedindo

    r = client.post(f"/api/cases/{cid}/input", json={"answers": {"client_ref": "CLIENTE-001"}})
    assert r.json()["status"] == "planned" and r.json()["scope"]["client_ids"] == ["CLIENTE-001"]

    r = client.post(f"/api/cases/{cid}/input", json={"answers": {"client_ref": "CLIENTE-002"}})
    assert r.status_code == 409  # scope congelado: input não muda mais o cliente
    assert client.get(f"/api/cases/{cid}").json()["scope"]["client_ids"] == ["CLIENTE-001"]


def test_run_not_available_before_s3_but_state_guarded(client):
    r = client.post("/api/cases", json={"user_id": "analyst-001", "prompt": PROMPT})
    cid = r.json()["case_id"]
    assert client.post(f"/api/cases/{cid}/run").status_code == 501
    assert client.post(f"/api/cases/{cid}/human-review", json={"decision": "approve_next_step"}).status_code == 409


def test_unknown_user_and_case(client):
    assert client.post("/api/cases", json={"user_id": "ghost", "prompt": PROMPT}).status_code == 403
    assert client.get("/api/cases/case-nope").status_code == 404


def test_health_reports_llm_mode(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True and body["llm_mode"] in ("real", "fallback", "unconfigured")

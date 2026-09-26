"""S3.7 — contrato HTTP usado pelo frontend: run assíncrono → polling de estado/eventos → report → human-review."""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import build_container, get_container
from app.main import app

PROMPT = "O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2025/26."


@pytest.fixture
def client():
    container = build_container(Settings(llm_api_key="", llm_fallback_enabled=True, _env_file=None))
    app.dependency_overrides[get_container] = lambda: container
    with TestClient(app) as c:  # lifespan mantém o event loop vivo para a task em background
        yield c
    app.dependency_overrides.clear()


def _wait_terminal(client: TestClient, cid: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = client.get(f"/api/cases/{cid}").json()
        if st["status"] not in ("planned", "running"):
            return st
        time.sleep(0.05)
    raise AssertionError("run não terminou a tempo")


def test_run_poll_report_and_human_gate(client):
    cid = client.post("/api/cases", json={"user_id": "analyst-001", "prompt": PROMPT}).json()["case_id"]
    r = client.post(f"/api/cases/{cid}/run")
    assert r.status_code == 202 and r.json()["status"] in ("running", "human_review_required")
    assert client.post(f"/api/cases/{cid}/run").status_code == 409

    st = _wait_terminal(client, cid)
    assert st["status"] == "human_review_required", st.get("error")
    assert st["llm_mode"] == "fallback" and all(a["fallback_used"] for a in st["agents"])
    assert st["counters"]["llm_calls"] >= 4 and st["counters"]["sources"] > 0
    assert {a["agent_id"]: a["status"] for a in st["agents"]} == {
        "agro_eligibility": "completed",
        "agro_credit_risk": "completed",
        "agro_structuring": "completed",
        "credit_review": "completed",
    }

    events = client.get(f"/api/cases/{cid}/events", params={"after": 0}).json()
    types = [e["type"] for e in events]
    assert types[-1] == "HUMAN_REVIEW_REQUIRED" and "RESULT_CONSOLIDATED" in types
    assert types.index("AGENT_STARTED") < types.index("REVIEW_STARTED")
    assert client.get(f"/api/cases/{cid}/events", params={"after": events[-1]["seq"]}).json() == []

    rep = client.get(f"/api/cases/{cid}/report")
    assert rep.status_code == 200
    body = rep.json()
    assert body["decision_status"] == "ready_for_human_review" and body["human_gate"]["status"] == "pending"
    assert len(body["alternatives"]) >= 2 and body["review"]["findings"]

    calc = client.get(f"/api/cases/{cid}/evidence/{body['calculations'][0]['calculation_id']}")
    assert calc.status_code == 200 and calc.json()["kind"] == "calculation" and "formula" in calc.json()
    src = client.get(f"/api/cases/{cid}/evidence/SRC-CLIENT-PROFILE-CLIENTE-001").json()
    assert src["kind"] == "source" and "tax_id" not in src["data"]  # campo `never` nunca chega à UI
    assert client.get(f"/api/cases/{cid}/evidence/SRC-CLIENT-PROFILE-CLIENTE-999").status_code == 404

    r = client.post(f"/api/cases/{cid}/human-review", json={"decision": "request_adjustment", "comment": "detalhar"})
    assert r.status_code == 200 and r.json()["status"] == "human_review_required"
    r = client.post(f"/api/cases/{cid}/human-review", json={"decision": "approve_next_step"})
    assert r.status_code == 200 and r.json()["status"] == "completed_demo"
    assert client.get(f"/api/cases/{cid}/report").json()["human_gate"]["status"] == "approved_next_step"
    assert client.post(f"/api/cases/{cid}/human-review", json={"decision": "approve_next_step"}).status_code == 409

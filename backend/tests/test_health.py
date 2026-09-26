from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_llm_mode():
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["llm_mode"] in {"real", "fallback", "unconfigured"}

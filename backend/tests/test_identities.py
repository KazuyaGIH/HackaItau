from fastapi.testclient import TestClient

from app.main import app


def test_identities_lists_demo_users_with_permissions():
    r = TestClient(app).get("/api/identities")
    assert r.status_code == 200
    users = {u["user_id"]: u for u in r.json()}
    assert {"analyst-001", "manager-001"} <= users.keys()
    assert "client_financials" in users["analyst-001"]["permissions_read"]
    assert "client_financials" not in users["manager-001"]["permissions_read"]

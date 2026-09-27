import pytest
from fastapi.testclient import TestClient

from accountdomino import config
from accountdomino.api import app
from accountdomino.client import DominoClient, ExternalRequestBlocked


@pytest.fixture
def client(db_file):
    return TestClient(app)


def test_services(client):
    ids = [s["service_id"] for s in client.get("/services").json()]
    assert ids == ["mail", "shop", "community", "school"]


def test_login_flow_and_logs(client):
    assert client.post("/scenarios/s1/load").status_code == 200
    run_id = client.post("/runs", json={
        "profile": "after", "leaked_service_id": "community", "leaked_username": "student01"}).json()["run_id"]
    results = {}
    for sid in config.SERVICES:
        r = client.post(f"/services/{sid}/login", json={
            "profile": "after", "username": "student01", "password": "Domino-A!2024", "run_id": run_id})
        assert r.status_code == 200
        results[sid] = r.json()["result"]
    # 학교는 다른 비밀번호(C)라 MFA 단계 전에 비밀번호 불일치로 멈춘다
    assert results == {"mail": "MFA 차단", "shop": "접근 성공", "community": "접근 성공", "school": "비밀번호 불일치"}

    logs = client.get(f"/runs/{run_id}/logs").json()
    assert len(logs) == 4
    assert all("Domino-" not in str(log) for log in logs)


def test_unknown_service_returns_404(client):
    r = client.post("/services/bank/login", json={"profile": "before", "username": "a", "password": "b"})
    assert r.status_code == 404


def test_put_accounts_validation(client):
    bad_group = [{"service_id": "mail", "username": "u", "password_group": "Z", "mfa_enabled": False}]
    assert client.put("/profiles/before/accounts", json=bad_group).status_code == 422
    ok = [{"service_id": "mail", "username": "u", "password_group": "C", "mfa_enabled": True}]
    assert client.put("/profiles/before/accounts", json=ok).status_code == 200
    accounts = client.get("/profiles/before/accounts").json()
    assert accounts == [{"service_id": "mail", "username": "u", "password_group": "C", "mfa_enabled": True}]


def test_client_blocks_external_hosts():
    with pytest.raises(ExternalRequestBlocked):
        DominoClient("https://mail.example.com")
    DominoClient("http://127.0.0.1:8000")  # 로컬은 허용

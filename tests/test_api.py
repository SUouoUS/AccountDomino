import pytest
from fastapi.testclient import TestClient

from accountdomino import config
from accountdomino.api import app
from accountdomino.client import DominoClient, ExternalRequestBlocked
from accountdomino.scenarios import build_scenario
from accountdomino.simulation import expected_result, leaked_credential, target_services


@pytest.fixture
def client(db_file):
    return TestClient(app)


def test_services(client):
    ids = [s["service_id"] for s in client.get("/services").json()]
    assert ids == list(config.SERVICES) and len(ids) == config.MAX_ACCOUNT_COUNT


@pytest.mark.parametrize("count", [config.DEFAULT_ACCOUNT_COUNT, config.MAX_ACCOUNT_COUNT])
def test_login_flow_matches_settings_and_logs(client, count):
    assert client.post("/scenarios/s1/load", params={"count": count}).status_code == 200
    accounts = client.get("/profiles/after/accounts").json()
    assert accounts == build_scenario("s1", count)["after"]
    before = client.get("/profiles/before/accounts").json()
    username, password = leaked_credential(before, "community")
    run_id = client.post("/runs", json={
        "profile": "after", "leaked_service_id": "community", "leaked_username": username}).json()["run_id"]
    by_service = {a["service_id"]: a for a in accounts}
    targets = target_services(accounts, "community")
    for sid in targets:
        r = client.post(f"/services/{sid}/login", json={
            "profile": "after", "username": username, "password": password, "run_id": run_id})
        assert r.status_code == 200
        assert r.json()["result"] == expected_result(by_service[sid], username, password)

    logs = client.get(f"/runs/{run_id}/logs").json()
    assert len(logs) == count - 1
    assert all("Domino-" not in str(log) for log in logs)


@pytest.mark.parametrize("count", [config.MIN_ACCOUNT_COUNT - 1, config.MAX_ACCOUNT_COUNT + 1])
def test_load_scenario_count_is_range_checked(client, count):
    assert client.post("/scenarios/s1/load", params={"count": count}).status_code == 422


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

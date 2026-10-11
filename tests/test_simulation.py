"""기본 시나리오를 같은 유출 정보로 전후 실행하고, 계정별 설정 대조(oracle) 결과와 인증 결과를 비교한다."""
import copy

import pytest

from accountdomino import auth, config
from accountdomino.scenarios import SCENARIOS, build_scenario, password_for
from accountdomino.simulation import (
    expected_result, leaked_credential, shared_credential_services, summarize, target_services,
)

S, M, F = config.RESULT_SUCCESS, config.RESULT_MFA_BLOCKED, config.RESULT_MISMATCH
COUNTS = [config.MIN_ACCOUNT_COUNT, config.DEFAULT_ACCOUNT_COUNT, config.MAX_ACCOUNT_COUNT]


def run_with_same_leak(conn, before, after, leaked_service_id):
    """변경 전 설정의 출처 계정에서 유출 정보를 한 번만 만들고, 전후 모두 출처를 뺀 서비스에 사용한다."""
    username, password = leaked_credential(before, leaked_service_id)
    results, expected = {}, {}
    for profile, accounts in (("before", before), ("after", after)):
        auth.save_accounts(conn, profile, [auth.AccountSetting(**a) for a in accounts])
        by_service = {a["service_id"]: a for a in accounts}
        targets = target_services(accounts, leaked_service_id)
        results[profile] = [
            {"service_id": sid, "result": auth.authenticate(conn, profile, sid, username, password)}
            for sid in targets
        ]
        expected[profile] = {sid: expected_result(by_service.get(sid), username, password) for sid in targets}
    return results, expected


@pytest.mark.parametrize("count", COUNTS)
@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_auth_results_match_settings_per_account(conn, scenario_id, count):
    sc = build_scenario(scenario_id, count)
    leaked = SCENARIOS[scenario_id]["leaked_service_id"]
    results, expected = run_with_same_leak(conn, sc["before"], sc["after"], leaked)
    for profile, rows in results.items():
        assert len(rows) == count - 1                   # 출처를 뺀 나머지가 검사 대상
        assert leaked not in {r["service_id"] for r in rows}
        assert {r["service_id"]: r["result"] for r in rows} == expected[profile]


def test_s2_source_account_kept_old_password_is_a_setting_condition(conn):
    """② 변형: 출처(쇼핑) 계정만 기존 비밀번호를 유지해도 출처는 검사 대상이 아니다. 다른 계정 결과는 설정대로다."""
    sc = SCENARIOS["s2"]
    after = copy.deepcopy(sc["after"])
    next(a for a in after if a["service_id"] == "shop")["password_group"] = "A"
    results, expected = run_with_same_leak(conn, sc["before"], after, "shop")
    after_results = {r["service_id"]: r["result"] for r in results["after"]}
    assert "shop" not in after_results
    assert after_results == expected["after"]


# ---- 결과 유형별 독립 테스트(작은 설정을 직접 만들어 실제 인증 로직으로 확인) ----------------------------
LEAK_USER, LEAK_GROUP = "tester", "A"
LEAK_PW = password_for(LEAK_GROUP, "community")


def _single(conn, **account):
    """작은 설정 하나를 저장하고 서버가 실제 기록한 단계(authenticate_steps)를 돌려준다."""
    acc = {"service_id": "mail", "username": LEAK_USER, "password_group": LEAK_GROUP, "mfa_enabled": False, **account}
    auth.save_accounts(conn, "before", [auth.AccountSetting(**acc)])
    rec = auth.authenticate_steps(conn, "before", acc["service_id"], LEAK_USER, LEAK_PW)
    return acc, rec


def test_username_mismatch_stops_at_id_step(conn):
    acc, rec = _single(conn, username="someone_else")
    assert rec["result"] == F and expected_result(acc, LEAK_USER, LEAK_PW) == F
    # 아이디 불일치면 비밀번호·MFA 는 실제로 수행하지 않는다.
    assert rec["steps"] == {"try": "done", "id": "nomatch", "password": "skipped", "mfa": "skipped"}


def test_password_mismatch_stops_at_password_step(conn):
    acc, rec = _single(conn, password_group="B")
    assert rec["result"] == F and expected_result(acc, LEAK_USER, LEAK_PW) == F
    assert rec["steps"]["id"] == "match" and rec["steps"]["password"] == "nomatch"
    assert rec["steps"]["mfa"] == "skipped" and rec["verified"] is False


def test_unique_password_stops_at_password_step(conn):
    acc, rec = _single(conn, password_group="고유")
    assert rec["result"] == F and rec["steps"]["password"] == "nomatch"


def test_mfa_blocks_matching_credentials(conn):
    acc, rec = _single(conn, mfa_enabled=True)
    assert rec["result"] == M and expected_result(acc, LEAK_USER, LEAK_PW) == M
    # 비밀번호는 일치하지만(MFA 평가로 진입) 추가 인증을 완료하지 못해 차단.
    assert rec["steps"]["password"] == "match" and rec["steps"]["mfa"] == "blocked"
    assert rec["verified"] is True


def test_matching_credentials_without_mfa_succeed(conn):
    acc, rec = _single(conn)
    assert rec["result"] == S and expected_result(acc, LEAK_USER, LEAK_PW) == S
    assert rec["steps"]["password"] == "match" and rec["steps"]["mfa"] == "off"


def test_expected_result_rules():
    acc = {"service_id": "mail", "username": "u", "password_group": "A", "mfa_enabled": False}
    assert expected_result(acc, "u", "Domino-A!2024") == S
    assert expected_result({**acc, "mfa_enabled": True}, "u", "Domino-A!2024") == M
    assert expected_result(acc, "other", "Domino-A!2024") == F
    assert expected_result(acc, "u", "Domino-B!2024") == F
    assert expected_result(None, "u", "Domino-A!2024") == F


def test_summarize_excludes_errors_and_unknown_results():
    df = summarize({"before": [
        {"service_id": "mail", "result": S},
        {"service_id": "shop", "result": None, "error": "ConnectError"},
        {"service_id": "community", "result": "알 수 없음"},
    ]})
    assert df["변경 전"].to_dict() == {S: 1, F: 0, M: 0}


def test_leaked_credential_missing_service():
    assert leaked_credential([], "mail") is None


def test_target_services_excludes_only_source():
    accounts = build_scenario("s1", 12)["before"]
    targets = target_services(accounts, "community")
    assert len(targets) == 11 and "community" not in targets
    assert targets == [a["service_id"] for a in accounts if a["service_id"] != "community"]


def test_shared_credential_services_depends_on_source():
    sc = [
        {"service_id": "mail", "username": "k", "password_group": "A", "mfa_enabled": False},
        {"service_id": "shop", "username": "k", "password_group": "A", "mfa_enabled": False},
        {"service_id": "community", "username": "k", "password_group": "B", "mfa_enabled": False},
        {"service_id": "school", "username": "k", "password_group": "A", "mfa_enabled": False},
    ]
    assert shared_credential_services(sc, "shop") == ["mail", "shop", "school"]
    assert shared_credential_services(sc, "community") == ["community"]
    unique = [{**a, "password_group": "고유"} for a in sc]
    assert shared_credential_services(unique, "mail") == ["mail"]


@pytest.mark.parametrize("count", COUNTS)
@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_default_scenarios_mix_reused_and_distinct_passwords(scenario_id, count):
    sc = build_scenario(scenario_id, count)
    shared = shared_credential_services(sc["before"], SCENARIOS[scenario_id]["leaked_service_id"])
    assert 1 < len(shared) < len(sc["before"])

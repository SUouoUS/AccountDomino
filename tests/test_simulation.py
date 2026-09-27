"""기본 시나리오를 같은 유출 정보로 전후 실행하고, 설정 대조(oracle) 결과와 인증 결과를 비교한다."""
import copy

import pytest

from accountdomino import auth, config
from accountdomino.scenarios import SCENARIOS
from accountdomino.simulation import (
    expected_result, leaked_credential, shared_credential_services, summarize,
)

S, M, F = config.RESULT_SUCCESS, config.RESULT_MFA_BLOCKED, config.RESULT_MISMATCH


def run_with_same_leak(conn, before, after, leaked_service_id):
    """변경 전 설정의 출처 계정에서 유출 정보를 한 번만 만들고 전후 모두에 사용한다."""
    username, password = leaked_credential(before, leaked_service_id)
    results, expected = {}, {}
    for profile, accounts in (("before", before), ("after", after)):
        auth.save_accounts(conn, profile, [auth.AccountSetting(**a) for a in accounts])
        by_service = {a["service_id"]: a for a in accounts}
        results[profile] = [
            {"service_id": sid, "result": auth.authenticate(conn, profile, sid, username, password)}
            for sid in config.SERVICES
        ]
        expected[profile] = {sid: expected_result(by_service.get(sid), username, password)
                             for sid in config.SERVICES}
    return results, expected


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_auth_results_match_settings(conn, scenario_id):
    sc = SCENARIOS[scenario_id]
    results, expected = run_with_same_leak(conn, sc["before"], sc["after"], sc["leaked_service_id"])
    for profile, rows in results.items():
        assert {r["service_id"]: r["result"] for r in rows} == expected[profile]


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_settings_change_reduces_success(conn, scenario_id):
    sc = SCENARIOS[scenario_id]
    results, _ = run_with_same_leak(conn, sc["before"], sc["after"], sc["leaked_service_id"])
    df = summarize(results)
    assert df.loc[S, "변경 후"] < df.loc[S, "변경 전"]


def test_s2_source_account_kept_old_password_stays_accessible(conn):
    """② 변형: 출처(쇼핑) 계정만 기존 비밀번호를 유지하면 그 계정만 접근 성공으로 남는다."""
    sc = SCENARIOS["s2"]
    after = copy.deepcopy(sc["after"])
    next(a for a in after if a["service_id"] == "shop")["password_group"] = "A"
    results, expected = run_with_same_leak(conn, sc["before"], after, "shop")
    after_results = {r["service_id"]: r["result"] for r in results["after"]}
    assert after_results == expected["after"]
    assert after_results == {"mail": F, "shop": S, "community": F, "school": F}


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


def test_shared_credential_services_depends_on_source():
    sc = SCENARIOS["s2"]["before"]          # 메일·쇼핑·학교 = A, 커뮤니티 = B
    assert shared_credential_services(sc, "shop") == ["mail", "shop", "school"]
    assert shared_credential_services(sc, "community") == ["community"]
    same = [{**a, "password_group": "A"} for a in sc]
    assert shared_credential_services(same, "community") == ["mail", "shop", "community", "school"]
    unique = [{**a, "password_group": "고유"} for a in sc]
    assert shared_credential_services(unique, "mail") == ["mail"]


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_default_scenarios_mix_reused_and_distinct_passwords(scenario_id):
    sc = SCENARIOS[scenario_id]
    shared = shared_credential_services(sc["before"], sc["leaked_service_id"])
    assert 1 < len(shared) < len(sc["before"])

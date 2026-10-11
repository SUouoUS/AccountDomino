"""시나리오 생성: 계정 수 범위, 변경 전·후 service_id 대응, 계정 수 조정 시 입력값 유지."""
import pytest

from accountdomino import config
from accountdomino.scenarios import SCENARIOS, build_scenario, resize_accounts, service_ids


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
@pytest.mark.parametrize("count", range(config.MIN_ACCOUNT_COUNT, config.MAX_ACCOUNT_COUNT + 1))
def test_before_after_align_by_service_id(scenario_id, count):
    sc = build_scenario(scenario_id, count)
    before_ids = [a["service_id"] for a in sc["before"]]
    assert before_ids == [a["service_id"] for a in sc["after"]] == service_ids(count)
    assert SCENARIOS[scenario_id]["leaked_service_id"] in before_ids
    assert all(a["username"] for p in sc.values() for a in p)


def test_default_is_twelve_and_max_twenty():
    assert config.DEFAULT_ACCOUNT_COUNT == 12 and config.MAX_ACCOUNT_COUNT == 20
    assert all(len(sc["before"]) == 12 for sc in SCENARIOS.values())
    assert len(build_scenario("s1", 20)["before"]) == 20
    assert {"mail", "shop", "community", "school", "game", "cloud"} <= set(service_ids(12))


@pytest.mark.parametrize("count", [config.MIN_ACCOUNT_COUNT - 1, config.MAX_ACCOUNT_COUNT + 1])
def test_count_out_of_range(count):
    with pytest.raises(ValueError):
        build_scenario("s1", count)


def test_resize_keeps_edits_and_fills_new_accounts():
    profiles = build_scenario("s1", 12)
    profiles["before"][0]["username"] = "edited"
    profiles["after"][4]["mfa_enabled"] = True
    grown = resize_accounts(profiles, "s1", 15)
    assert len(grown["before"]) == len(grown["after"]) == 15
    assert grown["before"][0]["username"] == "edited"
    assert grown["after"][4]["mfa_enabled"] is True
    assert grown["before"][12:] == build_scenario("s1", 15)["before"][12:]

    shrunk = resize_accounts(grown, "s1", 5)
    assert [a["service_id"] for a in shrunk["before"]] == service_ids(5)
    assert shrunk["before"][0]["username"] == "edited" and shrunk["after"][4]["mfa_enabled"] is True
    # 원본은 바꾸지 않는다
    assert len(grown["before"]) == 15


@pytest.mark.parametrize("count", [12, 20])
@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_change_summary_matches_actual_data(scenario_id, count):
    from accountdomino.scenarios import change_summary
    profiles = build_scenario(scenario_id, count)
    summary = change_summary(profiles)
    assert summary.startswith("변경 후:")
    # 요약이 실제로 바뀐 항목만 반영하는지 대조
    before = {a["service_id"]: a for a in profiles["before"]}
    mfa_on = any(not before[a["service_id"]]["mfa_enabled"] and a["mfa_enabled"] for a in profiles["after"])
    pw = any(before[a["service_id"]]["password_group"] != a["password_group"] for a in profiles["after"])
    assert ("MFA ON" in summary) == mfa_on
    assert ("비밀번호" in summary) == pw


def test_change_summary_reports_no_change():
    from accountdomino.scenarios import change_summary
    p = build_scenario("s1", 12)
    p = {"before": p["before"], "after": [dict(a) for a in p["before"]]}
    assert change_summary(p) == "변경 후: 변경 없음"


def test_change_summary_uses_all_accounts_wording():
    from accountdomino.scenarios import change_summary
    p = build_scenario("s3", 12)   # 메일만 이미 MFA → 나머지 11개가 켜짐
    assert "MFA ON" in change_summary(p)

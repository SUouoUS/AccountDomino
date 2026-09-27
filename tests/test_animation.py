"""애니메이션 데이터: 멈춤 단계는 API 결과, 사유는 스냅샷 대조, 오류는 별도 처리."""
import copy
import json
import re

import pytest

from accountdomino import animation, config, simulation
from accountdomino.scenarios import SCENARIOS

S, M, F = config.RESULT_SUCCESS, config.RESULT_MFA_BLOCKED, config.RESULT_MISMATCH


def acc(service_id, username="u", group="A", mfa=False):
    return {"service_id": service_id, "username": username, "password_group": group, "mfa_enabled": mfa}


def rows(**results):
    return [{"service_id": sid, "result": r} for sid, r in results.items()]


@pytest.fixture
def snapshot():
    before = [acc("mail", mfa=True), acc("shop"), acc("community", group="B"), acc("school", username="v")]
    after = [acc("mail", mfa=True), acc("shop", group="고유"), acc("community", group="B"), acc("school", mfa=True)]
    return {
        "leaked": {"service_id": "shop", "username": "u", "password_group": "A"},
        "accounts": {"before": before, "after": after},
        "results": {
            "before": rows(mail=M, shop=S, community=F, school=F),
            "after": rows(mail=M, shop=F, community=F, school=F),
        },
    }


def lanes(payload, profile):
    return {ln["service_id"]: ln for ln in payload["profiles"][profile]["lanes"]}


def test_stop_stage_follows_api_result(snapshot):
    before = lanes(simulation.build_animation_payload(snapshot), "before")
    assert {sid: ln["stop_stage"] for sid, ln in before.items()} == {
        "mail": "mfa", "shop": "access", "community": "password", "school": "password"}


def test_reasons_when_consistent(snapshot):
    before = lanes(simulation.build_animation_payload(snapshot), "before")
    assert all(ln["consistent"] for ln in before.values())
    assert before["mail"]["reason"] == simulation.REASON_MFA
    assert before["shop"]["reason"] == simulation.REASON_SUCCESS
    assert before["community"]["reason"] == simulation.REASON_PASSWORD
    assert before["school"]["reason"] == simulation.REASON_USERNAME


def test_inconsistent_result_is_not_explained_by_guess(snapshot):
    # 설정상으로는 쇼핑(그룹 A, MFA 없음)이 접근 성공이어야 하지만 API 가 불일치를 돌려준 경우
    snapshot["results"]["before"] = rows(mail=M, shop=F, community=F, school=F)
    shop = lanes(simulation.build_animation_payload(snapshot), "before")["shop"]
    assert shop["stop_stage"] == "password"          # 멈춤 위치는 API 결과 기준
    assert shop["consistent"] is False
    assert shop["reason"] == simulation.REASON_INCONSISTENT


def test_errors_and_unknown_results_are_request_errors(snapshot):
    snapshot["results"]["after"] = [
        {"service_id": "mail", "result": None, "error": "ConnectError"},
        {"service_id": "shop", "result": "알 수 없음"},
        {"service_id": "community", "result": F},
    ]  # school 결과 누락
    payload = simulation.build_animation_payload(snapshot)
    after = lanes(payload, "after")
    for sid in ("mail", "shop", "school"):
        assert after[sid]["status"] == "error"
        assert after[sid]["result"] is None
        assert after[sid]["reason"] == simulation.REASON_ERROR
    assert after["mail"]["error"] == "ConnectError"
    assert after["shop"]["error"] == "알 수 없는 결과: 알 수 없음"
    assert payload["profiles"]["after"]["summary"] == {"success": 0, "blocked": 1, "errors": 3}


def test_changes_are_marked_only_on_after(snapshot):
    payload = simulation.build_animation_payload(snapshot)
    after, before = lanes(payload, "after"), lanes(payload, "before")
    assert all(ln["changes"] == [] for ln in before.values())
    assert [c["text"] for c in after["shop"]["changes"]] == ["비밀번호 그룹 A→고유"]
    assert {c["field"] for c in after["school"]["changes"]} == {"username", "mfa_enabled"}
    username_change = next(c for c in after["school"]["changes"] if c["field"] == "username")
    assert username_change["text"] == "아이디" and username_change["detail"] == "아이디 v → u"
    assert after["mail"]["changes"] == []


def test_payload_uses_snapshot_not_later_edits(snapshot):
    payload = simulation.build_animation_payload(copy.deepcopy(snapshot))
    snapshot["accounts"]["after"][0]["mfa_enabled"] = False  # 실행 이후 편집
    assert lanes(payload, "after")["mail"]["mfa_enabled"] is True


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_rendered_html_has_no_plaintext_password(scenario_id):
    sc = SCENARIOS[scenario_id]
    src = next(a for a in sc["before"] if a["service_id"] == sc["leaked_service_id"])
    snap = {
        "leaked": {"service_id": sc["leaked_service_id"], "username": src["username"],
                   "password_group": src["password_group"]},
        "accounts": {"before": sc["before"], "after": sc["after"]},
        "results": {"before": [], "after": []},
    }
    html = animation.render(simulation.build_animation_payload(snap))
    assert "Domino-" not in html and "Unique-" not in html
    data = json.loads(re.search(r"window\.DOMINO = (.*?);\n", html).group(1))
    assert data["leaked"]["username"] == src["username"]
    assert "__DATA__" not in html


def test_result_sentences(snapshot):
    payload = simulation.build_animation_payload(snapshot)
    assert payload["profiles"]["before"]["sentence"] == (
        "변경 전: 4개 서비스 중 1개에서 비인가 접근이 성공했고 "
        "2개는 아이디·비밀번호 확인 단계에서, 1개는 MFA 단계에서 차단되었습니다.")
    assert payload["profiles"]["after"]["sentence"] == (
        # 픽스처의 변경 후 학교(아이디 u, 그룹 A, MFA 켜짐)는 설정상 MFA 차단인데 API 결과가 불일치 → 안내 포함
        "변경 후: 4개 서비스 중 3개는 아이디·비밀번호 확인 단계에서, 1개는 MFA 단계에서 차단되었습니다 "
        "(1개는 설정과 인증 결과가 일치하지 않습니다).")
    assert payload["compare_sentence"] == (
        "같은 유출 정보로 시도했을 때 비인가 접근에 성공한 서비스는 변경 전 1개에서 변경 후 0개로 줄었습니다.")


def test_sentence_mentions_errors_and_inconsistency(snapshot):
    snapshot["results"]["before"] = [
        {"service_id": "mail", "result": None, "error": "ConnectError"},
        *rows(shop=F, community=F, school=F),   # shop 은 설정상 접근 성공이어야 함 → 불일치
    ]
    payload = simulation.build_animation_payload(snapshot)
    assert payload["profiles"]["before"]["sentence"] == (
        "변경 전: 4개 서비스 중 3개는 아이디·비밀번호 확인 단계에서 차단되었습니다 "
        "(1개는 설정과 인증 결과가 일치하지 않습니다, 1개는 요청 오류로 판정하지 못했습니다).")
    assert payload["compare_sentence"].endswith("(요청 오류 1건은 제외).")

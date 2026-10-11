"""애니메이션 데이터: 서버가 실제 수행한 단계 기록을 payload 로 옮긴다(프런트 재계산 없음)."""
import copy
import json

import pytest

from accountdomino import animation, auth, config, db, simulation
from accountdomino.auth import AccountSetting
from accountdomino.scenarios import SCENARIOS, build_scenario, resolve_password

S, M, F = config.RESULT_SUCCESS, config.RESULT_MFA_BLOCKED, config.RESULT_MISMATCH


def acc(service_id, username="u", group="A", mfa=False):
    return {"service_id": service_id, "username": username, "password_group": group, "mfa_enabled": mfa}


def _conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    return c


def _server_rows(conn, profile, accounts, leaked_user, leaked_pw, leaked_service, group_pw):
    settings = [AccountSetting(a["service_id"], a["username"], a["password_group"], a["mfa_enabled"],
                               resolve_password(a["password_group"], a["service_id"], group_pw))
                for a in accounts]
    auth.save_accounts(conn, profile, settings)
    out = []
    for sid in simulation.target_services(accounts, leaked_service):
        rec = auth.authenticate_steps(conn, profile, sid, leaked_user, leaked_pw)
        full = rec["target_hash"]
        out.append({"service_id": sid, "username": leaked_user, "result": rec["result"], "steps": rec["steps"],
                    "verified": rec["verified"], "mfa_enabled": rec["mfa_enabled"],
                    "mfa_checked": rec["steps"]["mfa"] in ("blocked", "off"),
                    "hash_full": full, "hash_short": full[:12] if full else None, "salt": rec["target_salt"], "algo": rec["algo"]})
    return out


def make_snapshot(before, after, leaked_service="shop", group_pw=None, run_id=7):
    """실제 모의 서버로 before/after 를 저장·로그인해 서버 응답 행을 수집한 스냅샷."""
    conn = _conn()
    src = next(a for a in before if a["service_id"] == leaked_service)
    leaked_pw = resolve_password(src["password_group"], leaked_service, group_pw)
    results = {"before": _server_rows(conn, "before", before, src["username"], leaked_pw, leaked_service, group_pw),
               "after": _server_rows(conn, "after", after, src["username"], leaked_pw, leaked_service, group_pw)}
    conn.close()
    return {"run_id": run_id,
            "leaked": {"service_id": leaked_service, "username": src["username"],
                       "password_group": src["password_group"]},
            "accounts": {"before": before, "after": after}, "results": results}


@pytest.fixture
def snapshot():
    # 출처 = 쇼핑. 검사 대상 메일·커뮤니티·학교. 메일=MFA, 커뮤니티=비번(B)불일치, 학교=아이디(v)불일치.
    before = [acc("mail", mfa=True), acc("shop"), acc("community", group="B"), acc("school", username="v")]
    after = [acc("mail", mfa=True), acc("shop", group="고유"), acc("community", group="B"), acc("school", mfa=True)]
    return make_snapshot(before, after)


def lanes(payload, profile):
    return {ln["service_id"]: ln for ln in payload["profiles"][profile]["lanes"]}


def test_source_is_separate_and_not_a_target(snapshot):
    payload = simulation.build_animation_payload(snapshot)
    for profile in config.PROFILES:
        assert list(lanes(payload, profile)) == ["mail", "community", "school"]
        assert payload["profiles"][profile]["summary"]["total"] == 3
    assert payload["leaked"]["service"] == "쇼핑"
    assert payload["source"]["before"]["password_group"] == "A"
    assert [c["text"] for c in payload["source"]["after_changes"]] == ["비밀번호 A → 고유"]
    assert "검사 대상 아님" in payload["source"]["note"]
    assert payload["run_id"] == 7
    assert payload["order"] == ["mail", "community", "school"]
    assert [ln["service_id"] for ln in payload["profiles"]["after"]["lanes"]] == payload["order"]


def test_display_status_labels(snapshot):
    before = lanes(simulation.build_animation_payload(snapshot), "before")
    # 차단은 모두 '로그인 시도 차단'(보호), 성공은 '계정 침해'
    assert before["mail"]["short"] == "로그인 시도 차단" and before["mail"]["status_label"] == "로그인 시도 차단"
    assert before["community"]["short"] == "로그인 시도 차단"
    assert before["school"]["short"] == "로그인 시도 차단"


def test_reasons_from_server_steps(snapshot):
    payload = simulation.build_animation_payload(snapshot)
    before, after = lanes(payload, "before"), lanes(payload, "after")
    assert before["mail"]["reason"] == simulation.REASON_TEXT["blocked_mfa"]
    assert before["community"]["reason"] == simulation.REASON_TEXT["blocked_pw"]
    assert before["school"]["reason"] == simulation.REASON_TEXT["blocked_id"]
    assert {sid: ln["outcome"] for sid, ln in before.items()} == {
        "mail": "blocked_mfa", "community": "blocked_password", "school": "blocked_password"}
    assert after["school"]["outcome"] == "blocked_mfa"   # 아이디 u 로 맞췄지만 MFA 켜짐


def test_stop_stage_from_steps(snapshot):
    before = lanes(simulation.build_animation_payload(snapshot), "before")
    assert {sid: ln["stop_stage"] for sid, ln in before.items()} == {
        "mail": "mfa", "community": "password", "school": "id"}


def test_hash_meta_present_and_verified(snapshot):
    before = lanes(simulation.build_animation_payload(snapshot), "before")
    mail = before["mail"]
    assert mail["hash"]["short"] and mail["hash"]["full"] and mail["hash"]["salt"]
    assert len(mail["hash"]["short"]) == 12 and mail["hash"]["full"].startswith(mail["hash"]["short"])
    assert mail["hash"]["verified"] is True and mail["hash"]["mfa_checked"] is True   # 비번 일치 후 MFA 평가
    assert before["school"]["hash"]["verified"] is False   # 아이디 불일치 → 검증 안 함


def test_unknown_result_is_check_needed(snapshot):
    snapshot["results"]["before"][0] = {"service_id": "mail", "result": "알 수 없음",
                                        "steps": {"try": "done", "id": "match", "password": "match", "mfa": "off"}}
    mail = lanes(simulation.build_animation_payload(snapshot), "before")["mail"]
    assert mail["outcome"] == "inconsistent" and mail["status_label"] == "확인 필요"
    assert mail["reason"] == simulation.REASON_TEXT["inconsistent"]
    assert payload_summary(snapshot)["inconsistent"] == 1


def payload_summary(snapshot):
    return simulation.build_animation_payload(snapshot)["profiles"]["before"]["summary"]


def test_errors_are_request_errors(snapshot):
    snapshot["results"]["after"] = [
        {"service_id": "mail", "result": None, "error": "ConnectError"},
        {"service_id": "community", "result": "알 수 없음",
         "steps": {"try": "done", "id": "match", "password": "match", "mfa": "off"}},
    ]  # school 결과 누락
    payload = simulation.build_animation_payload(snapshot)
    after = lanes(payload, "after")
    assert after["mail"]["outcome"] == "error" and after["mail"]["error"] == "ConnectError"
    assert after["mail"]["reason"] == simulation.REASON_TEXT["error"]
    assert after["community"]["outcome"] == "inconsistent"
    assert after["school"]["outcome"] == "error"   # 결과 누락
    s = payload["profiles"]["after"]["summary"]
    assert s == {"total": 3, "success": 0, "blocked": 0, "blocked_password": 0, "blocked_mfa": 0,
                 "errors": 2, "inconsistent": 1}


def test_changes_are_marked_only_on_after(snapshot):
    payload = simulation.build_animation_payload(snapshot)
    after, before = lanes(payload, "after"), lanes(payload, "before")
    assert all(ln["changes"] == [] for ln in before.values())
    assert {c["field"] for c in after["school"]["changes"]} == {"username", "mfa_enabled"}
    username_change = next(c for c in after["school"]["changes"] if c["field"] == "username")
    assert username_change["text"] == "아이디 변경" and username_change["detail"] == "아이디 v → u"
    assert after["mail"]["changes"] == []


def test_payload_uses_snapshot_not_later_edits(snapshot):
    payload = simulation.build_animation_payload(copy.deepcopy(snapshot))
    snapshot["accounts"]["after"][0]["mfa_enabled"] = False  # 실행 이후 편집
    assert lanes(payload, "after")["mail"]["mfa_enabled"] is True


def _scenario_snapshot(scenario_id, count, group_pw=None):
    sc = build_scenario(scenario_id, count)
    leaked = SCENARIOS[scenario_id]["leaked_service_id"]
    return make_snapshot(sc["before"], sc["after"], leaked_service=leaked, group_pw=group_pw)


@pytest.mark.parametrize("count", [12, 20])
@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_target_count_and_summary_add_up(scenario_id, count):
    payload = simulation.build_animation_payload(_scenario_snapshot(scenario_id, count))
    for profile in config.PROFILES:
        p = payload["profiles"][profile]
        s = p["summary"]
        assert len(p["lanes"]) == s["total"] == count - 1
        assert s["success"] + s["blocked"] + s["errors"] + s["inconsistent"] == count - 1
        assert s["blocked"] == s["blocked_password"] + s["blocked_mfa"]
        assert p["sentence"].startswith(f"{p['label']}: 검사 대상 {count - 1}개 서비스 중")
        assert payload["leaked"]["service_id"] not in {ln["service_id"] for ln in p["lanes"]}


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_payload_has_no_plaintext_password(scenario_id):
    # 기본값(Domino-/Unique-)과 커스텀 센티넬 모두 payload JSON 에 없어야 한다.
    gp = {"A": "SENTINEL-PW", "B": "SENTINEL-B", "C": "SENTINEL-C", "D": "SENTINEL-D"}
    data = json.dumps(simulation.build_animation_payload(_scenario_snapshot(scenario_id, 20, group_pw=gp)),
                      ensure_ascii=False)
    assert "Domino-" not in data and "Unique-" not in data
    assert "SENTINEL" not in data


def test_component_assets_exist_and_do_not_embed_data():
    parts = animation.assets()
    assert set(parts) == {"html", "css", "js"}
    assert "export default function" in parts["js"]
    assert "시뮬레이션을 종료하겠습니까?" in parts["html"]
    assert "textContent" in parts["js"] and "esc =" in parts["js"] and "esc(lane" in parts["js"]


def test_result_sentences(snapshot):
    payload = simulation.build_animation_payload(snapshot)
    assert payload["profiles"]["before"]["sentence"] == (
        "변경 전: 검사 대상 3개 서비스 중 2개는 아이디·비밀번호 확인 단계에서, 1개는 MFA 단계에서 차단되었습니다.")
    assert payload["profiles"]["after"]["sentence"] == (
        "변경 후: 검사 대상 3개 서비스 중 1개는 아이디·비밀번호 확인 단계에서, 2개는 MFA 단계에서 차단되었습니다.")
    assert payload["compare_sentence"] == (
        "같은 유출 정보로 시도했을 때 비인가 접근에 성공한 서비스는 변경 전후 모두 0개로 같습니다.")


def _cmp(payload, profile, sid):
    return lanes(payload, profile)[sid]["compare"]


def test_compare_cause_and_explain(snapshot):
    p = simulation.build_animation_payload(snapshot)
    mail = _cmp(p, "before", "mail")        # MFA 차단
    assert mail["explain"] == simulation.EXPLAIN_MFA and mail["mfa_step"] == "추가 인증 요구 · 완료 못함"
    assert [r["cause"] for r in mail["rows"]] == [False, False, True]
    comm = _cmp(p, "before", "community")    # 비밀번호 불일치
    assert comm["explain"] == simulation.EXPLAIN_PASSWORD and comm["mfa_step"] == "진행하지 않음"
    assert [r["cause"] for r in comm["rows"]] == [False, True, False]
    sch = _cmp(p, "before", "school")        # 아이디 불일치
    assert sch["explain"] == simulation.EXPLAIN_USERNAME and sch["mfa_step"] == "진행하지 않음"
    assert [r["cause"] for r in sch["rows"]] == [True, False, False]


def test_compare_success_uses_mfa_not_used():
    snap = make_snapshot([acc("shop"), acc("mail")], [acc("shop"), acc("mail")])
    c = _cmp(simulation.build_animation_payload(snap), "before", "mail")
    assert c["explain"] == simulation.EXPLAIN_SUCCESS and c["mfa_step"] == "사용 안 함"
    assert all(r["cause"] is False for r in c["rows"])


def test_compare_distinguishes_unique_per_service():
    snap = make_snapshot([acc("shop", group="고유"), acc("mail", group="고유")],
                         [acc("shop", group="고유"), acc("mail", group="고유")])
    rows_ = _cmp(simulation.build_animation_payload(snap), "before", "mail")["rows"]
    pw = next(r for r in rows_ if r["k"] == "비밀번호")
    assert pw["attempt"] == "고유(쇼핑)" and pw["target"] == "고유(메일)" and pw["attempt"] != pw["target"]


def test_custom_group_value_changes_outcome():
    """그룹 A 값을 대상과 다르게 하면 서버가 실제 값으로 판정해 차단된다(그룹 이름 아님)."""
    before = [acc("shop"), acc("mail")]   # 둘 다 그룹 A, 아이디 u
    # 출처(shop) A=센티넬, 대상(mail) A=다른 값 → 그룹 이름은 같아도 실제 값이 달라 차단
    snap = make_snapshot(before, before, group_pw=None)
    mail = lanes(simulation.build_animation_payload(snap), "before")["mail"]
    assert mail["outcome"] == "success"   # 같은 기본값 → 침해
    # 값이 다르면 차단
    conn = _conn()
    gp = {"A": "SRC", "B": "x", "C": "y", "D": "z"}
    src_pw = resolve_password("A", "shop", gp)
    rows = _server_rows(conn, "before",
                        [acc("shop"), {**acc("mail"), }], "u", src_pw, "shop", None)  # mail 은 기본 A 값으로 저장
    conn.close()
    assert rows[0]["result"] == config.RESULT_MISMATCH   # 출처 값(SRC) != 대상 기본 A 값


def test_value_changed_tag_when_group_name_same(snapshot):
    """그룹 이름은 그대로여도 전후 실제 값이 달라지면 '비밀번호 값 변경' 태그를 보여 준다."""
    snapshot["value_changed"] = {"community": True, "mail": False}
    after = lanes(simulation.build_animation_payload(snapshot), "after")
    comm = [c for c in after["community"]["changes"] if c["field"] == "password_value"]
    assert comm and comm[0]["text"] == "비밀번호 값 변경"
    assert all(c["field"] != "password_value" for c in after["mail"]["changes"])


def test_value_changed_tag_not_added_when_group_already_changed():
    """그룹 자체가 바뀐 경우에는 기존 '비밀번호 A → 고유' 태그만 쓰고 중복 표시하지 않는다."""
    before = [acc("shop"), acc("mail")]
    after = [acc("shop"), acc("mail", group="고유")]
    snap = make_snapshot(before, after)
    snap["value_changed"] = {"mail": True}
    changes = lanes(simulation.build_animation_payload(snap), "after")["mail"]["changes"]
    assert [c["field"] for c in changes] == ["password_group"]

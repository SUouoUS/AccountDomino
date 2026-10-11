"""유출 자격증명 구성, 설정 대조 판정, 결과 집계, 애니메이션 데이터 생성(순수 함수)."""
from __future__ import annotations

import pandas as pd

from . import config
from .scenarios import UNIQUE_GROUP, password_for


def leaked_credential(accounts: list[dict], leaked_service_id: str) -> tuple[str, str] | None:
    """유출 출처 서비스 계정의 (아이디, 가상 비밀번호). 로그인 시도자가 손에 넣었다고 가정한다."""
    for acc in accounts:
        if acc["service_id"] == leaked_service_id:
            return acc["username"], password_for(acc["password_group"], leaked_service_id)
    return None



def shared_credential_services(accounts: list[dict], leaked_service_id: str) -> list[str]:
    """설정상 유출 정보와 같은 아이디·비밀번호를 쓰는 계정(출처 포함). 인증 결과가 아니라 설정 비교다."""
    leaked = leaked_credential(accounts, leaked_service_id)
    if leaked is None:
        return []
    username, password = leaked
    return [a["service_id"] for a in accounts
            if a["username"] == username and password_for(a["password_group"], a["service_id"]) == password]

def expected_result(account: dict | None, leaked_username: str, leaked_password: str) -> str:
    """계정 설정과 유출 정보를 대조한 기대 결과(API 결과와 독립적인 판정)."""
    if account is None or account["username"] != leaked_username:
        return config.RESULT_MISMATCH
    if password_for(account["password_group"], account["service_id"]) != leaked_password:
        return config.RESULT_MISMATCH
    return config.RESULT_MFA_BLOCKED if account["mfa_enabled"] else config.RESULT_SUCCESS


def is_valid(row: dict) -> bool:
    """오류 없이 알려진 결과를 받은 경우만 집계 대상이다."""
    return not row.get("error") and row.get("result") in config.RESULTS


def summarize(results: dict[str, list[dict]]) -> pd.DataFrame:
    """{profile: [{service_id, result}, ...]} → 결과 유형별 계정 수 비교 표(요청 오류 제외)."""
    table = {}
    for profile, rows in results.items():
        counts = {r: 0 for r in config.RESULTS}
        for row in rows:
            if is_valid(row):
                counts[row["result"]] += 1
        table[config.PROFILES.get(profile, profile)] = counts
    df = pd.DataFrame(table).reindex(config.RESULTS).fillna(0).astype(int)
    df.index.name = "결과"
    return df


def error_counts(results: dict[str, list[dict]]) -> dict[str, int]:
    return {config.PROFILES.get(p, p): sum(not is_valid(r) for r in rows) for p, rows in results.items()}


def blocked_total(df: pd.DataFrame) -> pd.Series:
    """차단 계정 수 = 비밀번호 불일치 + MFA 차단."""
    return df.loc[[config.RESULT_MISMATCH, config.RESULT_MFA_BLOCKED]].sum()


def _mfa_label(on: bool) -> str:
    return "ON" if on else "OFF"


# 피해·보호 중심 표시(§6). API 결과값은 그대로, 표시 라벨만 분리한다.
STATUS_BREACH = "계정 침해"
STATUS_BLOCKED = "로그인 시도 차단"
STATUS_CHECK = "확인 필요"

# 짧은 이유(서버가 실제 수행한 단계 기록 기준)
REASON_TEXT = {
    "success": "유출된 로그인 정보로 로그인 성공",
    "blocked_mfa": "추가 인증에서 차단",
    "blocked_id": "아이디 불일치",
    "blocked_pw": "유출 비밀번호와 다름",
    "inconsistent": "설정과 결과 불일치",
    "error": "요청 오류",
}
STATUS_LABEL = {
    "success": STATUS_BREACH, "blocked_password": STATUS_BLOCKED, "blocked_mfa": STATUS_BLOCKED,
    "inconsistent": STATUS_CHECK, "error": STATUS_CHECK,
}

# 상세창 설명 문장(시스템이 실제 확인한 범위만)
EXPLAIN_USERNAME = "유출된 아이디와 달라 차단됐습니다."
EXPLAIN_PASSWORD = "유출된 비밀번호와 달라 차단됐습니다."
EXPLAIN_MFA = "아이디·비밀번호는 일치하지만 추가 인증을 완료하지 못했습니다."
EXPLAIN_SUCCESS = "유출된 로그인 정보로 비인가 접근에 성공했습니다."
EXPLAIN_INCONSISTENT = "확인 필요: 설정과 인증 결과가 일치하지 않습니다."
EXPLAIN_ERROR = "요청 오류로 판정하지 못했습니다. (인증 실패로 해석하지 않음)"


def group_label(group: str, service_name: str) -> str:
    """비밀번호 그룹 표시. '고유'는 계정마다 다르므로 서비스명을 붙여 구분한다(평문·해시 없음)."""
    return f"고유({service_name})" if group == UNIQUE_GROUP else f"그룹 {group}"


_MFA_STEP_TEXT = {"blocked": "추가 인증 요구 · 완료 못함", "off": "사용 안 함", "skipped": "진행하지 않음"}


def build_compare(lane: dict, leaked: dict, source_service: str) -> dict:
    """유출 정보 대 대상 계정 설정 비교(설명용). 강조·설명은 서버가 실제 수행한 단계 기록만으로 결정한다.

    프런트가 설정만 보고 결과를 다시 만들지 않도록, 원인 행과 설명은 여기서 서버 steps 로 정한다.
    """
    out = lane["outcome"]
    steps = lane.get("steps") or {}
    rows = [
        {"k": "아이디", "attempt": leaked["username"], "target": lane["username"], "cause": False},
        {"k": "비밀번호",
         "attempt": group_label(leaked["password_group"], source_service),
         "target": group_label(lane["password_group"], lane["service"]), "cause": False},
        {"k": "추가 인증", "attempt": "인증 수단 없음",
         "target": ("MFA 켜짐" if lane["mfa_enabled"] else "MFA 꺼짐"), "cause": False},
    ]
    # 추가 인증 단계: 성공을 'MFA 진행'으로 오인시키지 않는다(실제 수행 단계만).
    mfa_step = "확인 불가" if out in ("error", "inconsistent") else _MFA_STEP_TEXT.get(steps.get("mfa"), "진행하지 않음")

    if out == "error":
        explain = EXPLAIN_ERROR
    elif out == "inconsistent":
        explain = EXPLAIN_INCONSISTENT
    elif out == "success":
        explain = EXPLAIN_SUCCESS
    elif out == "blocked_mfa":
        explain = EXPLAIN_MFA
        rows[2]["cause"] = True
    elif steps.get("id") == "nomatch":   # blocked_password, 아이디 단계에서 멈춤
        explain = EXPLAIN_USERNAME
        rows[0]["cause"] = True
    else:                                # blocked_password, 비밀번호 단계에서 멈춤
        explain = EXPLAIN_PASSWORD
        rows[1]["cause"] = True
    return {"rows": rows, "explain": explain, "mfa_step": mfa_step}


def changed_fields(before: dict | None, after: dict | None, value_changed: bool = False) -> list[dict]:
    """같은 서비스의 변경 전→후 설정 차이. stage 는 강조할 경로 노드.

    value_changed 는 실행 시 계산한 '전후 실제 비밀번호 값이 달라졌는가'(표시용 메타데이터, 평문 없음).
    그룹 이름이 그대로여도 값이 바뀌었으면 따로 알려 준다.
    """
    if before is None or after is None:
        return []
    changes = []
    if before["username"] != after["username"]:
        # 새 아이디는 노드에 표시되므로 표시는 짧게, 전→후 값은 detail(툴팁)로 둔다.
        changes.append({"field": "username", "stage": "service", "text": "아이디 변경",
                        "detail": f"아이디 {before['username']} → {after['username']}"})
    if before["password_group"] != after["password_group"]:
        changes.append({"field": "password_group", "stage": "password",
                        "text": f"비밀번호 {before['password_group']} → {after['password_group']}",
                        "detail": f"비밀번호 그룹 {before['password_group']} → {after['password_group']}"})
    elif value_changed:              # 그룹 이름은 같은데 실제 값이 달라진 경우
        changes.append({"field": "password_value", "stage": "password", "text": "비밀번호 값 변경",
                        "detail": f"그룹 {before['password_group']} 의 비밀번호 값이 변경 전후 다릅니다"})
    if bool(before["mfa_enabled"]) != bool(after["mfa_enabled"]):
        mfa = f"MFA {_mfa_label(before['mfa_enabled'])} → {_mfa_label(after['mfa_enabled'])}"
        changes.append({"field": "mfa_enabled", "stage": "mfa", "text": mfa, "detail": mfa})
    return changes


def target_services(accounts: list[dict], leaked_service_id: str) -> list[str]:
    """검사 대상 = 설정에 있는 서비스 중 유출 출처를 뺀 나머지(설정 순서 유지)."""
    return [a["service_id"] for a in accounts if a["service_id"] != leaked_service_id]


def _hash_meta(row: dict | None) -> dict:
    """상세창용 저장 해시 메타(평문 없음). 서버가 실제 저장·검증한 값."""
    if not row:
        return {"short": None, "full": None, "salt": None, "verified": None,
                "mfa_checked": None, "algo": None}
    return {"short": row.get("hash_short"), "full": row.get("hash_full"), "salt": row.get("salt"),
            "verified": row.get("verified"), "mfa_checked": row.get("mfa_checked"),
            "algo": row.get("algo")}


_DEFAULT_STEPS = {"try": "done", "id": "skipped", "password": "skipped", "mfa": "skipped"}


def _lane(service_id: str, account: dict | None, row: dict | None) -> dict:
    """서버 로그인 응답(row)을 그대로 lane 으로 옮긴다. 결과·단계·사유·해시는 서버 기록만 사용한다."""
    lane = {
        "service_id": service_id,
        "service": config.SERVICES.get(service_id, service_id),
        "username": account["username"] if account else "-",
        "password_group": account["password_group"] if account else "-",
        "mfa_enabled": bool(account["mfa_enabled"]) if account else False,
    }
    # 요청 오류: 성공·정상차단으로 해석하지 않는다.
    if row is None or row.get("error"):
        err = "결과 없음" if row is None else str(row.get("error"))
        return {**lane, "status": "error", "outcome": "error", "result": None, "stop_stage": "service",
                "steps": dict(_DEFAULT_STEPS), "reason": REASON_TEXT["error"],
                "status_label": STATUS_CHECK, "short": STATUS_CHECK, "hash": _hash_meta(None),
                "consistent": None, "error": err}

    result = row.get("result")
    steps = row.get("steps") or dict(_DEFAULT_STEPS)
    if result not in config.RESULTS:          # 알 수 없는 결과 → 확인 필요(성공·차단으로 세지 않음)
        return {**lane, "status": "ok", "outcome": "inconsistent", "result": result, "stop_stage": "password",
                "steps": steps, "reason": REASON_TEXT["inconsistent"],
                "status_label": STATUS_CHECK, "short": STATUS_CHECK, "hash": _hash_meta(row),
                "consistent": False, "error": None}

    if result == config.RESULT_SUCCESS:
        out, stop, reason = "success", "access", REASON_TEXT["success"]
    elif result == config.RESULT_MFA_BLOCKED:
        out, stop, reason = "blocked_mfa", "mfa", REASON_TEXT["blocked_mfa"]
    elif steps.get("id") == "nomatch":
        out, stop, reason = "blocked_password", "id", REASON_TEXT["blocked_id"]
    else:
        out, stop, reason = "blocked_password", "password", REASON_TEXT["blocked_pw"]
    return {**lane, "status": "ok", "outcome": out, "result": result, "stop_stage": stop,
            "steps": steps, "reason": reason, "status_label": STATUS_LABEL[out],
            "short": STATUS_LABEL[out], "hash": _hash_meta(row), "consistent": True, "error": None}


def summarize_lanes(lanes: list[dict]) -> dict:
    """검사 대상별 결과 집계(outcome 기준). 성공·차단은 API 결과로만 세고, 오류·확인 필요는 따로 센다."""
    def c(name):
        return sum(ln["outcome"] == name for ln in lanes)
    by_password, by_mfa = c("blocked_password"), c("blocked_mfa")
    return {
        "total": len(lanes),
        "success": c("success"),
        "blocked": by_password + by_mfa,
        "blocked_password": by_password,
        "blocked_mfa": by_mfa,
        "errors": c("error"),
        "inconsistent": c("inconsistent"),
    }


def _source_view(account: dict | None) -> dict | None:
    if account is None:
        return None
    return {"username": account["username"], "password_group": account["password_group"],
            "mfa_enabled": bool(account["mfa_enabled"])}


def build_animation_payload(snapshot: dict) -> dict:
    """실행 스냅샷 → 애니메이션 데이터. 평문 비밀번호는 포함하지 않는다.

    snapshot = {
        "run_id": 실행 구분 값(선택),
        "leaked": {"service_id", "username", "password_group"},
        "accounts": {"before": [...], "after": [...]},   # 실행 당시 설정
        "results": {"before": [...], "after": [...]},    # 검사 대상의 API 응답(또는 오류 행)
    }
    유출 출처 계정은 '로그인 정보가 유출된 계정'으로 따로 두고 검사 대상에서 뺀다.
    """
    leaked = snapshot["leaked"]
    source_id = leaked["service_id"]
    by_service = {p: {a["service_id"]: a for a in accs} for p, accs in snapshot["accounts"].items()}

    # 화면 배치 순서: 변경 전 설정 순서로 고정해 전후 비교에서 서비스 위치가 바뀌지 않게 한다.
    order = target_services(snapshot["accounts"]["before"], source_id)
    order += [s for s in target_services(snapshot["accounts"]["after"], source_id) if s not in order]

    value_changed = snapshot.get("value_changed") or {}
    profiles = {}
    for profile, label in config.PROFILES.items():
        rows = {r["service_id"]: r for r in snapshot["results"].get(profile, [])}
        lanes = []
        for service_id in order:
            lane = _lane(service_id, by_service[profile].get(service_id), rows.get(service_id))
            lane["changes"] = (changed_fields(by_service["before"].get(service_id),
                                              by_service["after"].get(service_id),
                                              bool(value_changed.get(service_id)))
                               if profile == "after" else [])
            lane["compare"] = build_compare(lane, leaked, config.SERVICES.get(source_id, source_id))
            lanes.append(lane)
        profiles[profile] = {
            "label": label,
            "lanes": lanes,
            "summary": summarize_lanes(lanes),
            "sentence": result_sentence(label, lanes),
        }
    source_before = by_service["before"].get(source_id)
    source_after = by_service["after"].get(source_id)
    return {
        "run_id": snapshot.get("run_id"),
        "order": order,
        "leaked": {
            "service_id": source_id,
            "service": config.SERVICES.get(source_id, source_id),
            "username": leaked["username"],
            "password_group": leaked["password_group"],
            "password_label": f"그룹 {leaked['password_group']} 비밀번호",
        },
        "source": {
            "before": _source_view(source_before),
            "after": _source_view(source_after),
            "after_changes": changed_fields(source_before, source_after),
            "note": source_note(config.SERVICES.get(source_id, source_id), source_before, source_after),
        },
        "profiles": profiles,
        "result_success": config.RESULT_SUCCESS,
        "compare_sentence": compare_sentence(profiles["before"]["summary"], profiles["after"]["summary"]),
    }


def source_note(service: str, before: dict | None, after: dict | None) -> str:
    """변경 후 설정에서 출처 계정이 어떻게 바뀌었는지(설정 비교이며 로그인 검사 결과가 아니다)."""
    changes = changed_fields(before, after)
    if not changes:
        return f"변경 후 설정에서도 {service} 계정의 설정은 그대로입니다(검사 대상 아님)."
    texts = ", ".join(c.get("detail") or c["text"] for c in changes)
    return f"변경 후 설정에서 바뀐 {service} 계정 설정: {texts} (검사 대상 아님)."


def result_sentence(label: str, lanes: list[dict]) -> str:
    """재생 완료 후 보여줄 한 문장. API 결과로만 센다."""
    s = summarize_lanes(lanes)
    success, by_password, by_mfa = s["success"], s["blocked_password"], s["blocked_mfa"]

    parts = []
    if success:
        parts.append(f"{success}개에서 비인가 접근이 성공했고" if (by_password or by_mfa)
                     else f"{success}개에서 비인가 접근이 성공했습니다")
    blocked = []
    if by_password:
        blocked.append(f"{by_password}개는 아이디·비밀번호 확인 단계에서")
    if by_mfa:
        blocked.append(f"{by_mfa}개는 MFA 단계에서")
    if blocked:
        parts.append(", ".join(blocked) + " 차단되었습니다")
    if not parts:
        parts.append("판정된 서비스가 없습니다")
    sentence = f"{label}: 검사 대상 {s['total']}개 서비스 중 " + " ".join(parts)
    notes = []
    if s["inconsistent"]:
        notes.append(f"{s['inconsistent']}개는 설정과 인증 결과가 일치하지 않습니다")
    if s["errors"]:
        notes.append(f"{s['errors']}개는 요청 오류로 판정하지 못했습니다")
    return sentence + (" (" + ", ".join(notes) + ")." if notes else ".")


def compare_sentence(before: dict, after: dict) -> str:
    b, a = before["success"], after["success"]
    if a < b:
        change = f"변경 전 {b}개에서 변경 후 {a}개로 줄었습니다"
    elif a > b:
        change = f"변경 전 {b}개에서 변경 후 {a}개로 늘었습니다"
    else:
        change = f"변경 전후 모두 {a}개로 같습니다"
    errors = before["errors"] + after["errors"]
    note = f" (요청 오류 {errors}건은 제외)" if errors else ""
    return f"같은 유출 정보로 시도했을 때 비인가 접근에 성공한 서비스는 {change}{note}."

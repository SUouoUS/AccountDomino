"""유출 자격증명 구성, 설정 대조 판정, 결과 집계, 애니메이션 데이터 생성(순수 함수)."""
from __future__ import annotations

import pandas as pd

from . import config
from .scenarios import password_for

# 멈춤 단계는 API 결과만으로 결정한다.
STOP_STAGE = {
    config.RESULT_MISMATCH: "password",
    config.RESULT_MFA_BLOCKED: "mfa",
    config.RESULT_SUCCESS: "access",
}

# 차단 지점에 붙는 짧은 이유(시스템이 실제 확인한 범위만)
REASON_USERNAME = "유출된 아이디와 다름"
REASON_PASSWORD = "유출된 비밀번호와 다름"
REASON_NO_ACCOUNT = "해당 서비스 계정 없음"
REASON_MFA = "추가 인증 수단 없음"
REASON_SUCCESS = "유출 정보만으로 로그인됨"
REASON_INCONSISTENT = "설정과 인증 결과가 일치하지 않음"
REASON_ERROR = "인증 판정 전 요청 실패"


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


def _reason(account: dict | None, result: str, leaked_username: str) -> str:
    if result == config.RESULT_SUCCESS:
        return REASON_SUCCESS
    if result == config.RESULT_MFA_BLOCKED:
        return REASON_MFA
    if account is None:
        return REASON_NO_ACCOUNT
    if account["username"] != leaked_username:
        return REASON_USERNAME
    return REASON_PASSWORD


def _mfa_label(on: bool) -> str:
    return "켜짐" if on else "꺼짐"


def changed_fields(before: dict | None, after: dict | None) -> list[dict]:
    """같은 서비스의 변경 전→후 설정 차이. stage 는 강조할 경로 노드."""
    if before is None or after is None:
        return []
    changes = []
    if before["username"] != after["username"]:
        # 새 아이디는 노드에 표시되므로 표시는 짧게, 전→후 값은 detail(툴팁)로 둔다.
        changes.append({"field": "username", "stage": "service", "text": "아이디",
                        "detail": f"아이디 {before['username']} → {after['username']}"})
    if before["password_group"] != after["password_group"]:
        changes.append({"field": "password_group", "stage": "password",
                        "text": f"비밀번호 그룹 {before['password_group']}→{after['password_group']}"})
    if bool(before["mfa_enabled"]) != bool(after["mfa_enabled"]):
        changes.append({"field": "mfa_enabled", "stage": "mfa",
                        "text": f"MFA {_mfa_label(before['mfa_enabled'])}→{_mfa_label(after['mfa_enabled'])}"})
    return changes


def _lane(service_id: str, account: dict | None, row: dict | None,
          leaked_username: str, leaked_password: str) -> dict:
    lane = {
        "service_id": service_id,
        "service": config.SERVICES[service_id],
        "username": account["username"] if account else "-",
        "password_group": account["password_group"] if account else "-",
        "mfa_enabled": bool(account["mfa_enabled"]) if account else False,
    }
    if row is None or not is_valid(row):
        if row is None:
            error = "결과 없음"
        elif row.get("error"):
            error = str(row["error"])
        else:
            error = f"알 수 없는 결과: {row.get('result')}"
        return {**lane, "status": "error", "result": None, "stop_stage": "service",
                "consistent": None, "reason": REASON_ERROR, "error": error}

    result = row["result"]
    consistent = expected_result(account, leaked_username, leaked_password) == result
    return {**lane, "status": "ok", "result": result, "stop_stage": STOP_STAGE[result],
            "consistent": consistent,
            "reason": _reason(account, result, leaked_username) if consistent else REASON_INCONSISTENT,
            "error": None}


def build_animation_payload(snapshot: dict) -> dict:
    """실행 스냅샷 → 애니메이션 데이터. 평문 비밀번호는 포함하지 않는다.

    snapshot = {
        "leaked": {"service_id", "username", "password_group"},
        "accounts": {"before": [...], "after": [...]},   # 실행 당시 설정
        "results": {"before": [...], "after": [...]},    # API 응답(또는 오류 행)
    }
    """
    leaked = snapshot["leaked"]
    leaked_password = password_for(leaked["password_group"], leaked["service_id"])
    by_service = {p: {a["service_id"]: a for a in accs} for p, accs in snapshot["accounts"].items()}

    profiles = {}
    for profile, label in config.PROFILES.items():
        rows = {r["service_id"]: r for r in snapshot["results"].get(profile, [])}
        lanes = []
        for service_id in config.SERVICES:
            lane = _lane(service_id, by_service[profile].get(service_id), rows.get(service_id),
                         leaked["username"], leaked_password)
            lane["changes"] = (changed_fields(by_service["before"].get(service_id),
                                              by_service["after"].get(service_id))
                               if profile == "after" else [])
            lanes.append(lane)
        ok = [ln for ln in lanes if ln["status"] == "ok"]
        profiles[profile] = {
            "label": label,
            "lanes": lanes,
            "summary": {
                "success": sum(ln["result"] == config.RESULT_SUCCESS for ln in ok),
                "blocked": sum(ln["result"] != config.RESULT_SUCCESS for ln in ok),
                "errors": len(lanes) - len(ok),
            },
            "sentence": result_sentence(label, lanes),
        }
    return {
        "leaked": {
            "service": config.SERVICES[leaked["service_id"]],
            "username": leaked["username"],
            "password_label": f"그룹 {leaked['password_group']} 비밀번호",
        },
        "profiles": profiles,
        "compare_sentence": compare_sentence(profiles["before"]["summary"], profiles["after"]["summary"]),
    }


def result_sentence(label: str, lanes: list[dict]) -> str:
    """재생 완료 후 보여줄 한 문장. API 결과로만 센다."""
    total = len(lanes)
    ok = [ln for ln in lanes if ln["status"] == "ok"]
    success = sum(ln["result"] == config.RESULT_SUCCESS for ln in ok)
    by_password = sum(ln["result"] == config.RESULT_MISMATCH for ln in ok)
    by_mfa = sum(ln["result"] == config.RESULT_MFA_BLOCKED for ln in ok)
    inconsistent = sum(ln["consistent"] is False for ln in ok)
    errors = total - len(ok)

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
    sentence = f"{label}: {total}개 서비스 중 " + " ".join(parts)
    notes = []
    if inconsistent:
        notes.append(f"{inconsistent}개는 설정과 인증 결과가 일치하지 않습니다")
    if errors:
        notes.append(f"{errors}개는 요청 오류로 판정하지 못했습니다")
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

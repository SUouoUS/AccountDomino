"""핵심 모의 인증 로직: 계정 저장, 로그인 판정, 로그 기록."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import config
from .scenarios import password_for
from .security import algo_info, hash_password, verify_password


class UnknownServiceError(ValueError):
    pass


@dataclass
class AccountSetting:
    service_id: str
    username: str
    password_group: str
    mfa_enabled: bool
    password: str | None = None   # 실습용 평문(있으면 이 값으로 해시). 없으면 그룹 기본값.


def ensure_service(service_id: str) -> None:
    if service_id not in config.SERVICES:
        raise UnknownServiceError(service_id)


def save_accounts(conn: sqlite3.Connection, profile: str, settings: list[AccountSetting]) -> None:
    """profile 의 계정 설정을 교체한다. 입력한 실습용 평문(또는 그룹 기본값)을 해시만 저장한다(평문 미저장)."""
    if profile not in config.PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    for s in settings:
        ensure_service(s.service_id)
    with conn:
        conn.execute("DELETE FROM accounts WHERE profile = ?", (profile,))
        for s in settings:
            plain = s.password if s.password is not None else password_for(s.password_group, s.service_id)
            pw_hash, salt = hash_password(plain)
            conn.execute(
                "INSERT INTO accounts(profile, service_id, username, password_group,"
                " password_hash, salt, mfa_enabled) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (profile, s.service_id, s.username, s.password_group, pw_hash, salt, int(s.mfa_enabled)),
            )


def list_accounts(conn: sqlite3.Connection, profile: str) -> list[dict]:
    rows = conn.execute(
        "SELECT service_id, username, password_group, mfa_enabled FROM accounts"
        " WHERE profile = ? ORDER BY id",
        (profile,),
    ).fetchall()
    return [{**dict(r), "mfa_enabled": bool(r["mfa_enabled"])} for r in rows]


def authenticate_steps(
    conn: sqlite3.Connection, profile: str, service_id: str, username: str, password: str
) -> dict:
    """실제로 수행한 인증 단계만 구조화해 기록한다(프런트가 설정만으로 결과를 만들지 않도록).

    서비스별 계정 하나(UNIQUE(profile, service_id))를 기준으로:
    - 아이디가 저장된 아이디와 다르면 아이디 단계에서 멈추고 비밀번호·MFA 는 수행하지 않음.
    - 아이디가 같으면 저장된 해시·salt 로 실제 검증. 실패면 MFA 미수행.
    - 비밀번호가 맞고 MFA 가 켜져 있으면 추가 인증 미완료로 차단, 꺼져 있으면 성공.
    평문은 포함하지 않고 저장 해시·salt·검증 결과만 반환한다(교육용 표시).
    """
    ensure_service(service_id)
    row = conn.execute(
        "SELECT password_hash, salt, username, mfa_enabled FROM accounts"
        " WHERE profile = ? AND service_id = ?",
        (profile, service_id),
    ).fetchone()
    target_hash = row["password_hash"] if row else None
    target_salt = row["salt"] if row else None
    mfa_enabled = bool(row["mfa_enabled"]) if row else False
    id_match = bool(row) and row["username"] == username

    steps = {"try": "done", "id": "match" if id_match else "nomatch",
             "password": "skipped", "mfa": "skipped"}
    verified = False
    if not id_match:
        result = config.RESULT_MISMATCH
    else:
        verified = verify_password(password, row["password_hash"], row["salt"])
        if not verified:
            steps["password"] = "nomatch"
            result = config.RESULT_MISMATCH
        else:
            steps["password"] = "match"
            if mfa_enabled:
                steps["mfa"] = "blocked"          # 추가 인증 요구 · 완료 못함
                result = config.RESULT_MFA_BLOCKED
            else:
                steps["mfa"] = "off"              # 추가 인증 사용 안 함
                result = config.RESULT_SUCCESS
    return {"result": result, "steps": steps, "verified": verified,
            "target_hash": target_hash, "target_salt": target_salt, "mfa_enabled": mfa_enabled,
            "algo": algo_info()}


def authenticate(
    conn: sqlite3.Connection, profile: str, service_id: str, username: str, password: str
) -> str:
    """모의 로그인 결과 문자열. 실제 단계 기록(authenticate_steps)의 결과만 돌려준다."""
    return authenticate_steps(conn, profile, service_id, username, password)["result"]


def create_run(
    conn: sqlite3.Connection, profile: str, leaked_service_id: str, leaked_username: str,
    scenario: str | None = None,
) -> int:
    ensure_service(leaked_service_id)
    with conn:
        cur = conn.execute(
            "INSERT INTO runs(scenario, profile, leaked_service_id, leaked_username) VALUES (?, ?, ?, ?)",
            (scenario, profile, leaked_service_id, leaked_username),
        )
    return int(cur.lastrowid)


def login_and_log(
    conn: sqlite3.Connection, profile: str, service_id: str, username: str, password: str,
    run_id: int | None = None,
) -> dict:
    """실제 단계 기록을 만들고 결과만 로그에 남긴다(로그·반환에 평문 없음)."""
    rec = authenticate_steps(conn, profile, service_id, username, password)
    with conn:
        conn.execute(
            "INSERT INTO login_logs(run_id, profile, service_id, username, result) VALUES (?, ?, ?, ?, ?)",
            (run_id, profile, service_id, username, rec["result"]),
        )
    return rec


def get_logs(conn: sqlite3.Connection, run_id: int | None = None, limit: int = 100) -> list[dict]:
    if run_id is not None:
        rows = conn.execute(
            "SELECT * FROM login_logs WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM login_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

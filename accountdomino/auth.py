"""핵심 모의 인증 로직: 계정 저장, 로그인 판정, 로그 기록."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import config
from .scenarios import password_for
from .security import hash_password, verify_password


class UnknownServiceError(ValueError):
    pass


@dataclass
class AccountSetting:
    service_id: str
    username: str
    password_group: str
    mfa_enabled: bool


def ensure_service(service_id: str) -> None:
    if service_id not in config.SERVICES:
        raise UnknownServiceError(service_id)


def save_accounts(conn: sqlite3.Connection, profile: str, settings: list[AccountSetting]) -> None:
    """profile 의 계정 설정을 교체한다. 비밀번호는 그룹에서 유도한 뒤 해시만 저장한다."""
    if profile not in config.PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    for s in settings:
        ensure_service(s.service_id)
    with conn:
        conn.execute("DELETE FROM accounts WHERE profile = ?", (profile,))
        for s in settings:
            pw_hash, salt = hash_password(password_for(s.password_group, s.service_id))
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


def authenticate(
    conn: sqlite3.Connection, profile: str, service_id: str, username: str, password: str
) -> str:
    """모의 로그인 결과를 반환한다.

    - 아이디가 없거나 해시가 다르면 '비밀번호 불일치' (계정 존재 여부를 노출하지 않음)
    - 해시가 맞아도 MFA 가 켜져 있으면 공격자는 2차 인증을 통과하지 못해 'MFA 차단'
    - 그 외에는 '접근 성공'
    """
    ensure_service(service_id)
    row = conn.execute(
        "SELECT password_hash, salt, mfa_enabled FROM accounts"
        " WHERE profile = ? AND service_id = ? AND username = ?",
        (profile, service_id, username),
    ).fetchone()
    if row is None or not verify_password(password, row["password_hash"], row["salt"]):
        return config.RESULT_MISMATCH
    if row["mfa_enabled"]:
        return config.RESULT_MFA_BLOCKED
    return config.RESULT_SUCCESS


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
) -> str:
    result = authenticate(conn, profile, service_id, username, password)
    with conn:
        conn.execute(
            "INSERT INTO login_logs(run_id, profile, service_id, username, result) VALUES (?, ?, ?, ?, ?)",
            (run_id, profile, service_id, username, result),
        )
    return result


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

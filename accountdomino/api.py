"""모의 인증 서버. 하나의 로컬 서버가 service_id 로 메일·쇼핑·커뮤니티·학교 등 가상 서비스를 구분한다."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from . import auth, config, db
from .scenarios import PASSWORD_GROUPS, SCENARIOS, build_scenario

Profile = Literal["before", "after"]

app = FastAPI(title="AccountDomino 모의 인증 서버", version="0.1.0")


def get_conn() -> Iterator:
    conn = db.connect()
    db.init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


class AccountIn(BaseModel):
    service_id: str
    username: str
    password_group: str
    mfa_enabled: bool = False
    password: str | None = None   # 실습용 평문(있으면 이 값으로 해시). 로컬 전용, 저장 안 함.


class LoginIn(BaseModel):
    profile: Profile
    username: str
    password: str
    run_id: int | None = None


class RunIn(BaseModel):
    profile: Profile
    leaked_service_id: str
    leaked_username: str
    scenario: str | None = None


def _check_service(service_id: str) -> None:
    if service_id not in config.SERVICES:
        raise HTTPException(404, f"알 수 없는 service_id: {service_id}")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/services")
def services() -> list[dict]:
    return [{"service_id": k, "name": v} for k, v in config.SERVICES.items()]


@app.get("/scenarios")
def scenarios() -> list[dict]:
    return [
        {"id": k, "title": v["title"], "description": v["description"],
         "leaked_service_id": v["leaked_service_id"]}
        for k, v in SCENARIOS.items()
    ]


@app.post("/scenarios/{scenario_id}/load")
def load_scenario(
    scenario_id: str,
    count: int = Query(config.DEFAULT_ACCOUNT_COUNT, ge=config.MIN_ACCOUNT_COUNT, le=config.MAX_ACCOUNT_COUNT),
    conn=Depends(get_conn),
) -> dict:
    sc = SCENARIOS.get(scenario_id)
    if sc is None:
        raise HTTPException(404, f"알 수 없는 시나리오: {scenario_id}")
    profiles = build_scenario(scenario_id, count)
    for profile in config.PROFILES:
        auth.save_accounts(conn, profile, [auth.AccountSetting(**a) for a in profiles[profile]])
    return {"loaded": scenario_id, "count": count, "leaked_service_id": sc["leaked_service_id"]}


@app.get("/profiles/{profile}/accounts")
def get_accounts(profile: Profile, conn=Depends(get_conn)) -> list[dict]:
    return auth.list_accounts(conn, profile)


@app.put("/profiles/{profile}/accounts")
def put_accounts(profile: Profile, accounts: list[AccountIn], conn=Depends(get_conn)) -> dict:
    for a in accounts:
        _check_service(a.service_id)
        if a.password_group not in PASSWORD_GROUPS:
            raise HTTPException(422, f"알 수 없는 비밀번호 그룹: {a.password_group}")
        if not a.username.strip():
            raise HTTPException(422, "아이디는 비워둘 수 없습니다.")
    auth.save_accounts(conn, profile, [auth.AccountSetting(**a.model_dump()) for a in accounts])
    return {"saved": len(accounts)}


@app.post("/runs")
def create_run(body: RunIn, conn=Depends(get_conn)) -> dict:
    _check_service(body.leaked_service_id)
    run_id = auth.create_run(conn, body.profile, body.leaked_service_id, body.leaked_username, body.scenario)
    return {"run_id": run_id}


@app.post("/services/{service_id}/login")
def login(service_id: str, body: LoginIn, conn=Depends(get_conn)) -> dict:
    _check_service(service_id)
    rec = auth.login_and_log(conn, body.profile, service_id, body.username, body.password, body.run_id)
    full = rec["target_hash"]
    return {
        "service_id": service_id, "username": body.username, "result": rec["result"],
        "steps": rec["steps"], "verified": rec["verified"], "mfa_enabled": rec["mfa_enabled"],
        "mfa_checked": rec["steps"]["mfa"] in ("blocked", "off"),
        "hash_full": full, "hash_short": (full[:12] if full else None), "salt": rec["target_salt"],
        "algo": rec["algo"],
    }


@app.get("/runs/{run_id}/logs")
def run_logs(run_id: int, conn=Depends(get_conn)) -> list[dict]:
    return auth.get_logs(conn, run_id=run_id)


@app.get("/logs")
def logs(limit: int = 100, conn=Depends(get_conn)) -> list[dict]:
    return auth.get_logs(conn, limit=limit)

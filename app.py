"""AccountDomino Streamlit 화면: ① 계정 설정 → ② 시뮬레이션. 로컬 모의 인증 서버에만 요청한다."""
from __future__ import annotations

import httpx
import pandas as pd
import streamlit as st

from accountdomino import animation, config
from accountdomino.client import DominoClient
from accountdomino.scenarios import PASSWORD_GROUPS
from accountdomino.simulation import build_animation_payload, leaked_credential, shared_credential_services

st.set_page_config(page_title="AccountDomino", layout="wide", initial_sidebar_state="collapsed")

SETTINGS, SIMULATION = "settings", "simulation"
DEFAULT_ACCOUNT = {"username": "student01", "password_group": "A", "mfa_enabled": False}


@st.cache_resource
def get_client() -> DominoClient:
    return DominoClient()


client = get_client()
state = st.session_state

if not client.health():
    st.title("AccountDomino")
    st.error(f"모의 인증 서버({config.API_BASE_URL})에 연결할 수 없습니다. README 의 실행 방법을 확인하세요.")
    st.stop()


def accounts_from_api(profile: str) -> list[dict]:
    by_service = {a["service_id"]: a for a in client.accounts(profile)}
    return [{"service_id": sid, **{k: by_service.get(sid, DEFAULT_ACCOUNT)[k] for k in DEFAULT_ACCOUNT}}
            for sid in config.SERVICES]


# 화면을 오가도 유지되는 입력값(위젯 상태와 별도로 보관)
if "base" not in state:
    state.base = {p: accounts_from_api(p) for p in config.PROFILES}
state.setdefault("page", SETTINGS)
state.setdefault("editor_version", 0)
state.setdefault("leaked_choice", "community")
state.setdefault("scenario_choice", "s1")
state.setdefault("scenario_id", None)
state.setdefault("last_run", None)

COLUMN_CONFIG = {
    "서비스": st.column_config.TextColumn(disabled=True),
    "아이디": st.column_config.TextColumn(required=True),
    "비밀번호 그룹": st.column_config.SelectboxColumn(options=PASSWORD_GROUPS, required=True),
    "MFA": st.column_config.CheckboxColumn(),
}


def steps_nav(current: str) -> None:
    first = "**① 계정 설정**" if current == SETTINGS else "① 계정 설정"
    second = "**② 시뮬레이션**" if current == SIMULATION else "② 시뮬레이션"
    st.markdown(f"{first} &nbsp;→&nbsp; {second}")


def to_frame(accounts: list[dict]) -> pd.DataFrame:
    rows = [{"서비스": config.SERVICES[a["service_id"]], "아이디": a["username"],
             "비밀번호 그룹": a["password_group"], "MFA": bool(a["mfa_enabled"])} for a in accounts]
    return pd.DataFrame(rows, index=[a["service_id"] for a in accounts])


def to_payload(df: pd.DataFrame) -> list[dict]:
    return [{"service_id": service_id, "username": str(r["아이디"] or "").strip(),
             "password_group": r["비밀번호 그룹"], "mfa_enabled": bool(r["MFA"])}
            for service_id, r in df.iterrows()]


def run_simulation(payloads: dict[str, list[dict]], leaked_service: str) -> dict:
    """두 설정에 같은 유출 정보(변경 전 출처 계정)로 모의 로그인하고, 실행 당시 설정·결과를 한 묶음으로 반환한다."""
    source = next(a for a in payloads["before"] if a["service_id"] == leaked_service)
    leaked = {"service_id": leaked_service, "username": source["username"], "password_group": source["password_group"]}
    username, password = leaked_credential(payloads["before"], leaked_service)
    snapshot = {"leaked": leaked, "accounts": payloads, "results": {}, "run_ids": {}}
    for profile in config.PROFILES:
        client.save_accounts(profile, payloads[profile])
        run_id = client.create_run(profile, leaked_service, username, state.scenario_id)
        snapshot["run_ids"][profile] = run_id
        rows = []
        for service_id in config.SERVICES:
            try:
                rows.append(client.login(service_id, profile, username, password, run_id))
            except (httpx.HTTPError, ValueError) as exc:
                # 오류를 불일치·차단으로 바꾸지 않고 그대로 기록한다.
                rows.append({"service_id": service_id, "result": None, "error": type(exc).__name__})
        snapshot["results"][profile] = rows
    return snapshot


def settings_page() -> None:
    steps_nav(SETTINGS)
    st.title("AccountDomino")
    st.write("한 서비스에서 유출된 로그인 정보가 다른 계정에도 통하는지, 비밀번호 분리와 MFA가 접근을 어디서 막는지 "
             "확인하는 시뮬레이션입니다. 모든 계정은 가상 데이터이며 이 컴퓨터의 모의 인증 서버에만 요청합니다.")

    col_steps, col_terms = st.columns(2, gap="large")
    with col_steps:
        st.subheader("시작 안내")
        st.markdown("1. 기본 시나리오를 불러오거나 계정을 직접 설정합니다.\n"
                    "2. 유출 출처를 고르고 유출 정보 미리보기를 확인합니다.\n"
                    "3. **시뮬레이션 시작**을 눌러 변경 전·후 결과를 봅니다.")
    with col_terms:
        st.subheader("용어")
        st.markdown("- **유출 출처**: 아이디·비밀번호가 유출된 원래 계정\n"
                    "- **비밀번호 그룹**: 같은 비밀번호를 쓰는 가상 계정 구분. 글자가 같으면 같은 비밀번호, "
                    "‘고유’는 그 계정만의 비밀번호\n"
                    "- **MFA**: 비밀번호를 맞힌 뒤 추가로 요구되는 인증")

    st.header("시나리오")
    scenarios = {s["id"]: s for s in client.scenarios()}
    if "scenario_widget" not in state:
        state.scenario_widget = state.scenario_choice
    col_sel, col_btn = st.columns([4, 1], vertical_alignment="bottom")
    with col_sel:
        sid = st.selectbox("기본 시나리오", list(scenarios), format_func=lambda k: scenarios[k]["title"],
                           key="scenario_widget")
    state.scenario_choice = sid
    with col_btn:
        if st.button("시나리오 불러오기", width="stretch"):
            client.load_scenario(sid)
            state.base = {p: accounts_from_api(p) for p in config.PROFILES}
            state.leaked_choice = scenarios[sid]["leaked_service_id"]
            state.pop("leaked_widget", None)
            state.scenario_id = sid
            state.editor_version += 1
            st.rerun()
    st.write(scenarios[sid]["description"])

    st.header("계정 설정")
    edited = {}
    cols = st.columns(2, gap="large")
    for col, (profile, label) in zip(cols, config.PROFILES.items()):
        with col:
            st.subheader(label)
            edited[profile] = st.data_editor(
                to_frame(state.base[profile]), column_config=COLUMN_CONFIG, hide_index=True,
                width="stretch", key=f"editor_{profile}_{state.editor_version}",
            )
    payloads = {p: to_payload(df) for p, df in edited.items()}

    st.header("유출 출처")
    if "leaked_widget" not in state:
        state.leaked_widget = state.leaked_choice
    leaked_service = st.selectbox("아이디·비밀번호가 유출된 원래 계정", list(config.SERVICES),
                                  format_func=config.SERVICES.get, key="leaked_widget")
    state.leaked_choice = leaked_service
    leak_preview(payloads["before"], leaked_service)

    if st.button("시뮬레이션 시작", type="primary"):
        state.base = payloads                       # 돌아왔을 때 입력값 유지
        state.editor_version += 1
        if any(not a["username"] for p in payloads.values() for a in p):
            st.error("아이디를 모두 입력하세요.")
            return
        try:
            with st.spinner("모의 로그인 중..."):
                state.last_run = run_simulation(payloads, leaked_service)
        except httpx.HTTPError as exc:
            st.error(f"모의 인증 서버 요청에 실패했습니다: {exc}")
            return
        state.page = SIMULATION
        st.rerun()


def leak_preview(before: list[dict], leaked_service: str) -> None:
    """선택한 출처 계정의 변경 전 아이디·비밀번호 그룹 = 유출 정보. 같은 정보를 쓰는 계정은 설정 비교로 보여 준다."""
    source = next(a for a in before if a["service_id"] == leaked_service)
    shared = shared_credential_services(before, leaked_service)
    with st.container(border=True):
        st.markdown(f"**유출 정보 미리보기** · 아이디 **{source['username'] or '미입력'}**, "
                    f"비밀번호 그룹 **{source['password_group']}** "
                    f"({config.SERVICES[leaked_service]} 계정의 변경 전 설정). 변경 전·후 모두 이 정보로 로그인합니다.")
        if len(shared) == len(before):
            st.write("모든 계정이 같은 아이디·비밀번호를 쓰고 있어, 유출 출처를 바꿔도 로그인 결과가 같을 수 있습니다.")
        elif len(shared) <= 1:
            st.write("변경 전 설정에서 이 아이디·비밀번호를 쓰는 계정은 출처 계정뿐입니다.")
        else:
            others = ", ".join(config.SERVICES[s] for s in shared if s != leaked_service)
            st.write(f"변경 전 설정에서 같은 아이디·비밀번호를 쓰는 다른 계정: {others}. "
                     "출처를 바꾸면 유출 정보와 결과가 달라질 수 있습니다.")


def simulation_page() -> None:
    run = state.last_run
    if run is None:
        state.page = SETTINGS
        st.rerun()
    col_nav, col_back = st.columns([5, 1], vertical_alignment="center")
    with col_nav:
        steps_nav(SIMULATION)
    with col_back:
        if st.button("설정으로 돌아가기", width="stretch"):
            state.page = SETTINGS
            st.rerun()
    st.title("로그인 경로 시뮬레이션")
    # 자체 생성 HTML(사용자 입력은 JSON 으로만 주입, 화면에는 textContent 로 출력)
    st.iframe(animation.render(build_animation_payload(run)), height=780)


if state.page == SIMULATION:
    simulation_page()
else:
    settings_page()

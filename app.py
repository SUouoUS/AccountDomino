"""AccountDomino Streamlit 화면: 소개 → 시나리오 → 계정 설정 → 유출 출처 → 시뮬레이션. 로컬 모의 인증 서버에만 요청한다."""
from __future__ import annotations

import copy
import hashlib

import httpx
import pandas as pd
import streamlit as st

from accountdomino import animation, config
from accountdomino.client import DominoClient
from accountdomino.scenarios import (
    GROUP_PASSWORDS, PASSWORD_GROUP_HELP, PASSWORD_GROUPS, SCENARIOS, UNIQUE_GROUP,
    build_scenario, change_summary, resize_accounts, resolve_password,
)
from accountdomino.simulation import (
    build_animation_payload, changed_fields, target_services,
)

st.set_page_config(page_title="AccountDomino", layout="wide", initial_sidebar_state="collapsed")

INTRO, SCENARIO, ACCOUNTS, LEAK, SIMULATION = "intro", "scenario", "accounts", "leak", "simulation"
PAGES = {
    INTRO: ("프로젝트 소개", ""),
    SCENARIO: ("시나리오 선택", "비교할 보안 설정과 계정 수를 선택하세요."),
    ACCOUNTS: ("계정 설정", "같은 그룹은 같은 비밀번호를 씁니다. ‘고유’는 계정마다 다른 비밀번호, MFA는 2차 인증입니다."),
    LEAK: ("유출 출처 선택", "어떤 서비스의 로그인 정보가 유출됐다고 가정할지 선택하세요. 선택한 계정의 아이디·비밀번호로 다른 서비스에 로그인을 시도합니다."),
}
SETUP_STEPS = [SCENARIO, ACCOUNTS, LEAK]
ROW_HEIGHT = 40
COL_SERVICE, COL_USER, COL_GROUP, COL_MFA = "서비스", "아이디", "그룹", "MFA"
FIELD_OF = {COL_USER: "username", COL_GROUP: "password_group", COL_MFA: "mfa_enabled"}
CHANGE_TAG = {"username": "아이디", "password_group": "비밀번호", "mfa_enabled": "MFA"}

CSS = """
<style>
/* 콘텐츠는 가로 중앙의 넓은 영역 안에서 왼쪽 정렬, 상단 여백은 일정하게 */
[data-testid="stMainBlockContainer"] {
  max-width: var(--pw, 1000px) !important; margin-inline: auto;
  padding-top: 3rem; padding-bottom: 2.5rem; padding-inline: 1rem;
}
[data-testid="stMarkdownContainer"] p.brand { font-size: 42px; font-weight: 700; margin: 0 0 6px; line-height: 1.2; color: #F4F7FB; }
[data-testid="stMarkdownContainer"] p.step { color: #60A5FA; font-size: 18px; font-weight: 700; margin: 0 0 2px; letter-spacing: 0.3px; }
[data-testid="stMarkdownContainer"] p.ptitle { font-size: 33px; font-weight: 700; color: #F4F7FB; margin: 4px 0 18px; }
[data-testid="stMarkdownContainer"] p.lead { font-size: 20px; color: #C0CDDD; margin: 0 0 16px; line-height: 1.7; word-break: keep-all; max-width: 62ch; }
[data-testid="stMarkdownContainer"] .intro-title { font-size: 33px; font-weight: 700; color: #F4F7FB; margin: 6px 0 16px; word-break: keep-all; }
[data-testid="stMarkdownContainer"] .intro-body p { font-size: 21px; color: #DCE5F0; margin: 0 0 16px; line-height: 1.75; word-break: keep-all; }
[data-testid="stMarkdownContainer"] p.foot-note { color: #C0CDDD; font-size: 17px; margin-top: 22px; word-break: keep-all; }
[data-testid="stMarkdownContainer"] p.summary { font-size: 20px; margin: 6px 0 4px; word-break: keep-all; }
[data-testid="stMarkdownContainer"] p.summary .mono { font-family: "Consolas","D2Coding",monospace; color: #60A5FA; font-weight: 700; overflow-wrap: anywhere; }
[data-testid="stMarkdownContainer"] p.change { font-size: 19px; color: #60A5FA; font-weight: 700; margin: 10px 0; word-break: keep-all; }
[data-testid="stMarkdownContainer"] p.prof-title { font-size: 22px; font-weight: 700; color: #F4F7FB; margin: 0; }
[data-testid="stMarkdownContainer"] p.list-count { font-size: 17px; color: #C0CDDD; margin: 0; }
/* 열 머리글: 표 바로 위에 붙여 두고 스크롤해도 남게 고정(사이에 테두리 상자를 두지 않는다) */
[data-testid="stMarkdownContainer"] p.col-head { display: flex; gap: 0; margin: 0; width: 498px; max-width: 100%;
  font-size: 16px; color: #C0CDDD; border-bottom: 1px solid #33455E; padding: 2px 0 7px 0; }
[data-testid="stMarkdownContainer"] p.col-head span { padding-left: 10px; }
/* 제목+열 머리글을 페이지 스크롤 중에도 위에 고정(바깥 래퍼에 걸어야 고정될 여지가 생긴다) */
[data-testid="stLayoutWrapper"]:has(> .st-key-acct_head) {
  position: sticky; top: 0; z-index: 6; background: #152033; padding: 4px 0 2px; }
/* 스크롤 영역 안의 표는 자체 머리글만큼 끌어올려 가린다(위의 고정 머리글을 쓴다) */
.st-key-acct_list [data-testid="stElementContainer"]:has([data-testid="stDataFrame"]) { overflow: hidden; }
.st-key-acct_list [data-testid="stDataFrameResizable"] { margin-top: -36px; border: 0; }
/* 목록·제목 줄을 표 너비에 맞춰 묶는다(스크롤바가 빈 공간에 뜨지 않게) */
.st-key-acct_list, .st-key-acct_head { max-width: none; }
/* 계정 설정 화면은 머리말을 줄여 목록에 세로 공간을 주고 페이지 스크롤을 없앤다 */
.acct-compact [data-testid="stMainBlockContainer"] { padding-top: 1.2rem !important; }
.st-key-acct_head [data-testid="stColumn"] > div { max-width: 498px; }
/* 변경 전·후는 선 없이 간격으로만 가른다 */
.st-key-acct_list [data-testid="stColumn"]:first-of-type,
.st-key-acct_head [data-testid="stColumn"]:first-of-type { padding-right: 8px; }
.st-key-acct_list [data-testid="stColumn"]:last-of-type,
.st-key-acct_head [data-testid="stColumn"]:last-of-type { padding-left: 8px; }
[data-testid="stCaptionContainer"] p { font-size: 17px; color: #C0CDDD; word-break: keep-all; }
.diagram { width: 100%; }
.diagram svg { width: 100%; height: auto; display: block; }
div[data-testid="stButton"] button { min-height: 50px; padding: 6px 20px; border-radius: 8px; white-space: nowrap; }
div[data-testid="stButton"] button p { font-size: 19px; white-space: nowrap; }
div[data-testid="stButton"] button[kind="primary"] { background: #60A5FA; color: #08131F; border-color: #60A5FA; }
div[data-testid="stButton"] button[kind="primary"] p { color: #08131F; font-weight: 700; }
div[data-testid="stWidgetLabel"] p { font-size: 19px; }
/* 비밀번호 편집 미니창 */
[data-testid="stMarkdownContainer"] p.pw-target { font-size: 20px; font-weight: 700; color: #F4F7FB; margin: 0 0 6px; }
[data-testid="stDialog"] [data-testid="stRadioGroup"] label p { font-size: 18px; }
[data-testid="stDialog"] { display: flex; align-items: center; justify-content: center; }
[data-testid="stDialog"] > div { margin: 0 auto; }
div[data-testid="stButton"] button p { font-size: 19px; white-space: nowrap; }
</style>"""


def set_page_width(px: int) -> None:
    st.markdown(f"<style>:root {{ --pw: {px}px; }}</style>", unsafe_allow_html=True)


@st.cache_resource
def get_client() -> DominoClient:
    return DominoClient()


@st.cache_resource
def get_simulation_component():
    return animation.register()


client = get_client()
state = st.session_state
st.markdown(CSS, unsafe_allow_html=True)

if not client.health():
    st.markdown('<p class="brand">AccountDomino</p>', unsafe_allow_html=True)
    st.error(f"모의 인증 서버({config.API_BASE_URL})에 연결할 수 없습니다. README 의 실행 방법을 확인하세요.")
    st.stop()

# ---- 화면을 오가도 유지되는 입력값(위젯 상태와 별도로 보관) ----------------------------------
if "base" not in state:
    state.scenario_id = "s1"
    state.count = config.DEFAULT_ACCOUNT_COUNT
    state.base = build_scenario(state.scenario_id, state.count)
    state.leaked = SCENARIOS[state.scenario_id]["leaked_service_id"]
state.setdefault("page", INTRO)
state.setdefault("editor_version", 0)
state.setdefault("notice", None)
state.setdefault("error", None)
state.setdefault("last_run", None)
state.setdefault("run_token", 0)
# 그룹(A–D) 실습용 비밀번호 값. 변경 전·후 독립(변경 후 수정이 변경 전에 영향 없음). '고유'는 서비스별 자동.
# 위젯 키와 분리해 보관한다: Streamlit 은 위젯이 그려지지 않은 런에서 위젯 키 상태를 버리므로,
# 미니창을 닫아도 값이 남도록 일반 상태(group_pw)를 원본으로 두고 위젯은 value= 로 초기화한다.
state.setdefault("group_pw", {p: dict(GROUP_PASSWORDS) for p in config.PROFILES})
state.setdefault("pw_open", None)      # 비밀번호 편집 미니창을 연 프로필(없으면 None)
state.setdefault("pw_draft", {})       # 미니창 임시 입력(적용 전까지 저장소에 반영하지 않음)
GROUP_PASSWORDS_LIST = list(GROUP_PASSWORDS)
state.setdefault("pw_group", GROUP_PASSWORDS_LIST[0])


def pw_input_key(group: str) -> str:
    return f"w_pwin_{group}"


def group_pw(profile: str) -> dict[str, str]:
    """프로필의 그룹→실습용 비밀번호 값(적용된 값 기준)."""
    return dict(state.group_pw[profile])


def reset_group_pw() -> None:
    """실습용 비밀번호를 기본 예시값으로 되돌린다(입력 중이던 값·위젯 상태까지 모두 폐기).

    여러 사람이 같은 화면을 번갈아 쓰는 실습 환경을 가정해, 앞 사람이 넣은 값이 남지 않게 한다.
    """
    state.group_pw = {p: dict(GROUP_PASSWORDS) for p in config.PROFILES}
    state.pw_open = None
    state.pw_draft = {}
    for g in GROUP_PASSWORDS:
        state.pop(pw_input_key(g), None)


def editor_key(profile: str) -> str:
    return f"editor_{profile}_{state.editor_version}"


def commit_editors(bump: bool = True) -> None:
    """표 편집 내용을 service_id 기준으로 입력값에 반영한다(쪽 나눔 없이 전체 목록).

    bump=True 는 단계 이동용(에디터를 새로 만들어 델타를 비운다).
    bump=False 는 편집 중 콜백용(변경 표시를 즉시 갱신하되 입력 포커스는 유지).
    """
    for profile in config.PROFILES:
        delta = state.get(editor_key(profile)) or {}
        rows = state.base[profile]
        for idx, changes in delta.get("edited_rows", {}).items():
            if int(idx) >= len(rows):
                continue
            row = rows[int(idx)]
            for column, value in changes.items():
                field = FIELD_OF.get(column)
                if field == "username":
                    row[field] = str(value or "").strip()
                elif field == "mfa_enabled":
                    row[field] = bool(value)
                elif field == "password_group" and value in PASSWORD_GROUPS:
                    row[field] = value
    if bump:
        state.editor_version += 1


def on_editor_change() -> None:
    commit_editors(bump=False)


def go(page: str) -> None:
    # 첫 화면으로 나가면 실습용 비밀번호를 기본값으로 되돌린다(다음 사람에게 남지 않게).
    if page == INTRO and state.get("group_pw") != {p: dict(GROUP_PASSWORDS) for p in config.PROFILES}:
        reset_group_pw()
        state.page = page
        state.notice = "입력한 실습용 비밀번호를 기본값으로 되돌렸습니다."
        state.error = None
        return
    state.page = page
    state.notice = None
    state.error = None


# ---- 콜백: 시나리오·계정 수를 바꿀 때만 관련 설정을 갱신 -------------------------------------
def on_scenario_change() -> None:
    sid = state.w_scenario
    state.scenario_id = sid
    state.base = build_scenario(sid, state.count)
    state.leaked = SCENARIOS[sid]["leaked_service_id"]
    state.editor_version += 1
    reset_group_pw()
    state.notice = f"‘{SCENARIOS[sid]['title']}’ 기본값으로 새로 채웠습니다."


def on_count_change() -> None:
    old, new = state.count, int(state.w_count)
    if old == new:
        return
    state.count = new
    state.base = resize_accounts(state.base, state.scenario_id, new)
    state.editor_version += 1
    msg = f"계정 수 {old} → {new}개. 기존 입력값은 유지됩니다."
    if state.leaked not in {a["service_id"] for a in state.base["before"]}:
        state.leaked = SCENARIOS[state.scenario_id]["leaked_service_id"]
        msg += f" 유출 출처는 {config.SERVICES[state.leaked]}(으)로 되돌렸습니다."
    state.notice = msg


def on_leak_change() -> None:
    state.leaked = state.w_leaked


def on_accounts_nav(target: str) -> None:
    commit_editors()
    if target == LEAK:          # 계정 설정에서 앞으로 나갈 때 아이디 누락을 먼저 잡는다
        empty = [i for i, a in enumerate(state.base["before"]) if not a["username"]]
        empty += [i for i, a in enumerate(state.base["after"]) if not a["username"]]
        if empty:
            names = sorted({config.SERVICES[state.base["before"][i]["service_id"]] for i in empty})
            state.error = f"아이디를 입력하세요: {', '.join(names)}"
            return
    go(target)


def on_exit_simulation() -> None:
    go(LEAK)        # 입력값은 그대로 두고 유출 출처 화면으로 돌아간다


# ---- 공통 배치 ------------------------------------------------------------------------
def brand() -> None:
    st.markdown('<p class="brand">AccountDomino</p>', unsafe_allow_html=True)


def header(page: str) -> None:
    """브랜드·단계·제목·설명·입력의 왼쪽 시작선을 맞춘다(중앙 정렬하지 않음)."""
    title, lead = PAGES[page]
    step = (f'<p class="step">단계 {SETUP_STEPS.index(page) + 1} / {len(SETUP_STEPS)}</p>'
            if page in SETUP_STEPS else "")
    st.markdown(f'{step}<p class="ptitle">{title}</p><p class="lead">{lead}</p>',
                unsafe_allow_html=True)


def nav(prev: str | None, next_label: str, on_next, next_args=(), prev_cb=None, prev_args=()) -> None:
    left, _, right = st.columns([2, 3, 2], vertical_alignment="bottom")
    with left:
        if prev:
            st.button("← 이전", key=f"prev_{state.page}", on_click=prev_cb or go,
                      args=prev_args or (prev,), width="stretch")
    with right:
        st.button(next_label, key=f"next_{state.page}", type="primary", on_click=on_next, args=next_args,
                  width="stretch")


# ---- 페이지 ---------------------------------------------------------------------------
_INTRO_ICONS = {
    "mail": "M4 6h16v12H4z M4 7l8 6 8-6",
    "shop": "M6 8h12l-1 11H7z M9 8a3 3 0 0 1 6 0",
    "sns": "M8 10a2.5 2.5 0 1 0 0-.1z M16 6a2 2 0 1 0 0-.1z M16 18a2 2 0 1 0 0-.1z M10 11l4-3 M10 13l4 3",
    "game": "M7 9h10a3 3 0 0 1 0 8H7a3 3 0 0 1 0-8z M10 11v4 M8 13h4 M16 12h.5 M18 14h.5",
    "cloud": "M7 17a4 4 0 0 1 .5-8 5 5 0 0 1 9.5 1 3.5 3.5 0 0 1-.5 7z",
}
_INTRO_NODES = [("mail", "메일", 118, 78), ("shop", "쇼핑", 502, 78),
                ("sns", "SNS", 74, 250), ("cloud", "클라우드", 546, 250), ("game", "게임", 310, 418)]


def _icon_paths(key: str) -> str:
    return "".join(f'<path d="{("M" + d) if i else d}"/>'
                   for i, d in enumerate(_INTRO_ICONS[key].split(" M")))


def intro_diagram() -> str:
    """시작 화면용 정적 네트워크 그림(중앙 유출 정보 → 주변 서비스). 결과·애니메이션 없음."""
    cx, cy = 310, 240
    lines = "".join(f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="#7186A3" stroke-width="1.5"/>'
                    for _, _, x, y in _INTRO_NODES)
    nodes = ""
    for key, name, x, y in _INTRO_NODES:
        nodes += (
            f'<g transform="translate({x - 68},{y - 23})">'
            f'<rect width="136" height="46" rx="8" fill="#1E2D43" stroke="#465B75"/>'
            f'<g transform="translate(13,12)" fill="none" stroke="#C0CDDD" stroke-width="1.7" '
            f'stroke-linecap="round" stroke-linejoin="round">{_icon_paths(key)}</g>'
            f'<text x="48" y="29" fill="#F4F7FB" font-size="18" font-weight="700">{name}</text></g>')
    return (
        '<div class="diagram"><svg viewBox="0 47 620 402" preserveAspectRatio="xMidYMid meet" role="img" '
        'aria-label="유출된 로그인 정보가 여러 서비스의 로그인에 시도되는 그림">'
        f'{lines}'
        f'<g transform="translate({cx - 96},{cy - 42})">'
        '<rect width="192" height="84" rx="12" fill="#273950" stroke="#60A5FA" stroke-width="1.5"/>'
        '<text x="96" y="34" fill="#60A5FA" font-size="15" font-weight="700" text-anchor="middle">유출된</text>'
        '<text x="96" y="58" fill="#F4F7FB" font-size="21" font-weight="700" text-anchor="middle">로그인 정보</text></g>'
        f'{nodes}</svg></div>')


def intro_page() -> None:
    set_page_width(1300)
    brand()
    left, right = st.columns([1, 1.35], gap="large", vertical_alignment="center")
    with left:
        st.markdown(
            '<p class="intro-title">크리덴셜 스터핑이란?</p>'
            '<div class="intro-body">'
            '<p>유출된 아이디·비밀번호 조합을 다른 서비스의 로그인에 자동으로 대입해, 계정 접근을 시도하는 공격입니다.</p>'
            '<p>같은 로그인 정보를 여러 서비스에서 재사용하면, 한 곳의 유출이 다른 계정의 피해로 이어질 수 있습니다.</p>'
            '<p>AccountDomino에서 비밀번호 재사용의 위험을 확인하고, 비밀번호 분리와 2차 인증이 결과를 어떻게 바꾸는지 비교해 보세요.</p>'
            '</div>', unsafe_allow_html=True)
        st.button("시뮬레이션 시작하기  →", type="primary", on_click=go, args=(SCENARIO,))
        st.markdown('<p class="foot-note">가상 계정으로 진행되는 교육용 시뮬레이션입니다</p>', unsafe_allow_html=True)
    with right:
        st.markdown(intro_diagram(), unsafe_allow_html=True)


def scenario_page() -> None:
    set_page_width(1000)
    brand()
    header(SCENARIO)
    if "w_scenario" not in state:
        state.w_scenario = state.scenario_id
    sid = st.selectbox("시나리오", list(SCENARIOS), format_func=lambda k: SCENARIOS[k]["title"],
                       key="w_scenario", on_change=on_scenario_change)
    st.markdown(f'<p class="change">{change_summary(state.base)}</p>', unsafe_allow_html=True)
    if "w_count" not in state:
        state.w_count = state.count
    st.number_input(f"가상 서비스 계정 수 ({config.MIN_ACCOUNT_COUNT}~{config.MAX_ACCOUNT_COUNT}개)",
                    min_value=config.MIN_ACCOUNT_COUNT, max_value=config.MAX_ACCOUNT_COUNT, step=1,
                    key="w_count", on_change=on_count_change)
    if state.base != build_scenario(state.scenario_id, state.count):
        st.caption("시나리오를 바꾸면 편집한 계정 설정이 기본값으로 초기화됩니다.")
    st.write("")
    nav(INTRO, "다음", go, (ACCOUNTS,))


# 열 제목은 짧게. 변경 전·후는 각각 독립 표로 두고, 공통 스크롤 영역에서 같은 행 높이에 맞춘다.
COLUMN_CONFIG = {
    COL_SERVICE: st.column_config.TextColumn(disabled=True, width=166),
    COL_USER: st.column_config.TextColumn(required=True, width=164),
    COL_GROUP: st.column_config.SelectboxColumn(options=PASSWORD_GROUPS, required=True, width=94,
                                                help=PASSWORD_GROUP_HELP),
    COL_MFA: st.column_config.CheckboxColumn(width=74, help="켜면 비밀번호가 맞아도 추가 인증이 필요합니다."),
}


def change_tag(before: dict, after: dict) -> str:
    fields = [c["field"] for c in changed_fields(before, after)]
    return " · ".join(CHANGE_TAG[f] for f in fields)


def to_frame(accounts: list[dict], before: list[dict] | None = None) -> pd.DataFrame:
    """계정 목록 → 표. before 를 주면(변경 후 표) 바뀐 행의 서비스 셀에 변경 태그를 붙인다."""
    by_before = {a["service_id"]: a for a in before} if before else {}
    rows = []
    for a in accounts:
        name = config.SERVICES[a["service_id"]]
        tag = change_tag(by_before.get(a["service_id"]), a) if before else ""
        rows.append({COL_SERVICE: f"{name} · {tag}" if tag else name, COL_USER: a["username"],
                     COL_GROUP: a["password_group"], COL_MFA: bool(a["mfa_enabled"])})
    return pd.DataFrame(rows)


def _same_value_groups(values: dict[str, str]) -> list[tuple[str, str]]:
    """서로 다른 그룹인데 값이 같은 쌍(실제로 같은 비밀번호로 인증됨)."""
    items = [(g, v) for g, v in values.items() if v != ""]
    return [(a, b) for i, (a, va) in enumerate(items) for (b, vb) in items[i + 1:] if va == vb]


def sync_pw_draft() -> None:
    """미니창 입력을 임시 보관(draft)에 반영한다. 그룹을 바꿔도 입력하던 값이 남는다."""
    for g in GROUP_PASSWORDS:
        key = pw_input_key(g)
        if key in state:
            state.pw_draft[g] = state[key]


def open_pw_modal(profile: str) -> None:
    """현재 적용값을 임시 보관에 복사해 미니창을 연다(계정 표 편집은 그대로 유지)."""
    commit_editors(bump=False)              # 표에 입력 중이던 내용을 먼저 보존
    state.pw_open = profile
    state.pw_draft = dict(state.group_pw[profile])
    state.pw_group = GROUP_PASSWORDS_LIST[0]
    for g in GROUP_PASSWORDS:               # 이전 미니창의 입력 위젯 상태를 지워 value= 로 다시 초기화
        state.pop(pw_input_key(g), None)


def close_pw_modal() -> None:
    """X·Esc·바깥 클릭·취소: 임시 입력을 폐기하고 닫는다(적용값은 그대로)."""
    state.pw_open = None
    state.pw_draft = {}


@st.dialog("비밀번호 편집", on_dismiss=close_pw_modal)
def pw_modal() -> None:
    profile = state.pw_open
    label = config.PROFILES[profile]
    st.markdown(f'<p class="pw-target">{label} 설정의 비밀번호 그룹 값</p>', unsafe_allow_html=True)
    st.caption("실제 사용 중인 비밀번호 대신 실습용 값을 입력하세요.")
    g = st.radio("그룹", GROUP_PASSWORDS_LIST, key="pw_group", horizontal=True,
                 on_change=sync_pw_draft)
    st.text_input(f"그룹 {g} 비밀번호", value=state.pw_draft.get(g, GROUP_PASSWORDS[g]),
                  key=pw_input_key(g), type="password", autocomplete="new-password",
                  on_change=sync_pw_draft)
    used = [a for a in state.base[profile] if a["password_group"] == g]
    names = "·".join(config.SERVICES[a["service_id"]] for a in used[:3])
    more = f" 외 {len(used) - 3}개" if len(used) > 3 else ""
    st.caption(f"이 값을 쓰는 계정 {len(used)}개" + (f": {names}{more}" if used else " (없음)"))
    draft = {**state.group_pw[profile], **state.pw_draft}
    same = [b for a, b in _same_value_groups(draft) if a == g] + [a for a, b in _same_value_groups(draft) if b == g]
    if same:
        st.caption(f"그룹 {'·'.join(sorted(set(same)))} 과(와) 값이 같아 실제로 같은 비밀번호로 인증됩니다.")
    st.write("")
    c_cancel, c_apply = st.columns(2)
    with c_cancel:
        if st.button("취소", width="stretch"):
            close_pw_modal()
            st.rerun()
    with c_apply:
        if st.button("적용", type="primary", width="stretch"):
            sync_pw_draft()
            state.group_pw[profile] = {**state.group_pw[profile], **state.pw_draft}
            state.notice = f"{label} 설정의 비밀번호 값을 적용했습니다."
            close_pw_modal()
            st.rerun()


def accounts_page() -> None:
    set_page_width(1096)
    # 목록이 화면 안에 들어오도록 이 화면에서만 머리말을 압축한다(페이지 스크롤 제거).
    st.markdown(
        '<style>[data-testid="stMainBlockContainer"]{padding-top:1.2rem !important;}'
        '[data-testid="stMarkdownContainer"] p.brand{font-size:30px !important;margin-bottom:2px !important;}'
        '[data-testid="stMarkdownContainer"] p.ptitle{font-size:26px !important;margin:2px 0 8px !important;}'
        '[data-testid="stMarkdownContainer"] p.lead{font-size:17px !important;margin-bottom:6px !important;}'
        '[data-testid="stMarkdownContainer"] p.step{margin-bottom:0 !important;}</style>',
        unsafe_allow_html=True)
    brand()
    header(ACCOUNTS)
    # 제목과 비밀번호 편집 버튼은 목록 위에 둔다(아래 표만 스크롤).
    with st.container(key="acct_head"):
        for col, profile in zip(st.columns(2, gap="medium"), config.PROFILES):
            with col:
                c_title, c_edit = st.columns([1.3, 1], vertical_alignment="center")
                with c_title:
                    st.markdown(f'<p class="prof-title">{config.PROFILES[profile]}</p>',
                                unsafe_allow_html=True)
                with c_edit:
                    st.button("비밀번호 편집", key=f"pw_btn_{profile}", on_click=open_pw_modal,
                              args=(profile,), width="stretch")
                st.markdown(
                    '<p class="col-head">'
                    '<span style="width:166px">서비스</span><span style="width:164px">아이디</span>'
                    '<span style="width:94px">그룹</span><span style="width:74px">MFA</span></p>',
                    unsafe_allow_html=True)
    # 두 표를 나란히 두어 같은 서비스가 항상 같은 줄에 오게 한다(목록 자체 스크롤 없이 페이지만 스크롤).
    full = (len(state.base["before"]) + 1) * ROW_HEIGHT + 3
    with st.container(key="acct_list"):
        for col, profile in zip(st.columns(2, gap="medium"), config.PROFILES):
            with col:
                before_rows = state.base["before"] if profile == "after" else None
                st.data_editor(to_frame(state.base[profile], before_rows),
                               column_config=COLUMN_CONFIG, hide_index=True, width="content",
                               key=editor_key(profile), on_change=on_editor_change,
                               row_height=ROW_HEIGHT, height=full)
    if state.error:
        st.error(state.error)
    st.write("")
    nav(SCENARIO, "다음", on_accounts_nav, (LEAK,),
        prev_cb=on_accounts_nav, prev_args=(SCENARIO,))
    if state.pw_open:
        pw_modal()


def group_pw_digest(profile: str) -> str:
    """그룹 값 변경 감지용 지문. 평문을 남기지 않으려고 해시만 보관한다(복원 불가)."""
    pairs = [(g, group_pw(profile)[g]) for g in GROUP_PASSWORDS]
    return hashlib.sha256(repr(pairs).encode("utf-8")).hexdigest()


def run_simulation(accounts: dict[str, list[dict]], leaked_service: str) -> dict:
    """두 설정에 같은 유출 정보(변경 전 출처 계정)로 출처를 뺀 서비스마다 모의 로그인하고, 실행 당시 설정·결과를 묶는다.

    입력한 그룹 값(resolve_password)으로 실제 해시 저장·검증한다. 평문은 서버 저장·스냅샷에 남기지 않는다.
    """
    accounts = copy.deepcopy(accounts)
    gpw = {profile: group_pw(profile) for profile in config.PROFILES}
    source = next(a for a in accounts["before"] if a["service_id"] == leaked_service)
    username = source["username"]
    # 유출 자격증명 = 변경 전 출처 계정의 아이디·실습용 비밀번호(전후 공통, 변경 후 값으로 새로 만들지 않음).
    password = resolve_password(source["password_group"], leaked_service, gpw["before"])
    # 같은 그룹이라도 전후 실제 값이 달라졌는지(표시용 메타데이터만, 평문은 남기지 않는다).
    by_after = {a["service_id"]: a for a in accounts["after"]}
    value_changed = {}
    for a in accounts["before"]:
        b_after = by_after.get(a["service_id"])
        if b_after is None:
            continue
        value_changed[a["service_id"]] = (
            resolve_password(a["password_group"], a["service_id"], gpw["before"])
            != resolve_password(b_after["password_group"], a["service_id"], gpw["after"]))
    snapshot = {"leaked": {"service_id": leaked_service, "username": source["username"],
                           "password_group": source["password_group"]},
                "accounts": accounts, "results": {}, "run_ids": {},
                "value_changed": value_changed,
                "group_pw_digest": {pf: group_pw_digest(pf) for pf in config.PROFILES}}
    for profile in config.PROFILES:
        # 평문은 서버 저장(해시) 용으로만 쓰고 스냅샷(accounts)에는 넣지 않는다.
        put_accounts = [{**a, "password": resolve_password(a["password_group"], a["service_id"], gpw[profile])}
                        for a in accounts[profile]]
        client.save_accounts(profile, put_accounts)
        run_id = client.create_run(profile, leaked_service, username, state.scenario_id)
        snapshot["run_ids"][profile] = run_id
        rows = []
        for service_id in target_services(accounts[profile], leaked_service):
            try:
                rows.append(client.login(service_id, profile, username, password, run_id))
            except (httpx.HTTPError, ValueError) as exc:
                # 오류를 불일치·차단으로 바꾸지 않고 그대로 기록한다.
                rows.append({"service_id": service_id, "result": None, "error": type(exc).__name__})
        snapshot["results"][profile] = rows
    return snapshot


def leak_page() -> None:
    set_page_width(1040)
    brand()
    header(LEAK)
    before = state.base["before"]
    ids = [a["service_id"] for a in before]
    if state.leaked not in ids:
        state.leaked = ids[0]
    if "w_leaked" not in state or state.w_leaked not in ids:
        state.w_leaked = state.leaked
    leaked = st.selectbox("로그인 정보가 유출된 계정", ids, format_func=config.SERVICES.get,
                          key="w_leaked", on_change=on_leak_change)
    source = next(a for a in before if a["service_id"] == leaked)
    st.markdown(
        f'<p class="summary"><b>{config.SERVICES[leaked]}</b> · 아이디 <span class="mono">{source["username"]}</span> · '
        f'비밀번호 {source["password_group"]}</p>'
        f'<p class="summary">다른 <b>{len(ids) - 1}개</b> 서비스에 시도</p>', unsafe_allow_html=True)
    if state.last_run is not None and (
            state.last_run["accounts"]["before"] != before
            or state.last_run.get("group_pw_digest")
            != {pf: group_pw_digest(pf) for pf in config.PROFILES}):
        st.caption("마지막 실행 이후 설정이 바뀌었습니다. 다시 시작하면 새 설정으로 시도합니다.")
    if state.error:
        st.error(state.error)
    st.write("")
    left, _, right = st.columns([2, 3, 2], vertical_alignment="bottom")
    with left:
        st.button("← 이전", on_click=go, args=(ACCOUNTS,), width="stretch")
    with right:
        start = st.button("시뮬레이션 시작", type="primary", width="stretch")
    if start:
        if any(not a["username"] for p in state.base.values() for a in p):
            state.error = "비어 있는 아이디가 있습니다. 계정 설정에서 입력하세요."
            st.rerun()
        try:
            with st.spinner("모의 로그인 중..."):
                snapshot = run_simulation(state.base, leaked)
        except httpx.HTTPError as exc:
            state.error = f"모의 인증 서버 요청에 실패했습니다: {exc}"
            st.rerun()
        state.run_token += 1
        snapshot["run_id"] = state.run_token
        state.last_run = snapshot
        go(SIMULATION)
        st.rerun()


def simulation_page() -> None:
    set_page_width(1600)
    run = state.last_run
    if run is None:
        go(LEAK)
        st.rerun()
    brand()
    mount = get_simulation_component()
    # 실행마다 새 key → 이전 실행의 재생 상태나 결과가 섞이지 않는다.
    mount(key=f"sim_{state.run_token}", data=build_animation_payload(run), on_exit_change=on_exit_simulation)


if state.notice:                       # 설정 변경 알림은 잠깐만 띄우고 남기지 않는다
    st.toast(state.notice)
    state.notice = None

{INTRO: intro_page, SCENARIO: scenario_page, ACCOUNTS: accounts_page,
 LEAK: leak_page,
 SIMULATION: simulation_page}.get(state.page, intro_page)()

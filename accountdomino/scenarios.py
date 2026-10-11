"""비밀번호 그룹과 기본 시나리오(모두 가상 데이터). 시나리오는 계정 수에 맞춰 규칙으로 생성한다."""
from __future__ import annotations

from . import config

# 같은 그룹 = 같은 비밀번호. 실제 비밀번호가 아닌 교육용 가상 값이다.
GROUP_PASSWORDS: dict[str, str] = {
    "A": "Domino-A!2024",
    "B": "Domino-B!2024",
    "C": "Domino-C!2024",
    "D": "Domino-D!2024",
}
UNIQUE_GROUP = "고유"
PASSWORD_GROUPS = [*GROUP_PASSWORDS, UNIQUE_GROUP]
PASSWORD_GROUP_HELP = "같은 그룹이면 같은 비밀번호를 사용합니다. ‘고유’는 계정마다 서로 다른 비밀번호입니다."


def password_for(group: str, service_id: str) -> str:
    """그룹 → 기본 가상 비밀번호. '고유'는 서비스마다 다른 값이 되도록 service_id 로 유도한다."""
    if group == UNIQUE_GROUP:
        return f"Unique-{service_id}!2024"
    if group not in GROUP_PASSWORDS:
        raise ValueError(f"unknown password group: {group}")
    return GROUP_PASSWORDS[group]


def resolve_password(group: str, service_id: str, group_passwords: dict[str, str] | None = None) -> str:
    """실제 인증에 쓸 평문. A–D 는 입력한 그룹 값(없으면 기본값), '고유'는 서비스별 자동 값.

    그룹 이름이 아니라 실제 값으로 판정되도록, 서로 다른 그룹에 같은 값을 넣으면 같은 비밀번호가 된다.
    """
    if group == UNIQUE_GROUP:
        return password_for(UNIQUE_GROUP, service_id)
    if group_passwords and group in group_passwords:
        return group_passwords[group]
    return password_for(group, service_id)


def service_ids(count: int) -> list[str]:
    """계정 수 → 사용할 서비스(카탈로그 앞에서부터)."""
    if not config.MIN_ACCOUNT_COUNT <= count <= config.MAX_ACCOUNT_COUNT:
        raise ValueError(f"account count out of range: {count}")
    return list(config.SERVICES)[:count]


# 규칙: 기본 아이디·그룹 + 서비스별 예외, 변경 전/후 MFA 대상. ALL = 모든 서비스.
ALL = "*"
_RULES: dict[str, dict] = {
    "s1": {
        "title": "일부 계정에 MFA 적용",
        "description": "대부분의 서비스에서 같은 아이디와 비밀번호(그룹 A)를 쓰고, 일부만 다른 비밀번호나 아이디를 쓰다가 "
                       "커뮤니티가 유출된 경우입니다. 변경 후에는 비밀번호는 그대로 두고 메일·학교·클라우드에만 MFA 를 켭니다.",
        "leaked_service_id": "community",
        "username": "student01",
        "usernames": {"game": "gamer_s01"},
        "group": "A",
        "groups": {"school": "C", "news": "B", "travel": UNIQUE_GROUP, "blog": "B", "map": UNIQUE_GROUP},
        "mfa_before": set(),
        "mfa_after": {"mail", "school", "cloud"},
    },
    "s2": {
        "title": "서비스별 비밀번호 분리",
        "description": "여러 서비스가 같은 비밀번호(그룹 A)를 쓰고 일부는 다른 비밀번호를 쓰다가 쇼핑이 유출된 경우입니다. "
                       "변경 후에는 유출 출처인 쇼핑을 포함해 모든 서비스의 비밀번호를 계정마다 다르게(고유) 바꿉니다.",
        "leaked_service_id": "shop",
        "username": "kim.demo",
        "usernames": {"sns": "kim.sns"},
        "group": "A",
        "groups": {"community": "B", "game": "B", "music": "C", "delivery": UNIQUE_GROUP,
                   "ticket": "B", "photo": "C"},
        "after_group": UNIQUE_GROUP,
        "mfa_before": set(),
        "mfa_after": set(),
    },
    "s3": {
        "title": "전체 계정에 MFA 적용",
        "description": "대부분의 서비스가 같은 비밀번호(그룹 B)를 쓰고 메일에만 MFA 를 켠 상태에서 커뮤니티가 유출된 경우입니다. "
                       "변경 후에는 비밀번호는 그대로 두고 모든 서비스에 MFA 를 켭니다.",
        "leaked_service_id": "community",
        "username": "lee_test",
        "usernames": {},
        "group": "B",
        "groups": {"school": "D", "video": "D", "travel": UNIQUE_GROUP, "job": "D"},
        "mfa_before": {"mail"},
        "mfa_after": {ALL},
    },
}


def _account(rule: dict, service_id: str, profile: str) -> dict:
    group = rule["groups"].get(service_id, rule["group"])
    if profile == "after" and "after_group" in rule:
        group = rule["after_group"]
    mfa = rule["mfa_before"] if profile == "before" else rule["mfa_after"]
    return {"service_id": service_id,
            "username": rule["usernames"].get(service_id, rule["username"]),
            "password_group": group,
            "mfa_enabled": ALL in mfa or service_id in mfa}


def build_scenario(scenario_id: str, count: int = config.DEFAULT_ACCOUNT_COUNT) -> dict[str, list[dict]]:
    """시나리오 규칙 → {"before": [...], "after": [...]}. 전후는 같은 service_id 순서로 대응한다."""
    rule = _RULES[scenario_id]
    ids = service_ids(count)
    return {p: [_account(rule, sid, p) for sid in ids] for p in config.PROFILES}


def resize_accounts(profiles: dict[str, list[dict]], scenario_id: str, count: int) -> dict[str, list[dict]]:
    """계정 수 조정: 남는 계정은 입력값 그대로 두고, 늘어난 계정만 시나리오 기본값으로 채운다."""
    defaults = build_scenario(scenario_id, count)
    resized = {}
    for profile, rows in defaults.items():
        current = {a["service_id"]: a for a in profiles.get(profile, [])}
        resized[profile] = [dict(current.get(row["service_id"], row)) for row in rows]
    return resized


def _names(ids: list[str], total: int) -> str:
    if ids and len(ids) == total:
        return "모든 계정"
    if len(ids) > 4:
        return f"{len(ids)}개 계정"
    return "·".join(config.SERVICES.get(s, s) for s in ids)


def change_summary(profiles: dict[str, list[dict]]) -> str:
    """변경 전→후에서 실제로 바뀐 설정을 한 줄로 요약한다(하드코딩이 아니라 데이터에서 계산)."""
    before = {a["service_id"]: a for a in profiles["before"]}
    after = profiles["after"]
    total = len(after)
    mfa_on, mfa_off, pw, unique, user = [], [], [], [], []
    for a in after:
        b = before.get(a["service_id"])
        if b is None:
            continue
        sid = a["service_id"]
        if bool(b["mfa_enabled"]) != bool(a["mfa_enabled"]):
            (mfa_on if a["mfa_enabled"] else mfa_off).append(sid)
        if b["password_group"] != a["password_group"]:
            pw.append(sid)
            if a["password_group"] == UNIQUE_GROUP:
                unique.append(sid)
        if b["username"] != a["username"]:
            user.append(sid)

    parts = []
    if pw:
        if unique and len(unique) == len(pw):
            parts.append(f"{_names(pw, total)} 비밀번호 고유")
        else:
            parts.append(f"{_names(pw, total)} 비밀번호 변경")
    if mfa_on:
        parts.append(f"{_names(mfa_on, total)} MFA ON")
    if mfa_off:
        parts.append(f"{_names(mfa_off, total)} MFA OFF")
    if user:
        parts.append(f"{_names(user, total)} 아이디 변경")
    return "변경 후: " + (" · ".join(parts) if parts else "변경 없음")


SCENARIOS: dict[str, dict] = {
    sid: {"title": r["title"], "description": r["description"], "leaked_service_id": r["leaked_service_id"],
          **build_scenario(sid)}
    for sid, r in _RULES.items()
}

"""비밀번호 재사용 그룹과 기본 시나리오(모두 가상 데이터)."""
from __future__ import annotations

# 같은 그룹 = 같은 비밀번호 재사용. 실제 비밀번호가 아닌 교육용 가상 값이다.
GROUP_PASSWORDS: dict[str, str] = {
    "A": "Domino-A!2024",
    "B": "Domino-B!2024",
    "C": "Domino-C!2024",
    "D": "Domino-D!2024",
}
UNIQUE_GROUP = "고유"
PASSWORD_GROUPS = [*GROUP_PASSWORDS, UNIQUE_GROUP]


def password_for(group: str, service_id: str) -> str:
    """그룹 → 가상 비밀번호. '고유'는 서비스마다 다른 값이 되도록 service_id 로 유도한다."""
    if group == UNIQUE_GROUP:
        return f"Unique-{service_id}!2024"
    if group not in GROUP_PASSWORDS:
        raise ValueError(f"unknown password group: {group}")
    return GROUP_PASSWORDS[group]


def _acc(service_id: str, username: str, group: str, mfa: bool = False) -> dict:
    return {"service_id": service_id, "username": username, "password_group": group, "mfa_enabled": mfa}


SCENARIOS: dict[str, dict] = {
    "s1": {
        "title": "① 세 계정 재사용 · MFA 없음 → 메일·학교에 MFA 적용",
        "description": "메일·쇼핑·커뮤니티는 같은 비밀번호(A), 학교만 다른 비밀번호(C)를 쓰다가 커뮤니티가 유출된 경우. "
                       "변경 후에는 비밀번호는 그대로 두고 메일·학교에만 MFA 를 켠다.",
        "leaked_service_id": "community",
        "before": [
            _acc("mail", "student01", "A"),
            _acc("shop", "student01", "A"),
            _acc("community", "student01", "A"),
            _acc("school", "student01", "C"),
        ],
        "after": [
            _acc("mail", "student01", "A", True),
            _acc("shop", "student01", "A"),
            _acc("community", "student01", "A"),
            _acc("school", "student01", "C", True),
        ],
    },
    "s2": {
        "title": "② 부분 재사용 → 모든 서비스 고유 비밀번호",
        "description": "메일·쇼핑·학교는 같은 비밀번호(A), 커뮤니티만 다른 비밀번호(B)를 쓰다가 쇼핑이 유출된 경우. "
                       "변경 후에는 유출 출처인 쇼핑을 포함해 모든 서비스의 비밀번호를 고유하게 바꾼다"
                       "(출처 계정을 그대로 두면 그 계정은 여전히 접근될 수 있다).",
        "leaked_service_id": "shop",
        "before": [
            _acc("mail", "kim.demo", "A"),
            _acc("shop", "kim.demo", "A"),
            _acc("community", "kim.demo", "B"),
            _acc("school", "kim.demo", "A"),
        ],
        "after": [
            _acc("mail", "kim.demo", UNIQUE_GROUP),
            _acc("shop", "kim.demo", UNIQUE_GROUP),
            _acc("community", "kim.demo", UNIQUE_GROUP),
            _acc("school", "kim.demo", UNIQUE_GROUP),
        ],
    },
    "s3": {
        "title": "③ 메일만 MFA → 전 서비스 MFA",
        "description": "메일·쇼핑·커뮤니티는 같은 비밀번호(B), 학교만 다른 비밀번호(D)를 쓰고 메일만 MFA 를 켠 상태에서 "
                       "커뮤니티가 유출된 경우. 변경 후에는 비밀번호는 그대로 두고 모든 서비스에 MFA 를 켠다.",
        "leaked_service_id": "community",
        "before": [
            _acc("mail", "lee_test", "B", True),
            _acc("shop", "lee_test", "B"),
            _acc("community", "lee_test", "B"),
            _acc("school", "lee_test", "D"),
        ],
        "after": [
            _acc("mail", "lee_test", "B", True),
            _acc("shop", "lee_test", "B", True),
            _acc("community", "lee_test", "B", True),
            _acc("school", "lee_test", "D", True),
        ],
    },
}

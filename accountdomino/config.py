"""공통 설정값. 모든 데이터와 요청은 로컬 환경에만 머문다."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "accountdomino.db"


def db_path() -> Path:
    """환경변수 ACCOUNTDOMINO_DB 로 DB 위치를 바꿀 수 있다(테스트용)."""
    return Path(os.environ.get("ACCOUNTDOMINO_DB", DEFAULT_DB_PATH))


API_BASE_URL = os.environ.get("ACCOUNTDOMINO_API", "http://127.0.0.1:8000")
ALLOWED_API_HOSTS = {"127.0.0.1", "localhost"}

# 하나의 모의 인증 서버가 service_id 로 서비스를 구분한다.
SERVICES: dict[str, str] = {
    "mail": "메일",
    "shop": "쇼핑",
    "community": "커뮤니티",
    "school": "학교",
}

PROFILES: dict[str, str] = {"before": "변경 전", "after": "변경 후"}

RESULT_SUCCESS = "접근 성공"
RESULT_MISMATCH = "비밀번호 불일치"
RESULT_MFA_BLOCKED = "MFA 차단"
RESULTS = [RESULT_SUCCESS, RESULT_MISMATCH, RESULT_MFA_BLOCKED]

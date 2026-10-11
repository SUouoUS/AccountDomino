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

# 하나의 모의 인증 서버가 service_id 로 서비스를 구분한다. 계정 수 N 이면 앞에서부터 N 개를 쓴다.
SERVICES: dict[str, str] = {
    "mail": "메일",
    "shop": "쇼핑",
    "community": "커뮤니티",
    "school": "학교",
    "game": "게임",
    "cloud": "클라우드",
    "sns": "SNS",
    "video": "동영상",
    "music": "음악",
    "news": "뉴스",
    "delivery": "배달",
    "travel": "여행",
    "ticket": "예매",
    "blog": "블로그",
    "job": "채용",
    "lecture": "온라인 강의",
    "photo": "사진 보관",
    "map": "지도",
    "ebook": "전자책",
    "fitness": "운동 기록",
}

# 기본 시나리오의 유출 출처(쇼핑·커뮤니티)가 항상 포함되도록 최소 4개
MIN_ACCOUNT_COUNT = 4
DEFAULT_ACCOUNT_COUNT = 12
MAX_ACCOUNT_COUNT = len(SERVICES)

PROFILES: dict[str, str] = {"before": "변경 전", "after": "변경 후"}

RESULT_SUCCESS = "접근 성공"
RESULT_MISMATCH = "비밀번호 불일치"
RESULT_MFA_BLOCKED = "MFA 차단"
RESULTS = [RESULT_SUCCESS, RESULT_MISMATCH, RESULT_MFA_BLOCKED]

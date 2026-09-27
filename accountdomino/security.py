"""비밀번호 해시. 표준 라이브러리 PBKDF2-HMAC-SHA256 + 계정별 salt 를 사용한다."""
from __future__ import annotations

import hashlib
import hmac
import secrets

ITERATIONS = 120_000
SALT_BYTES = 16


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """(hash_hex, salt_hex) 를 반환한다. 평문은 어디에도 저장하지 않는다."""
    if salt is None:
        salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    candidate, _ = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, hash_hex)

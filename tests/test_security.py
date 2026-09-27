from accountdomino.security import hash_password, verify_password


def test_hash_does_not_contain_plaintext():
    pw_hash, salt = hash_password("Domino-A!2024")
    assert "Domino" not in pw_hash
    assert len(pw_hash) == 64 and len(salt) == 32


def test_same_password_gets_different_salt_and_hash():
    h1, s1 = hash_password("Domino-A!2024")
    h2, s2 = hash_password("Domino-A!2024")
    assert s1 != s2 and h1 != h2


def test_verify_password():
    pw_hash, salt = hash_password("Domino-A!2024")
    assert verify_password("Domino-A!2024", pw_hash, salt)
    assert not verify_password("Domino-B!2024", pw_hash, salt)

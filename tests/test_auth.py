import pytest

from accountdomino import auth, config
from accountdomino.auth import AccountSetting
from accountdomino.scenarios import password_for


@pytest.fixture
def accounts(conn):
    auth.save_accounts(conn, "before", [
        AccountSetting("mail", "tester", "A", True),
        AccountSetting("shop", "tester", "A", False),
        AccountSetting("community", "tester", "B", False),
        AccountSetting("school", "other", "A", False),
    ])
    return conn


def test_passwords_are_stored_hashed(accounts):
    rows = accounts.execute("SELECT * FROM accounts").fetchall()
    columns = rows[0].keys()
    assert "password" not in columns
    for row in rows:
        for value in dict(row).values():
            assert "Domino-" not in str(value)


def test_access_success(accounts):
    assert auth.authenticate(accounts, "before", "shop", "tester", "Domino-A!2024") == config.RESULT_SUCCESS


def test_mfa_blocks_even_with_correct_password(accounts):
    assert auth.authenticate(accounts, "before", "mail", "tester", "Domino-A!2024") == config.RESULT_MFA_BLOCKED


def test_password_mismatch(accounts):
    assert auth.authenticate(accounts, "before", "community", "tester", "Domino-A!2024") == config.RESULT_MISMATCH


def test_unknown_username_is_reported_as_mismatch(accounts):
    assert auth.authenticate(accounts, "before", "school", "tester", "Domino-A!2024") == config.RESULT_MISMATCH


def test_profiles_are_isolated(accounts):
    assert auth.authenticate(accounts, "after", "shop", "tester", "Domino-A!2024") == config.RESULT_MISMATCH


def test_unknown_service_raises(accounts):
    with pytest.raises(auth.UnknownServiceError):
        auth.authenticate(accounts, "before", "bank", "tester", "Domino-A!2024")


def test_unique_group_differs_per_service():
    assert password_for("고유", "mail") != password_for("고유", "shop")
    assert password_for("A", "mail") == password_for("A", "shop")


def test_login_is_logged_without_password(accounts):
    run_id = auth.create_run(accounts, "before", "shop", "tester")
    auth.login_and_log(accounts, "before", "shop", "tester", "Domino-A!2024", run_id)
    logs = auth.get_logs(accounts, run_id=run_id)
    assert len(logs) == 1
    assert logs[0]["result"] == config.RESULT_SUCCESS
    assert all("Domino-" not in str(v) for v in logs[0].values())


def test_authenticate_steps_records_only_performed_steps(conn):
    auth.save_accounts(conn, "before", [
        AccountSetting("mail", "u", "A", True),      # 아이디 일치 + MFA
        AccountSetting("shop", "u", "A", False),     # 아이디 일치 + 성공
        AccountSetting("school", "other", "A", False),  # 아이디 불일치
    ])
    pw = password_for("A", "mail")
    # 아이디 불일치 → 비밀번호·MFA 미수행
    r = auth.authenticate_steps(conn, "before", "school", "u", pw)
    assert r["result"] == config.RESULT_MISMATCH
    assert r["steps"] == {"try": "done", "id": "nomatch", "password": "skipped", "mfa": "skipped"}
    assert r["verified"] is False and r["target_hash"] and r["target_salt"]
    # 비밀번호 불일치 → MFA 미수행
    r = auth.authenticate_steps(conn, "before", "shop", "u", "WRONG-VALUE")
    assert r["result"] == config.RESULT_MISMATCH
    assert r["steps"]["id"] == "match" and r["steps"]["password"] == "nomatch" and r["steps"]["mfa"] == "skipped"
    # 비밀번호 일치 + MFA 켜짐 → 차단
    r = auth.authenticate_steps(conn, "before", "mail", "u", pw)
    assert r["result"] == config.RESULT_MFA_BLOCKED and r["steps"]["mfa"] == "blocked" and r["verified"] is True
    # 비밀번호 일치 + MFA 꺼짐 → 성공
    r = auth.authenticate_steps(conn, "before", "shop", "u", pw)
    assert r["result"] == config.RESULT_SUCCESS and r["steps"]["mfa"] == "off"


def test_custom_group_password_is_used_for_real_auth(conn):
    # 그룹 A 에 실습용 값 SENTINEL 을 직접 저장 → 그 값으로만 인증
    auth.save_accounts(conn, "before", [
        AccountSetting("mail", "u", "A", False, password="SENTINEL-PW"),
        AccountSetting("shop", "u", "A", False, password="SENTINEL-PW"),   # 같은 값 → 같은 비밀번호
        AccountSetting("school", "u", "B", False, password="OTHER-PW"),    # 다른 값
    ])
    assert auth.authenticate(conn, "before", "mail", "u", "SENTINEL-PW") == config.RESULT_SUCCESS
    assert auth.authenticate(conn, "before", "shop", "u", "SENTINEL-PW") == config.RESULT_SUCCESS  # 다른 그룹 같은 값
    assert auth.authenticate(conn, "before", "school", "u", "SENTINEL-PW") == config.RESULT_MISMATCH
    assert auth.authenticate(conn, "before", "mail", "u", password_for("A", "mail")) == config.RESULT_MISMATCH


def test_steps_record_has_no_plaintext(conn):
    auth.save_accounts(conn, "before", [AccountSetting("mail", "u", "A", False, password="SENTINEL-PW")])
    r = auth.authenticate_steps(conn, "before", "mail", "u", "SENTINEL-PW")
    assert "SENTINEL-PW" not in str(r)

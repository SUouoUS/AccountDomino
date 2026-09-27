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

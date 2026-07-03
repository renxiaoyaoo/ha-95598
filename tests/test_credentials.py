import pytest

from scripts.support.credentials import load_login_credentials, mask_account, mask_user_id, mask_user_ids


def test_load_single_login_credential(monkeypatch):
    monkeypatch.delenv("LOGIN_CREDENTIALS", raising=False)
    monkeypatch.setenv("ACCOUNT", "test_account")
    monkeypatch.setenv("PASSWORD", "secret")

    credentials = load_login_credentials()

    assert len(credentials) == 1
    assert credentials[0].account == "test_account"
    assert credentials[0].password == "secret"
    assert credentials[0].label == "te***nt"


def test_login_credentials_json_overrides_single_account(monkeypatch):
    monkeypatch.setenv("ACCOUNT", "ignored")
    monkeypatch.setenv("PASSWORD", "ignored")
    monkeypatch.setenv(
        "LOGIN_CREDENTIALS",
        '[{"account":"account1","password":"password1","label":"main"},'
        '{"account":"account2","password":"password2"}]',
    )

    credentials = load_login_credentials()

    assert [credential.account for credential in credentials] == ["account1", "account2"]
    assert [credential.password for credential in credentials] == ["password1", "password2"]
    assert [credential.label for credential in credentials] == ["main", "ac***t2"]


def test_login_credentials_json_requires_valid_json(monkeypatch):
    monkeypatch.setenv("LOGIN_CREDENTIALS", "account1=password1")

    with pytest.raises(ValueError, match="LOGIN_CREDENTIALS must be a JSON array"):
        load_login_credentials()


def test_mask_short_account():
    assert mask_account("abc") == "***"


def test_mask_user_id_keeps_only_suffix():
    assert mask_user_id("fake-user-a") == "***er-a"
    assert mask_user_ids(["fake-user-a", "fake-user-b"]) == ["***er-a", "***er-b"]

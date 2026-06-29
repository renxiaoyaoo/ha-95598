import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LoginCredential:
    account: str
    password: str
    label: str


def mask_account(account: str) -> str:
    if len(account) <= 4:
        return "*" * len(account)
    return f"{account[:2]}***{account[-2:]}"


def load_login_credentials() -> list[LoginCredential]:
    raw_credentials = (os.getenv("LOGIN_CREDENTIALS") or "").strip()
    if raw_credentials:
        credentials = _parse_login_credentials_json(raw_credentials)
    else:
        account = (os.getenv("ACCOUNT") or "").strip()
        password = (os.getenv("PASSWORD") or "").strip()
        if not account or not password:
            raise ValueError("ACCOUNT and PASSWORD must be configured")
        credentials = [LoginCredential(account=account, password=password, label=mask_account(account))]

    if not credentials:
        raise ValueError("At least one login credential must be configured")
    return credentials


def _parse_login_credentials_json(raw_credentials: str) -> list[LoginCredential]:
    try:
        payload = json.loads(raw_credentials)
    except json.JSONDecodeError as exc:
        raise ValueError("LOGIN_CREDENTIALS must be a JSON array") from exc

    if not isinstance(payload, list):
        raise ValueError("LOGIN_CREDENTIALS must be a JSON array")

    credentials: list[LoginCredential] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"LOGIN_CREDENTIALS item #{index} must be an object")

        account = str(item.get("account") or "").strip()
        password = str(item.get("password") or "").strip()
        if not account or not password:
            raise ValueError(f"LOGIN_CREDENTIALS item #{index} must include account and password")

        label = str(item.get("label") or "").strip() or mask_account(account)
        credentials.append(LoginCredential(account=account, password=password, label=label))

    return credentials


def mask_user_id(user_id: str) -> str:
    value = str(user_id or "")
    if len(value) <= 4:
        return "*" * len(value)
    return f"***{value[-4:]}"

def mask_user_ids(user_ids) -> list[str]:
    return [mask_user_id(user_id) for user_id in (user_ids or [])]

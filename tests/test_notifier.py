import os
import types

import pytest

import scripts.support.notifier as notifier_module
from scripts.support.notifier import NoopNotifier, TelegramNotifier, build_notifier


class _RequestsStub:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, files=None, data=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "files": files,
                "data": data,
                "timeout": timeout,
            }
        )
        return types.SimpleNamespace(status_code=200, text="ok")


requests_stub = _RequestsStub()


@pytest.fixture(autouse=True)
def stub_requests(monkeypatch):
    requests_stub.calls.clear()
    monkeypatch.setattr(notifier_module, "requests", requests_stub)


def test_build_notifier_defaults_to_noop() -> None:
    os.environ.pop("NOTIFIER", None)
    os.environ.pop("TG_BOT_TOKEN", None)
    os.environ.pop("TG_CHAT_ID", None)
    os.environ.pop("TG_API_BASE_URL", None)
    notifier = build_notifier()
    assert isinstance(notifier, NoopNotifier)


def test_telegram_notifier_sends_stale_message() -> None:
    notifier = TelegramNotifier(bot_token="test_token", chat_id="test_chat_id")
    assert notifier.send_stale_data_alert("test_user", "2026-04-20", 3) is True
    assert requests_stub.calls[-1]["url"].endswith("/bottest_token/sendMessage")


def test_telegram_notifier_sends_qr_code() -> None:
    notifier = TelegramNotifier(bot_token="test_token", chat_id="test_chat_id")
    assert notifier.send_qr_code(b"fake_png") is True
    assert requests_stub.calls[-1]["url"].endswith("/bottest_token/sendPhoto")


def test_build_telegram_notifier_uses_custom_api_base_url() -> None:
    os.environ["NOTIFIER"] = "telegram"
    os.environ["TG_BOT_TOKEN"] = "test_token"
    os.environ["TG_CHAT_ID"] = "test_chat_id"
    os.environ["TG_API_BASE_URL"] = "https://tg-api.example.com/"
    notifier = build_notifier()
    assert isinstance(notifier, TelegramNotifier)
    assert notifier.api_base == "https://tg-api.example.com/bottest_token"


def test_build_telegram_notifier_accepts_api_base_domain_without_scheme() -> None:
    os.environ["NOTIFIER"] = "telegram"
    os.environ["TG_BOT_TOKEN"] = "test_token"
    os.environ["TG_CHAT_ID"] = "test_chat_id"
    os.environ["TG_API_BASE_URL"] = "tg-api.example.com"
    notifier = build_notifier()
    assert isinstance(notifier, TelegramNotifier)
    assert notifier.api_base == "https://tg-api.example.com/bottest_token"

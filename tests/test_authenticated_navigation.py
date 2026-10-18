from types import SimpleNamespace

import pytest

from scripts.support.ha95598_navigator import Ha95598Navigator


class FakeDriver:
    def __init__(self) -> None:
        self.urls = []

    def get(self, url: str) -> None:
        self.urls.append(url)


def make_navigator(expired_states):
    states = iter(expired_states)
    traces = []
    sleeps = []
    relogins = []
    navigator = Ha95598Navigator(
        driver_wait_time=1,
        login_manager=SimpleNamespace(),
        tencent_captcha=SimpleNamespace(),
        log_page_state=lambda _driver, label: traces.append(label),
        step_sleep=lambda _driver, label: sleeps.append(label),
        click_button=lambda *_args: None,
    )
    navigator.has_session_expired_modal = lambda _driver: next(states)
    navigator.relogin_after_session_expired = lambda _driver: relogins.append(True)
    return navigator, traces, sleeps, relogins


def test_open_authenticated_url_returns_when_session_is_valid():
    navigator, traces, sleeps, relogins = make_navigator([False])
    driver = FakeDriver()

    navigator.open_authenticated_url(driver, "https://example.invalid/protected", "open_protected")

    assert driver.urls == ["https://example.invalid/protected"]
    assert traces == ["open_protected"]
    assert sleeps == ["open_protected"]
    assert relogins == []


def test_open_authenticated_url_retries_once_after_expiry():
    navigator, traces, sleeps, relogins = make_navigator([True, False])
    driver = FakeDriver()

    navigator.open_authenticated_url(driver, "https://example.invalid/protected", "open_protected")

    assert driver.urls == ["https://example.invalid/protected", "https://example.invalid/protected"]
    assert traces == ["open_protected", "open_protected_after_relogin"]
    assert sleeps == traces
    assert relogins == [True]


def test_open_authenticated_url_fails_after_repeated_expiry():
    navigator, _traces, _sleeps, relogins = make_navigator([True, True])

    with pytest.raises(RuntimeError, match="expired again"):
        navigator.open_authenticated_url(FakeDriver(), "https://example.invalid/protected", "open_protected")

    assert relogins == [True]

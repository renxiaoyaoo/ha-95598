from types import SimpleNamespace

import pytest

import scripts.data_fetcher as data_fetcher_module
from scripts.data_fetcher import DataFetcher


class FakeDriver:
    def __init__(self) -> None:
        self.quit_called = False

    def get(self, _url) -> None:
        pass

    def quit(self) -> None:
        self.quit_called = True


class FakeUpdater:
    def __init__(self) -> None:
        self.statuses = []
        self.closed = False

    def update_fetch_status(self, _user_id, _postfix, status, **_attributes) -> None:
        self.statuses.append(status)

    def get_progress(self, _user_id) -> dict:
        return {}

    def get_cached_user_data(self, _user_id) -> dict:
        return {}

    def close(self) -> None:
        self.closed = True


def test_fetch_raises_when_a_user_fetch_fails(monkeypatch) -> None:
    driver = FakeDriver()
    updater = FakeUpdater()
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.updater = updater
    fetcher.IGNORE_USER_ID = []
    fetcher.RETRY_TIMES_LIMIT = 3
    fetcher.login_manager = SimpleNamespace(restore_or_login=lambda _driver: None)
    fetcher.ha_energy_backfiller = None
    fetcher._get_webdriver = lambda: driver
    fetcher._step_sleep = lambda *_args, **_kwargs: None
    fetcher._resolve_user_id_list = lambda _driver, _updater: ["test_user_0000"]
    fetcher._is_progress_current = lambda _progress: False
    fetcher._has_completed_stage = lambda _progress, _stage: False
    fetcher._log_page_state = lambda *_args: None
    fetcher._get_all_data = lambda *_args: (_ for _ in ()).throw(ValueError("private"))
    monkeypatch.setattr(
        data_fetcher_module.ErrorWatcher,
        "instance",
        staticmethod(lambda: SimpleNamespace(set_driver=lambda _driver: None)),
    )

    with pytest.raises(RuntimeError, match="1 user fetch"):
        fetcher.fetch()

    assert updater.statuses == ["running", "failed"]
    assert updater.closed is True
    assert driver.quit_called is True


def test_fetch_raises_when_login_returns_no_user_ids(monkeypatch) -> None:
    driver = FakeDriver()
    updater = FakeUpdater()
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.updater = updater
    fetcher.IGNORE_USER_ID = []
    fetcher.RETRY_TIMES_LIMIT = 3
    fetcher.login_manager = SimpleNamespace(restore_or_login=lambda _driver: None)
    fetcher._get_webdriver = lambda: driver
    fetcher._step_sleep = lambda *_args, **_kwargs: None
    fetcher._resolve_user_id_list = lambda _driver, _updater: []
    monkeypatch.setattr(
        data_fetcher_module.ErrorWatcher,
        "instance",
        staticmethod(lambda: SimpleNamespace(set_driver=lambda _driver: None)),
    )

    with pytest.raises(RuntimeError, match="No user IDs"):
        fetcher.fetch()

    assert updater.closed is True
    assert driver.quit_called is True

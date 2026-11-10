import os
from pathlib import Path

import pytest
from selenium.common.exceptions import TimeoutException

import scripts.support.browser_factory as browser_factory
from scripts.support.browser_factory import prune_profile_cache, remove_stale_profile_locks


def test_profile_cache_pruning_removes_oldest_files_first(tmp_path: Path):
    cache_dir = tmp_path / "Default" / "Code Cache"
    cache_dir.mkdir(parents=True)
    files = [cache_dir / f"cache-{index}" for index in range(3)]
    for index, path in enumerate(files):
        path.write_bytes(b"x" * 10)
        os.utime(path, (index + 1, index + 1))

    removed_files, removed_bytes = prune_profile_cache(tmp_path, limit_bytes=15)

    assert removed_files == 2
    assert removed_bytes == 20
    assert not files[0].exists()
    assert not files[1].exists()
    assert files[2].exists()


def test_profile_cache_pruning_can_be_disabled(tmp_path: Path):
    cache_file = tmp_path / "Default" / "Cache" / "cache-entry"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"x" * 10)

    assert prune_profile_cache(tmp_path, limit_bytes=0) == (0, 0)
    assert cache_file.exists()


def test_driver_start_failure_stops_chromedriver_service(monkeypatch):
    class FakeService:
        stopped = False

        def stop(self):
            self.stopped = True

    service = FakeService()
    monkeypatch.setenv("PYTHON_IN_DOCKER", "1")
    monkeypatch.setenv("BROWSER_PERSIST_PROFILE", "false")
    monkeypatch.setattr(browser_factory, "ChromeService", lambda **_kwargs: service)
    monkeypatch.setattr(
        browser_factory.webdriver,
        "Chrome",
        lambda **_kwargs: (_ for _ in ()).throw(TimeoutException()),
    )

    with pytest.raises(TimeoutException):
        browser_factory.create_chromium_driver(1)

    assert service.stopped is True


def test_driver_setup_failure_quits_browser_and_stops_service(monkeypatch):
    class FakeService:
        stopped = False

        def stop(self):
            self.stopped = True

    class FakeDriver:
        quit_called = False

        def set_page_load_timeout(self, _timeout):
            pass

        def execute_cdp_cmd(self, *_args):
            raise TimeoutException()

        def quit(self):
            self.quit_called = True

    service = FakeService()
    driver = FakeDriver()
    monkeypatch.setenv("PYTHON_IN_DOCKER", "1")
    monkeypatch.setenv("BROWSER_PERSIST_PROFILE", "false")
    monkeypatch.setattr(browser_factory, "ChromeService", lambda **_kwargs: service)
    monkeypatch.setattr(browser_factory.webdriver, "Chrome", lambda **_kwargs: driver)

    with pytest.raises(TimeoutException):
        browser_factory.create_chromium_driver(1)

    assert driver.quit_called is True
    assert service.stopped is True


def test_stale_profile_locks_are_removed(tmp_path: Path):
    (tmp_path / "SingletonLock").symlink_to("old-container-123")
    (tmp_path / "SingletonSocket").symlink_to("/tmp/missing-socket")
    (tmp_path / "SingletonCookie").symlink_to("123456")

    assert remove_stale_profile_locks(tmp_path) == 3
    assert not (tmp_path / "SingletonLock").is_symlink()
    assert not (tmp_path / "SingletonSocket").is_symlink()
    assert not (tmp_path / "SingletonCookie").is_symlink()


def test_active_profile_lock_is_preserved(tmp_path: Path, monkeypatch):
    lock = tmp_path / "SingletonLock"
    lock.symlink_to(f"test-host-{os.getpid()}")
    monkeypatch.setattr(browser_factory.socket, "gethostname", lambda: "test-host")

    assert remove_stale_profile_locks(tmp_path) == 0
    assert lock.is_symlink()


def test_persistent_profile_failure_retries_with_ephemeral_profile(monkeypatch, tmp_path):
    class FakeService:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    class FakeDriver:
        def __init__(self, fail_setup):
            self.fail_setup = fail_setup
            self.quit_called = False

        def set_page_load_timeout(self, _timeout):
            pass

        def execute_cdp_cmd(self, *_args):
            if self.fail_setup:
                raise TimeoutException()

        def implicitly_wait(self, _timeout):
            pass

        def quit(self):
            self.quit_called = True

    services = []
    drivers = []

    def make_service(**_kwargs):
        service = FakeService()
        services.append(service)
        return service

    def make_driver(*, options, service):
        driver = FakeDriver(fail_setup=not drivers)
        driver.options = options
        driver.service = service
        drivers.append(driver)
        return driver

    monkeypatch.setenv("PYTHON_IN_DOCKER", "1")
    monkeypatch.setenv("BROWSER_PERSIST_PROFILE", "true")
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(browser_factory, "_persistent_profile_available", True)
    monkeypatch.setattr(browser_factory, "ChromeService", make_service)
    monkeypatch.setattr(browser_factory.webdriver, "Chrome", make_driver)

    result = browser_factory.create_chromium_driver(1)

    assert result is drivers[1]
    assert drivers[0].quit_called is True
    assert services[0].stopped is True
    assert any(argument.startswith("--user-data-dir=") for argument in drivers[0].options.arguments)
    assert not any(argument.startswith("--user-data-dir=") for argument in drivers[1].options.arguments)
    assert drivers[0].options.experimental_options["prefs"]["session.startup_urls"] == ["data:,"]
    assert "session.startup_urls" not in drivers[1].options.experimental_options["prefs"]

    browser_factory.create_chromium_driver(1)
    assert not any(argument.startswith("--user-data-dir=") for argument in drivers[2].options.arguments)

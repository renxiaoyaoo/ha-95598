from scripts.support import job_scheduler


class FailingFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self) -> None:
        self.calls += 1
        raise ValueError("private details must not affect retry behavior")


def test_run_task_retries_failed_fetch(monkeypatch) -> None:
    fetcher = FailingFetcher()
    monkeypatch.setattr(job_scheduler, "run_captcha_maintenance", lambda _path: None)
    monkeypatch.setattr(job_scheduler, "touch_scheduler_heartbeat", lambda: None)
    monkeypatch.setenv("FETCH_ATTEMPT_TIMEOUT_MINUTES", "0")

    assert job_scheduler.run_task(fetcher, 2) is False
    assert fetcher.calls == 2


def test_invalid_fetch_timeout_uses_safe_default(monkeypatch) -> None:
    monkeypatch.setenv("FETCH_ATTEMPT_TIMEOUT_MINUTES", "invalid")

    assert job_scheduler._fetch_attempt_timeout_seconds() == 30 * 60


def test_fetch_timeout_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("FETCH_ATTEMPT_TIMEOUT_MINUTES", "0")

    assert job_scheduler._fetch_attempt_timeout_seconds() == 0

from scripts.support import job_scheduler


class FailingFetcher:
    def __init__(self) -> None:
        self.calls = 0
        self.prepare_calls = 0
        self.stale_checks = 0
        self.failure_types = []

    def fetch(self) -> None:
        self.calls += 1
        raise ValueError("private details must not affect retry behavior")

    def prepare_scheduled_run(self) -> None:
        self.prepare_calls += 1

    def check_cached_stale_data(self) -> None:
        self.stale_checks += 1

    def handle_scheduled_failure(self, error_type: str) -> None:
        self.failure_types.append(error_type)


def test_run_task_retries_failed_fetch(monkeypatch) -> None:
    fetcher = FailingFetcher()
    monkeypatch.setattr(job_scheduler, "run_captcha_maintenance", lambda _path: None)
    monkeypatch.setattr(job_scheduler, "touch_scheduler_heartbeat", lambda: None)
    monkeypatch.setenv("FETCH_ATTEMPT_TIMEOUT_MINUTES", "0")

    assert job_scheduler.run_task(fetcher, 2) is False
    assert fetcher.calls == 2
    assert fetcher.prepare_calls == 1
    assert fetcher.stale_checks == 0
    assert fetcher.failure_types == ["ValueError"]


def test_invalid_fetch_timeout_uses_safe_default(monkeypatch) -> None:
    monkeypatch.setenv("FETCH_ATTEMPT_TIMEOUT_MINUTES", "invalid")

    assert job_scheduler._fetch_attempt_timeout_seconds() == 30 * 60


def test_fetch_timeout_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("FETCH_ATTEMPT_TIMEOUT_MINUTES", "0")

    assert job_scheduler._fetch_attempt_timeout_seconds() == 0


def test_explicit_job_times_override_evenly_spaced_schedule(monkeypatch) -> None:
    job_scheduler.schedule.clear()
    monkeypatch.setattr(job_scheduler.random, "randint", lambda _start, _end: 0)
    try:
        job_scheduler.schedule_jobs(
            FailingFetcher(),
            object(),
            "07:00",
            2,
            1,
            0,
            ("12:15", "18:15"),
        )

        assert [job.at_time.strftime("%H:%M") for job in job_scheduler.schedule.get_jobs()] == [
            "12:15",
            "18:15",
        ]
    finally:
        job_scheduler.schedule.clear()

import logging
import os
import random
import signal
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import schedule


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HEARTBEAT_PATH = Path("/tmp/ha95598_scheduler_heartbeat")


class FetchAttemptTimeout(TimeoutError):
    pass


def _fetch_attempt_timeout_seconds() -> int:
    try:
        minutes = int(os.getenv("FETCH_ATTEMPT_TIMEOUT_MINUTES", "30"))
    except ValueError:
        logging.warning("Invalid FETCH_ATTEMPT_TIMEOUT_MINUTES; using 30 minutes.")
        minutes = 30
    return max(minutes, 0) * 60


def touch_scheduler_heartbeat() -> None:
    try:
        HEARTBEAT_PATH.touch()
    except OSError as exc:
        logging.warning("Failed to update scheduler heartbeat (%s).", type(exc).__name__)


def run_captcha_maintenance(data_dir: Path) -> None:
    from captcha_solver.replay import auto_replay_once

    auto_replay_once(data_dir)


@contextmanager
def fetch_attempt_timeout(timeout_seconds: int):
    """Bound one synchronous fetch attempt on Unix main-thread schedulers."""

    can_alarm = (
        timeout_seconds > 0
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    if not can_alarm:
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)

    def handle_timeout(_signum, _frame):
        raise FetchAttemptTimeout(f"fetch attempt exceeded {timeout_seconds} seconds")

    signal.signal(signal.SIGALRM, handle_timeout)
    signal.alarm(timeout_seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def schedule_jobs(fetcher, updater, job_start_time: str, job_times: int, retry_times_limit: int, republish_interval_minutes: int) -> None:
    base_time = datetime.strptime(job_start_time, "%H:%M")

    for index in range(job_times):
        random_delay_minutes = random.randint(-10, 10)
        final_time = base_time + timedelta(hours=(24 / job_times) * index) + timedelta(minutes=random_delay_minutes)
        run_time_str = final_time.strftime("%H:%M")
        logging.info("Scheduled job will run at %s every day", run_time_str)
        schedule.every().day.at(run_time_str).do(run_task, fetcher, retry_times_limit)

    if republish_interval_minutes > 0:
        logging.info("Cached data will be republished every %s minutes", republish_interval_minutes)
        schedule.every(republish_interval_minutes).minutes.do(updater.republish)
    else:
        logging.info("Periodic cache republish is disabled.")


def run_task(data_fetcher, retry_times_limit: int):
    logging.info("Scheduled state-refresh task started.")
    success = False
    timeout_seconds = _fetch_attempt_timeout_seconds()
    try:
        for retry_times in range(1, retry_times_limit + 1):
            touch_scheduler_heartbeat()
            try:
                with fetch_attempt_timeout(timeout_seconds):
                    data_fetcher.fetch()
                success = True
                logging.info("Scheduled state-refresh task completed successfully.")
                return True
            except Exception as exc:
                logging.error(
                    "Scheduled state-refresh task failed (%s), %s retry times left.",
                    type(exc).__name__,
                    retry_times_limit - retry_times,
                )
        logging.error("Scheduled state-refresh task failed after %s attempt(s).", retry_times_limit)
        stale_check = getattr(data_fetcher, "check_cached_stale_data", None)
        if callable(stale_check):
            try:
                stale_check()
            except Exception as exc:
                logging.error("Cached stale-data check failed (%s).", type(exc).__name__)
    finally:
        touch_scheduler_heartbeat()
        run_captcha_maintenance(DATA_DIR)
        touch_scheduler_heartbeat()
        if not success:
            logging.info("Scheduled state-refresh task ended without new data.")
    return False


def run_forever() -> None:
    while True:
        touch_scheduler_heartbeat()
        schedule.run_pending()
        time.sleep(1)

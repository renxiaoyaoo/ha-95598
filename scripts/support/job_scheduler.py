import logging
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import schedule

from captcha_solver.replay import auto_replay_once


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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
    try:
        for retry_times in range(1, retry_times_limit + 1):
            try:
                data_fetcher.fetch()
                success = True
                logging.info("Scheduled state-refresh task completed successfully.")
                return
            except Exception as exc:
                logging.error(
                    "Scheduled state-refresh task failed, reason is [%s], %s retry times left.",
                    exc,
                    retry_times_limit - retry_times,
                )
        logging.error("Scheduled state-refresh task failed after %s attempt(s).", retry_times_limit)
    finally:
        auto_replay_once(DATA_DIR)
        if not success:
            logging.info("Scheduled state-refresh task ended without new data.")


def run_forever() -> None:
    while True:
        schedule.run_pending()
        time.sleep(1)

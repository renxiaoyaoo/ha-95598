import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from scripts.data_fetcher import DataFetcher
from scripts.sensor_updater import SensorUpdater
from scripts.support.error_watcher import ErrorWatcher
from scripts.support.credentials import LoginCredential, load_login_credentials
from scripts.support.job_scheduler import run_forever, run_task, schedule_jobs
from scripts.support.tou_price import TimeOfUsePriceResolver


LOCAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class RuntimeConfig:
    credentials: list[LoginCredential]
    job_start_time: str
    job_times: int
    log_level: str
    version: str | None
    retry_times_limit: int
    republish_interval_minutes: int
    fetch_on_startup: bool


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        credentials=load_login_credentials(),
        job_start_time=os.getenv("JOB_START_TIME", "07:00"),
        job_times=int(os.getenv("JOB_TIMES", 2)),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        version=os.getenv("VERSION"),
        retry_times_limit=int(os.getenv("RETRY_TIMES_LIMIT", 5)),
        republish_interval_minutes=int(os.getenv("REPUBLISH_INTERVAL_MINUTES", 60)),
        fetch_on_startup=os.getenv("FETCH_ON_STARTUP", "false").lower() == "true",
    )
def main():
    if "PYTHON_IN_DOCKER" not in os.environ:
        import dotenv
        dotenv.load_dotenv(verbose=True)

    try:
        config = load_runtime_config()
        logger_init(config.log_level)
        if "PYTHON_IN_DOCKER" in os.environ:
            logging.info("The current run uses the Docker environment.")
        else:
            logging.info("The current run uses the local environment.")
    except Exception as exc:
        logging.error("Failed to read runtime configuration: %s", exc)
        sys.exit()

    logging.info("The current project version is %s.", config.version)
    logging.info("Configured %s login credential(s).", len(config.credentials))
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("The current date is %s.", current_datetime)
    logging.info("TOU price config path: %s", TimeOfUsePriceResolver().config_path)

    error_root = str(LOCAL_DATA_DIR)
    screenshot_dir = str(LOCAL_DATA_DIR / "pages")
    logging.info("Start init ErrorWatcher")
    ErrorWatcher.init(root_dir=error_root, screenshot_dir=screenshot_dir)
    logging.info("ErrorWatcher init done")
    updater = SensorUpdater()
    fetcher = DataFetcher(config.credentials[0].account, config.credentials[0].password, updater=updater, credentials=config.credentials)
    schedule_jobs(fetcher, updater, config.job_start_time, config.job_times, config.retry_times_limit, config.republish_interval_minutes)

    republished = updater.republish()
    if not config.fetch_on_startup:
        logging.info("Startup fetch is disabled; waiting for the scheduled run.")
    elif republished and updater.should_skip_startup_fetch():
        logging.info("Data restored from complete cache, skipping startup fetch to protect account.")
    else:
        logging.info("Cache is missing, stale, or incomplete. Fetching data from State Grid...")
        run_task(fetcher, config.retry_times_limit)

    run_forever()

def logger_init(level: str):
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.handlers.clear()
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    format = logging.Formatter("%(asctime)s  [%(levelname)s] ---- %(message)s", "%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(format)
    logger.addHandler(sh)


if __name__ == "__main__":
    main()

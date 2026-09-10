import argparse
import logging
import os
import sys
from pathlib import Path

from scripts.data_fetcher import DataFetcher
from scripts.fetchers.daily_range import DailyRangeFetchService
from scripts.main import logger_init
from scripts.sensor_updater import SensorUpdater
from scripts.support.credentials import load_login_credentials
from scripts.support.error_watcher import ErrorWatcher


LOCAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch 95598 daily usage data for an explicit date range.")
    parser.add_argument("--start", required=True, help="Start date, format YYYY-MM-DD.")
    parser.add_argument("--end", required=True, help="End date, format YYYY-MM-DD.")
    parser.add_argument(
        "--user-id",
        action="append",
        dest="user_ids",
        help="Optional target user id. Can be repeated. Defaults to all discovered user ids.",
    )
    return parser.parse_args()


def main():
    if "PYTHON_IN_DOCKER" not in os.environ:
        import dotenv

        dotenv.load_dotenv(verbose=True)

    args = parse_args()
    logger_init(os.getenv("LOG_LEVEL", "INFO"))
    ErrorWatcher.init(root_dir=str(LOCAL_DATA_DIR), screenshot_dir=str(LOCAL_DATA_DIR / "pages"))

    credentials = load_login_credentials()
    updater = SensorUpdater()
    fetcher = DataFetcher(
        credentials[0].account,
        credentials[0].password,
        updater=updater,
        credentials=credentials,
    )
    service = DailyRangeFetchService.from_data_fetcher(fetcher)
    result = service.fetch(args.start, args.end, user_ids=args.user_ids)
    logging.info("Daily range fetch completed for %s user(s).", len(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.error("Daily range fetch failed (%s).", type(exc).__name__)
        sys.exit(1)

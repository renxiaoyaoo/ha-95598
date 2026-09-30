import logging
import os
import time
from datetime import datetime
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from scripts.fetchers.balance import BalanceFetcher
from scripts.fetchers.monthly_bill import MonthlyBillFetcher
from scripts.fetchers.usage import UsageFetcher
from scripts.pages.usage_page import UsagePage
from scripts.sensor_updater import SensorUpdater
from scripts.support.browser_factory import create_chromium_driver
from scripts.support.data_persister import DataPersister, FetchedUserData
from scripts.support.error_watcher import ErrorWatcher
from scripts.support.fetch_progress import has_completed_stage
from typing import Optional
from scripts.support.page_tracer import PageTracer
from scripts.support.session_manager import SessionManager
from scripts.support.credentials import LoginCredential, mask_account, mask_user_id, mask_user_ids
from scripts.support.login_manager import LoginManager
from scripts.support.ha95598_navigator import Ha95598Navigator
from scripts.support.ha_energy_backfiller import HaEnergyStatisticsBackfiller
from scripts.support.user_ids import resolve_user_ids
from scripts.support.fetch_workflow import FetchWorkflow

from scripts.const import BALANCE_URL

from pathlib import Path
from scripts.support.tou_price import TimeOfUsePriceResolver


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

class DataFetcher:

    def __init__(self, account: str, password: str, updater=None, credentials: Optional[list[LoginCredential]] = None):
        if 'PYTHON_IN_DOCKER' not in os.environ:
            import dotenv
            dotenv.load_dotenv(verbose=True)
        self.credentials = credentials or [
            LoginCredential(account=account, password=password, label=mask_account(account))
        ]
        self.updater = updater

        self.DRIVER_IMPLICITY_WAIT_TIME = int(os.getenv("DRIVER_IMPLICITY_WAIT_TIME", 60))
        self.RETRY_TIMES_LIMIT = int(os.getenv("RETRY_TIMES_LIMIT", 5))
        self.RETRY_WAIT_TIME_OFFSET_UNIT = int(os.getenv("RETRY_WAIT_TIME_OFFSET_UNIT", 5))
        self.IGNORE_USER_ID = [user_id.strip() for user_id in os.getenv("IGNORE_USER_ID", "").split(",") if user_id.strip()]
        self.QR_CODE_LOGIN_WAIT_COUNT = int(os.getenv("QR_CODE_LOGIN_WAIT_COUNT", 7))
        self.QR_CODE_LOGIN_WAIT_TIME_INTERVAL_UNIT = int(os.getenv("QR_CODE_LOGIN_WAIT_TIME_INTERVAL_UNIT", 10))
        self.QR_CODE_LOGIN_REFRESH_LIMIT = int(os.getenv("QR_CODE_LOGIN_REFRESH_LIMIT", 1))
        self.tou_price_resolver = TimeOfUsePriceResolver()
        self.page_tracer = PageTracer(DATA_DIR / "pages")
        self.session_manager = SessionManager(
            session_file=DATA_DIR / "ha_95598_session.json",
            can_use_session=self._can_use_session,
            log_page_state=self._log_page_state,
            step_sleep=self._step_sleep,
            driver_wait_time=self.DRIVER_IMPLICITY_WAIT_TIME,
        )
        self.login_manager = LoginManager(
            credentials=self.credentials,
            session_manager=self.session_manager,
            driver_wait_time=self.DRIVER_IMPLICITY_WAIT_TIME,
            qr_wait_count=self.QR_CODE_LOGIN_WAIT_COUNT,
            qr_wait_interval=self.QR_CODE_LOGIN_WAIT_TIME_INTERVAL_UNIT,
            qr_refresh_limit=self.QR_CODE_LOGIN_REFRESH_LIMIT,
            trace_dir=self._trace_dir,
            log_page_state=self._log_page_state,
            step_sleep=self._step_sleep,
            click_button=self._click_button,
        )
        self.tencent_captcha = self.login_manager.tencent_captcha
        self.navigator = Ha95598Navigator(
            driver_wait_time=self.DRIVER_IMPLICITY_WAIT_TIME,
            login_manager=self.login_manager,
            tencent_captcha=self.tencent_captcha,
            log_page_state=self._log_page_state,
            step_sleep=self._step_sleep,
            click_button=self._click_button,
        )
        self.usage_page = UsagePage(
            navigator=self.navigator,
            log_page_state=self._log_page_state,
            step_sleep=self._step_sleep,
        )
        self._init_db()
        self.balance_fetcher = BalanceFetcher()
        self.usage_fetcher = UsageFetcher(
            driver_wait_time=self.DRIVER_IMPLICITY_WAIT_TIME,
            click_button=self._click_button,
            step_sleep=self._step_sleep,
        )
        self.monthly_bill_fetcher = MonthlyBillFetcher(
            db=self.db,
            driver_wait_time=self.DRIVER_IMPLICITY_WAIT_TIME,
            log_page_state=self._log_page_state,
            step_sleep=self._step_sleep,
        )
        self.data_persister = DataPersister(self.db, self.tou_price_resolver)
        self.ha_energy_backfiller = HaEnergyStatisticsBackfiller(self.db.db_path) if self.db is not None else None
        self.fetch_workflow = FetchWorkflow(self)

    def _init_db(self):
        self.db_type = os.getenv("DB_TYPE", "sqlite").lower()
        if self.db_type == 'sqlite':
            from scripts.support.db import SqliteDB
            self.db = SqliteDB()
            logging.info("Using SQLite database to store data.")
        else:
            self.db = None
            if self.db_type not in ('none', ''):
                logging.warning("Unsupported DB_TYPE=%s, database storage disabled.", self.db_type)
            logging.info("No database will be used to store data.")

    def _trace_dir(self) -> Path:
        return self.page_tracer.ensure_trace_dir()

    def _resolve_trace_label(self, label: Optional[str] = None) -> str:
        return self.page_tracer.resolve_label(label, caller_depth=3)

    def _log_page_state(self, driver, label: Optional[str] = None) -> None:
        self.page_tracer.log_page_state(driver, label)

    def _can_use_session(self, driver) -> bool:
        return SessionManager.is_session_usable(driver)

    def _progress_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _is_progress_current(self, progress: dict) -> bool:
        return (progress or {}).get("fetch_date") == self._progress_date()

    def _has_completed_stage(self, progress: dict, stage: str) -> bool:
        return has_completed_stage(progress, stage)

    def _known_user_ids_from_local_state(self, updater) -> list[str]:
        user_ids: list[str] = []

        def add_user_id(value) -> None:
            value = str(value or "").strip()
            if value and value not in user_ids:
                user_ids.append(value)

        try:
            cache_data = updater.cache_store.load()
            if isinstance(cache_data, dict):
                for user_id, entry in cache_data.items():
                    if isinstance(entry, dict) and entry.get("data"):
                        add_user_id(user_id)
        except Exception as exc:
            logging.debug("Failed to read known user ids from cache: %s", exc)

        try:
            if self.db is not None and getattr(self.db, "db_path", None) and self.db.db_path.exists():
                import sqlite3

                with sqlite3.connect(self.db.db_path) as conn:
                    for table in ("daily_usage", "monthly_usage", "yearly_usage"):
                        try:
                            rows = conn.execute(f"SELECT DISTINCT user_id FROM {table}").fetchall()
                        except Exception:
                            continue
                        for row in rows:
                            add_user_id(row[0])
        except Exception as exc:
            logging.debug("Failed to read known user ids from database: %s", exc)

        return user_ids

    def _step_sleep(self, driver, label: Optional[str] = None, multiplier: int = 1) -> None:
        step_label = self._resolve_trace_label(label)
        seconds = self.RETRY_WAIT_TIME_OFFSET_UNIT * multiplier
        logging.info("Sleep %ss for step [%s]", seconds, step_label)
        time.sleep(seconds)

    def _click_button(self, driver, button_search_type, button_search_key):
        """Click an element only after it becomes clickable."""
        self._log_page_state(driver, f"before_click_{button_search_key}")
        click_element = driver.find_element(button_search_type, button_search_key)
        WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(click_element))
        driver.execute_script("arguments[0].click();", click_element)

    def _get_webdriver(self):
        return create_chromium_driver(self.DRIVER_IMPLICITY_WAIT_TIME)

    def create_webdriver(self):
        return self._get_webdriver()

    def step_sleep(self, driver, label: Optional[str] = None, multiplier: int = 1) -> None:
        self._step_sleep(driver, label, multiplier)

    def log_page_state(self, driver, label: Optional[str] = None) -> None:
        self._log_page_state(driver, label)

    def _resolve_user_id_list(self, driver, updater) -> list[str]:
        local_user_ids = self._known_user_ids_from_local_state(updater)
        if local_user_ids:
            logging.info("Use %s locally known user id(s).", len(local_user_ids))
        else:
            logging.info("Try to get the userid list from page.")

        return resolve_user_ids(local_user_ids, lambda: self.navigator.get_user_ids(driver))

    def fetch(self):

        """main logic here"""

        driver = self._get_webdriver()
        ErrorWatcher.instance().set_driver(driver)
        updater = self.updater or SensorUpdater()

        failed_user_count = 0
        try:
            self._step_sleep(driver, "after_webdriver_init")
            logging.info("Webdriver initialized.")
            self.login_manager.restore_or_login(driver)

            self._step_sleep(driver, "after_login_success")
            user_id_list = self._resolve_user_id_list(driver, updater)
            if not user_id_list:
                raise RuntimeError("No user IDs were available after login")
            logging.info("Here are a total of %s userids, which are %s among which %s will be ignored.", len(user_id_list), mask_user_ids(user_id_list), mask_user_ids(self.IGNORE_USER_ID))
            self._step_sleep(driver, "after_get_user_ids")

            for userid_index, user_id in enumerate(user_id_list):
                postfix = f"_{user_id[-4:]}"
                try:
                    if user_id in self.IGNORE_USER_ID:
                        logging.info("The user ID %s will be ignored in user_id_list", mask_user_id(user_id))
                        continue

                    updater.update_fetch_status(
                        user_id,
                        postfix,
                        "running",
                        last_attempt_at=datetime.now().isoformat(timespec="seconds"),
                        stage="start",
                    )
                    progress = updater.get_progress(user_id)
                    should_open_balance_page = not (
                        self._is_progress_current(progress)
                        and self._has_completed_stage(progress, "balance")
                    )

                    if should_open_balance_page:
                        driver.get(BALANCE_URL)
                        self._log_page_state(driver, "after_open_balance_url")
                        self._step_sleep(driver, "after_open_balance_url")
                        if len(user_id_list) > 1:
                            current_userid = self.navigator.ensure_target_userid(
                                driver, userid_index, expected_user_id=user_id
                            )
                            self._step_sleep(driver, f"after_choose_balance_user_{userid_index}")
                            if current_userid in self.IGNORE_USER_ID:
                                logging.info("The user ID %s will be ignored in user_id_list", mask_user_id(current_userid))
                                continue
                        else:
                            logging.info("Skip user switching because there is only one known user.")
                    else:
                        logging.info(
                            "Skip opening balance page for %s because today's progress already passed balance stage.",
                            mask_user_id(user_id),
                        )

                    (
                        balance,
                        last_daily_date,
                        last_daily_usage,
                        last_daily_charge,
                        yearly_charge,
                        yearly_usage,
                        month_charge,
                        month_usage,
                        valley_usage,
                        flat_usage,
                        peak_usage,
                        tip_usage,
                    ) = self._get_all_data(driver, user_id, userid_index, updater)
                    updater.update_one_userid(
                        user_id=user_id,
                        balance=balance,
                        last_daily_date=last_daily_date,
                        last_daily_usage=last_daily_usage,
                        yearly_charge=yearly_charge,
                        yearly_usage=yearly_usage,
                        month_charge=month_charge,
                        month_usage=month_usage,
                        last_daily_charge=last_daily_charge,
                        valley_usage=valley_usage,
                        flat_usage=flat_usage,
                        peak_usage=peak_usage,
                        tip_usage=tip_usage,
                    )
                    if self.ha_energy_backfiller is not None:
                        self.ha_energy_backfiller.run(user_id)

                    self._step_sleep(driver, f"after_update_user_state_{mask_user_id(user_id)}")
                except Exception as e:
                    failed_user_count += 1
                    cached = updater.get_cached_user_data(user_id)
                    updater.update_fetch_status(
                        user_id,
                        postfix,
                        "failed",
                        latest_daily_date=cached.get("last_daily_date"),
                        last_success_at=cached.get("last_fetch_success_at"),
                        last_attempt_at=datetime.now().isoformat(timespec="seconds"),
                        stage=(updater.get_progress(user_id) or {}).get("stage"),
                        error_type=type(e).__name__,
                    )
                    if userid_index != len(user_id_list) - 1:
                        logging.warning(
                            "The current user %s data fetching failed (%s); continuing with the next user.",
                            mask_user_id(user_id),
                            type(e).__name__,
                        )
                    else:
                        logging.warning(
                            "The user %s data fetching failed (%s).",
                            mask_user_id(user_id),
                            type(e).__name__,
                        )
                        logging.info("Webdriver will quit after processing the user list.")
                    continue
            if failed_user_count:
                raise RuntimeError(f"{failed_user_count} user fetch(es) failed")
        except Exception as e:
            logging.error("Webdriver run failed (%s).", type(e).__name__)
            raise
        finally:
            updater.close()
            driver.quit()

    def check_cached_stale_data(self) -> None:
        updater = self.updater or SensorUpdater()
        try:
            updater.check_cached_stale_data(self.IGNORE_USER_ID)
        finally:
            if self.updater is None:
                updater.close()

    def handle_scheduled_failure(self, error_type: str) -> None:
        updater = self.updater or SensorUpdater()
        try:
            updater.mark_cached_fetches_failed(error_type, self.IGNORE_USER_ID)
        finally:
            if self.updater is None:
                updater.close()

    def _sync_monthly_bill_tou(self, driver, user_id: str):
        return self.monthly_bill_fetcher.sync(driver, user_id)

    def _select_usage_year(self, driver, target_year: int) -> bool:
        return self.usage_fetcher.select_usage_year(driver, target_year)

    def _get_all_data(self, driver, user_id, userid_index, updater: SensorUpdater):
        return self.fetch_workflow.run(driver, user_id, userid_index, updater)

    def _get_electric_balance(self, driver):
        return self.balance_fetcher.get_balance(driver)

    def _get_yearly_data(self, driver, target_year=None):
        return self.usage_fetcher.get_yearly_data(driver, target_year=target_year)

    def _get_yesterday_usage(self, driver):
        return self.usage_fetcher.get_yesterday_usage(driver)

    def _get_latest_daily_usage_breakdown(self, driver):
        return self.usage_fetcher.get_latest_daily_usage_breakdown(driver)

    def _get_recent_daily_usage_breakdown_map(self, driver, limit_days=7):
        return self.usage_fetcher.get_recent_daily_usage_breakdown_map(driver, limit_days=limit_days)

    def _set_daily_retention_days(self, driver, retention_days=30) -> bool:
        return self.usage_fetcher.set_daily_retention_days(driver, retention_days=retention_days)

    def _extract_daily_usage_rows(self, driver):
        return self.usage_fetcher.extract_daily_usage_rows(driver)

    def _get_month_usage(self, driver, target_year=None):
        return self.usage_fetcher.get_month_usage(driver, target_year=target_year)

    # 增加获取每日用电量的函数
    def _get_daily_usage_data(self, driver):
        return self.usage_fetcher.get_daily_usage_data(driver)

    @staticmethod
    def _get_daily_usage_window_days() -> int:
        return UsageFetcher.get_daily_usage_window_days()

    def _save_user_data(self, user_id, data: FetchedUserData):
        return self.data_persister.save_fetched_user_data(user_id, data)

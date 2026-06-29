import logging
from typing import Optional

from scripts.fetchers.vue_daily_range import VueDailyRangeCollector
from scripts.pages.usage_page import UsagePage
from scripts.sensor_updater import SensorUpdater
from scripts.support.error_watcher import ErrorWatcher
from scripts.support.credentials import mask_user_id
from scripts.support.ha_energy_backfiller import HaEnergyStatisticsBackfiller


class DailyRangeFetchService:
    """Independent daily range fetch flow sharing the project's common services."""

    def __init__(
        self,
        driver_factory,
        login_manager,
        navigator,
        step_sleep,
        log_page_state,
        db,
        tou_price_resolver,
        updater: Optional[SensorUpdater],
        ignore_user_ids: list[str],
    ) -> None:
        self.driver_factory = driver_factory
        self.login_manager = login_manager
        self.navigator = navigator
        self.step_sleep = step_sleep
        self.log_page_state = log_page_state
        self.db = db
        self.ha_energy_backfiller = HaEnergyStatisticsBackfiller(db.db_path) if db is not None else None
        self.tou_price_resolver = tou_price_resolver
        self.updater = updater or SensorUpdater()
        self.ignore_user_ids = ignore_user_ids
        self.usage_page = UsagePage(
            navigator=navigator,
            log_page_state=log_page_state,
            step_sleep=step_sleep,
        )
        self.collector = VueDailyRangeCollector(
            click_button=navigator.click_button,
            step_sleep=step_sleep,
            log_page_state=log_page_state,
        )

    @classmethod
    def from_data_fetcher(cls, fetcher):
        return cls(
            driver_factory=fetcher.create_webdriver,
            login_manager=fetcher.login_manager,
            navigator=fetcher.navigator,
            step_sleep=fetcher.step_sleep,
            log_page_state=fetcher.log_page_state,
            db=fetcher.db,
            tou_price_resolver=fetcher.tou_price_resolver,
            updater=fetcher.updater,
            ignore_user_ids=fetcher.IGNORE_USER_ID,
        )

    def fetch(self, start_date: str, end_date: str, user_ids: Optional[list[str]] = None):
        driver = self.driver_factory()
        ErrorWatcher.instance().set_driver(driver)
        try:
            self.step_sleep(driver, "after_range_webdriver_init")
            logging.info("Webdriver initialized for daily range fetch.")
            self.login_manager.restore_or_login(driver)
            self.step_sleep(driver, "after_range_login_success")

            discovered_user_ids = self.navigator.get_user_ids(driver)
            target_user_ids = user_ids or discovered_user_ids
            results = {}

            for user_id in target_user_ids:
                if user_id in self.ignore_user_ids:
                    logging.info("The user ID %s will be ignored in daily range fetch.", mask_user_id(user_id))
                    continue
                if user_id not in discovered_user_ids:
                    raise RuntimeError(f"user_id {mask_user_id(user_id)} was not discovered after login")

                userid_index = discovered_user_ids.index(user_id)
                self.usage_page.open_for_user(
                    driver,
                    user_id,
                    userid_index,
                    label_prefix="after_open_usage_url_for_daily_range",
                )

                rows = self.collector.collect(driver, start_date, end_date)
                persisted_count = self._persist_rows(user_id, rows)
                self._publish_refresh(user_id)
                if self.ha_energy_backfiller is not None:
                    self.ha_energy_backfiller.run(user_id)
                results[user_id] = {
                    "collected": len(rows),
                    "persisted": persisted_count,
                    "start_date": start_date,
                    "end_date": end_date,
                }
                logging.info(
                    "Daily range fetch completed for user %s: collected=%s persisted=%s range=%s~%s",
                    mask_user_id(user_id),
                    len(rows),
                    persisted_count,
                    start_date,
                    end_date,
                )
            return results
        finally:
            driver.quit()

    def _persist_rows(self, user_id: str, rows: list[dict]) -> int:
        if self.db is None:
            logging.info("Database is disabled, daily range rows will not be stored.")
            return 0
        if not self.db.connect_user_db(user_id):
            raise RuntimeError("database connection failed")

        touched_months = set()
        touched_years = set()
        persisted_count = 0
        try:
            for row in sorted(rows, key=lambda item: item["date"]):
                row_date = row["date"]
                month_usage_before = self.db.get_month_total_usage_before(row_date)
                total_charge = self.tou_price_resolver.calculate_daily_charge(
                    row_date,
                    row.get("valley_usage"),
                    row.get("flat_usage"),
                    row.get("peak_usage"),
                    row.get("tip_usage"),
                    month_usage_before,
                )
                if total_charge is not None:
                    total_charge = round(total_charge, 2)
                row["total_charge"] = total_charge
                self.db.insert_daily_data(
                    {
                        "date": row_date,
                        "total_usage": row.get("total_usage", 0.0),
                        "total_charge": total_charge,
                        "valley_usage": row.get("valley_usage", 0.0),
                        "flat_usage": row.get("flat_usage", 0.0),
                        "peak_usage": row.get("peak_usage", 0.0),
                        "tip_usage": row.get("tip_usage", 0.0),
                    }
                )
                touched_months.add(row_date[:7])
                touched_years.add(row_date[:4])
                persisted_count += 1

            for month in sorted(touched_months):
                self.db.sync_monthly_from_daily(month)
            for year in sorted(touched_years):
                self.db.sync_yearly_from_monthly(year)
        finally:
            self.db.close_connect()

        return persisted_count

    def _publish_refresh(self, user_id: str) -> None:
        if self.db is None or not self.db.connect_user_db(user_id):
            return
        try:
            latest_daily = self.db.get_latest_daily_row()
            month_summary = self.db.get_current_month_daily_summary() or self.db.get_latest_daily_month_summary()
            year_summary = self.db.get_current_year_daily_summary()
        finally:
            self.db.close_connect()

        if latest_daily is None:
            return

        cached = self.updater.get_cached_user_data(user_id)
        postfix = f"_{user_id[-4:]}"
        self.updater.update_one_userid(
            user_id=user_id,
            balance=cached.get("balance"),
            last_daily_date=latest_daily["date"],
            last_daily_usage=latest_daily["usage"],
            last_daily_charge=latest_daily["charge"],
            yearly_usage=year_summary["usage"] if year_summary else cached.get("yearly_usage"),
            yearly_charge=year_summary["charge"] if year_summary else cached.get("yearly_charge"),
            month_usage=month_summary["usage"] if month_summary else cached.get("month_usage"),
            month_charge=month_summary["charge"] if month_summary else cached.get("month_charge"),
            valley_usage=latest_daily["valley_usage"],
            flat_usage=latest_daily["flat_usage"],
            peak_usage=latest_daily["peak_usage"],
            tip_usage=latest_daily["tip_usage"],
            notify_stale=False,
        )
        self.updater.update_total_data(user_id, postfix, usage=True)
        self.updater.update_total_data(user_id, postfix, usage=False)
        self.updater.close()

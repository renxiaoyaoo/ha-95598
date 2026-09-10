import logging

from scripts.support.credentials import mask_user_id
from scripts.support.data_persister import FetchedUserData
from scripts.support.fetch_result import FetchResult


class FetchWorkflow:
    def __init__(self, fetcher) -> None:
        self.fetcher = fetcher

    def run(self, driver, user_id, userid_index, updater):
        fetcher = self.fetcher
        progress = updater.get_progress(user_id)
        cached = updater.get_cached_user_data(user_id)
        if not fetcher._is_progress_current(progress):
            updater.update_progress_stage(user_id, "none", fetch_date=fetcher._progress_date())
            progress = updater.get_progress(user_id)
            cached = updater.get_cached_user_data(user_id)

        cached_balance = cached.get("balance")
        balance = cached_balance
        if fetcher._has_completed_stage(progress, "balance"):
            logging.info("Skip balance fetch for %s because today's progress already exists.", mask_user_id(user_id))
        else:
            fetched_balance = fetcher._get_electric_balance(driver)
            if fetched_balance is None:
                if cached_balance is None:
                    logging.warning("Get electricity charge balance for %s failed, no cached balance available.", mask_user_id(user_id))
                else:
                    logging.warning("Get electricity charge balance for %s failed, keep cached balance.", mask_user_id(user_id))
            else:
                balance = fetched_balance
                logging.info("Updated electricity balance for %s.", mask_user_id(user_id))
                updater.save_partial_data(user_id, balance=balance)
                updater.update_progress_stage(user_id, "balance", fetch_date=fetcher._progress_date())
                progress = updater.get_progress(user_id)

        fetcher.usage_page.open_for_user(driver, user_id, userid_index)

        yearly_usage = cached.get("yearly_usage")
        yearly_charge = cached.get("yearly_charge")
        if fetcher._has_completed_stage(progress, "yearly"):
            logging.info("Skip yearly fetch for %s because today's progress already exists.", mask_user_id(user_id))
        else:
            yearly_usage, yearly_charge = fetcher._get_yearly_data(driver)

            if yearly_usage is None:
                logging.error("Get year power usage for %s failed, pass", mask_user_id(user_id))
            else:
                logging.info("Updated yearly electricity usage for %s.", mask_user_id(user_id))
            if yearly_charge is None:
                logging.error("Get year power charge for %s failed, pass", mask_user_id(user_id))
            else:
                logging.info("Updated yearly electricity charge for %s.", mask_user_id(user_id))
            updater.save_partial_data(user_id, yearly_usage=yearly_usage, yearly_charge=yearly_charge)
            updater.update_progress_stage(user_id, "yearly", fetch_date=fetcher._progress_date())
            progress = updater.get_progress(user_id)

        month = None
        month_usage = None
        month_charge = None
        if fetcher._has_completed_stage(progress, "monthly"):
            logging.info("Skip monthly fetch for %s because today's progress already exists.", mask_user_id(user_id))
            if cached.get("month_usage") is not None:
                month_usage = [cached.get("month_usage")]
            if cached.get("month_charge") is not None:
                month_charge = [cached.get("month_charge")]
        else:
            month, month_usage, month_charge = fetcher._get_month_usage(driver)
            if month is None:
                logging.error("Get month power usage for %s failed, pass", mask_user_id(user_id))
            else:
                logging.info("Updated %s monthly usage row(s) for %s.", len(month), mask_user_id(user_id))
                updater.save_partial_data(
                    user_id,
                    month_usage=month_usage[-1] if month_usage else None,
                    month_charge=month_charge[-1] if month_charge else None,
                )
                updater.update_progress_stage(user_id, "monthly", fetch_date=fetcher._progress_date())
                progress = updater.get_progress(user_id)

        last_daily_date = cached.get("last_daily_date")
        last_daily_usage = cached.get("last_daily_usage")
        if fetcher._has_completed_stage(progress, "daily"):
            logging.info("Skip daily fetch for %s because today's progress already exists.", mask_user_id(user_id))
        else:
            last_daily_date, last_daily_usage = fetcher._get_yesterday_usage(driver)
            if last_daily_usage is None:
                logging.error("Get daily power consumption for %s failed, pass", mask_user_id(user_id))
            else:
                logging.info("Updated latest daily usage for %s (%s).", mask_user_id(user_id), last_daily_date)
                updater.save_partial_data(
                    user_id,
                    last_daily_date=last_daily_date,
                    last_daily_usage=last_daily_usage,
                )
                updater.update_progress_stage(user_id, "daily", fetch_date=fetcher._progress_date())
                progress = updater.get_progress(user_id)

        valley_usage = cached.get("valley_usage")
        flat_usage = cached.get("flat_usage")
        peak_usage = cached.get("peak_usage")
        tip_usage = cached.get("tip_usage")
        daily_tou_map = {}
        if fetcher._has_completed_stage(progress, "tou"):
            logging.info("Skip TOU fetch for %s because today's progress already exists.", mask_user_id(user_id))
        else:
            daily_tou_map = fetcher._get_recent_daily_usage_breakdown_map(driver, limit_days=7)
            latest_tou = daily_tou_map.get(last_daily_date) if last_daily_date else None
            if latest_tou:
                valley_usage = latest_tou.get("valley_usage")
                flat_usage = latest_tou.get("flat_usage")
                peak_usage = latest_tou.get("peak_usage")
                tip_usage = latest_tou.get("tip_usage")
            else:
                valley_usage, flat_usage, peak_usage, tip_usage = fetcher._get_latest_daily_usage_breakdown(driver)
                if last_daily_date and any(value is not None for value in (valley_usage, flat_usage, peak_usage, tip_usage)):
                    daily_tou_map[last_daily_date] = {
                        "valley_usage": valley_usage or 0.0,
                        "flat_usage": flat_usage or 0.0,
                        "peak_usage": peak_usage or 0.0,
                        "tip_usage": tip_usage or 0.0,
                    }

            if daily_tou_map or any(value is not None for value in (valley_usage, flat_usage, peak_usage, tip_usage)):
                logging.info(
                    "Updated recent time-of-use data for %s (%s day(s)).",
                    mask_user_id(user_id),
                    len(daily_tou_map),
                )
                updater.save_partial_data(
                    user_id,
                    valley_usage=valley_usage,
                    flat_usage=flat_usage,
                    peak_usage=peak_usage,
                    tip_usage=tip_usage,
                )
                updater.update_progress_stage(user_id, "tou", fetch_date=fetcher._progress_date())
                progress = updater.get_progress(user_id)
            else:
                logging.error("Get latest time-of-use power usage for %s failed, pass", mask_user_id(user_id))

        last_daily_charge = None

        if fetcher.db is not None:
            logging.info("db is %s, we will store the data to the database.", fetcher.db_type)
            date, usages = fetcher._get_daily_usage_data(driver)
            last_daily_charge = fetcher._save_user_data(
                user_id,
                FetchedUserData(
                    last_daily_date=last_daily_date,
                    last_daily_usage=last_daily_usage,
                    last_daily_charge=last_daily_charge,
                    daily_dates=date,
                    daily_usages=usages,
                    months=month,
                    month_usage=month_usage,
                    month_charge=month_charge,
                    yearly_charge=yearly_charge,
                    yearly_usage=yearly_usage,
                    valley_usage=valley_usage,
                    flat_usage=flat_usage,
                    peak_usage=peak_usage,
                    tip_usage=tip_usage,
                    daily_tou_map=daily_tou_map,
                ),
            )
            updater.save_partial_data(user_id, last_daily_charge=last_daily_charge)
            updater.update_progress_stage(user_id, "persist", fetch_date=fetcher._progress_date())
            progress = updater.get_progress(user_id)
        else:
            logging.info("db is None, we will not store the data to the database.")

        if fetcher.db is not None:
            if fetcher._has_completed_stage(progress, "billing"):
                logging.info("Skip monthly billing TOU fetch for %s because today's progress already exists.", mask_user_id(user_id))
            else:
                bill_rows, bill_verified = fetcher._sync_monthly_bill_tou(driver, user_id)
                if bill_rows:
                    months = ", ".join(row["month"] for row in bill_rows)
                    logging.info("Synced monthly bill TOU for %s: %s", mask_user_id(user_id), months)
                elif bill_verified:
                    logging.info("Monthly bill TOU check completed for %s with no new data.", mask_user_id(user_id))
                else:
                    logging.warning("Monthly bill TOU check did not complete for %s", mask_user_id(user_id))
                if bill_verified:
                    updater.update_progress_stage(user_id, "billing", fetch_date=fetcher._progress_date())
                    progress = updater.get_progress(user_id)

        if fetcher.db is None or fetcher._has_completed_stage(progress, "billing"):
            updater.update_progress_stage(user_id, "complete", fetch_date=fetcher._progress_date())

        if month_charge:
            month_charge = month_charge[-1]
        else:
            month_charge = None
        if month_usage:
            month_usage = month_usage[-1]
        else:
            month_usage = None

        return FetchResult(
            balance=balance,
            last_daily_date=last_daily_date,
            last_daily_usage=last_daily_usage,
            last_daily_charge=last_daily_charge,
            yearly_charge=yearly_charge,
            yearly_usage=yearly_usage,
            month_charge=month_charge,
            month_usage=month_usage,
            valley_usage=valley_usage,
            flat_usage=flat_usage,
            peak_usage=peak_usage,
            tip_usage=tip_usage,
        )

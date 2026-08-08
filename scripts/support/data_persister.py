import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Optional

from scripts.support.db import SqliteDB
from scripts.support.monthly_billing import MonthlyBillingService
from scripts.support.tou_price import TimeOfUsePriceResolver


@dataclass
class FetchedUserData:
    last_daily_date: str | None = None
    last_daily_usage: Any = None
    last_daily_charge: Any = None
    daily_dates: list[Any] | None = None
    daily_usages: list[Any] | None = None
    months: list[Any] | None = None
    month_usage: list[Any] | None = None
    month_charge: list[Any] | None = None
    yearly_charge: Any = None
    yearly_usage: Any = None
    valley_usage: Any = None
    flat_usage: Any = None
    peak_usage: Any = None
    tip_usage: Any = None
    daily_tou_map: dict[str, dict[str, Any]] = field(default_factory=dict)


class DataPersister:
    def __init__(self, db: Optional[SqliteDB], tou_price_resolver: TimeOfUsePriceResolver):
        self.db = db
        self.tou_price_resolver = tou_price_resolver

    @staticmethod
    def _normalize_month_value(raw_month, reference_year):
        return MonthlyBillingService.normalize_month_value(raw_month, reference_year)

    def _calculate_latest_daily_charge(
        self,
        last_daily_date,
        valley_usage,
        flat_usage,
        peak_usage,
        tip_usage,
        month_usage_before,
    ):
        if last_daily_date is None:
            return None
        if all(value is None for value in (valley_usage, flat_usage, peak_usage, tip_usage)):
            return None

        daily_charge = self.tou_price_resolver.calculate_daily_charge(
            last_daily_date,
            valley_usage,
            flat_usage,
            peak_usage,
            tip_usage,
            month_usage_before,
        )
        if daily_charge is not None:
            logging.info("Calculated daily TOU charge for %s: %.2f CNY", last_daily_date, daily_charge)
        else:
            logging.info("No matching TOU tariff config found for %s", last_daily_date)
        return daily_charge

    def save_user_data(
        self,
        user_id,
        last_daily_date,
        last_daily_usage,
        last_daily_charge,
        date,
        usages,
        month,
        month_usage,
        month_charge,
        yearly_charge,
        yearly_usage,
        valley_usage,
        flat_usage,
        peak_usage,
        tip_usage,
        daily_tou_map=None,
    ):
        return self.save_fetched_user_data(
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
                daily_tou_map=daily_tou_map or {},
            ),
        )

    def save_fetched_user_data(self, user_id, data: FetchedUserData):
        last_daily_date = data.last_daily_date
        last_daily_usage = data.last_daily_usage
        last_daily_charge = data.last_daily_charge
        date = data.daily_dates
        usages = data.daily_usages
        month = data.months
        month_usage = data.month_usage
        month_charge = data.month_charge
        yearly_charge = data.yearly_charge
        yearly_usage = data.yearly_usage
        valley_usage = data.valley_usage
        flat_usage = data.flat_usage
        peak_usage = data.peak_usage
        tip_usage = data.tip_usage
        daily_tou_map = data.daily_tou_map or {}

        if self.db is None:
            return last_daily_charge

        if not self.db.connect_user_db(user_id):
            logging.info("The database creation failed and the data was not written correctly.")
            return last_daily_charge

        try:
            billing = MonthlyBillingService(self.db)

            if date:
                for index in range(len(date)):
                    existing_tou = self.db.get_daily_tou_values(date[index])
                    row_tou = daily_tou_map.get(date[index], {})
                    payload = {
                        "date": date[index],
                        "total_usage": float(usages[index]),
                        "total_charge": None,
                        "valley_usage": row_tou.get("valley_usage", existing_tou.get("valley_usage", 0.0)),
                        "flat_usage": row_tou.get("flat_usage", existing_tou.get("flat_usage", 0.0)),
                        "peak_usage": row_tou.get("peak_usage", existing_tou.get("peak_usage", 0.0)),
                        "tip_usage": row_tou.get("tip_usage", existing_tou.get("tip_usage", 0.0)),
                    }
                    if date[index] == last_daily_date:
                        payload.update(
                            {
                                "total_charge": last_daily_charge,
                                "valley_usage": valley_usage or 0,
                                "flat_usage": flat_usage or 0,
                                "peak_usage": peak_usage or 0,
                                "tip_usage": tip_usage or 0,
                            }
                        )
                    self.db.insert_daily_data(payload)
                    logging.info(
                        "The electricity consumption of %sKWh on %s has been successfully deposited into the database",
                        usages[index],
                        date[index],
                    )
            elif last_daily_date and last_daily_usage is not None:
                self.db.insert_daily_data(
                    {
                        "date": last_daily_date,
                        "total_usage": last_daily_usage,
                        "total_charge": last_daily_charge,
                        "valley_usage": valley_usage or 0,
                        "flat_usage": flat_usage or 0,
                        "peak_usage": peak_usage or 0,
                        "tip_usage": tip_usage or 0,
                    }
                )

            if daily_tou_map:
                for row_date in sorted(daily_tou_map.keys()):
                    tou_values = daily_tou_map[row_date]
                    daily_row = self.db.get_period_row("daily_usage", "date", row_date)
                    if not daily_row or daily_row.get("total_usage") is None:
                        continue
                    month_usage_before = self.db.get_month_total_usage_before(row_date)
                    row_charge = self.tou_price_resolver.calculate_daily_charge(
                        row_date,
                        tou_values.get("valley_usage"),
                        tou_values.get("flat_usage"),
                        tou_values.get("peak_usage"),
                        tou_values.get("tip_usage"),
                        month_usage_before,
                    )
                    self.db.insert_daily_data(
                        {
                            "date": row_date,
                            "total_usage": daily_row["total_usage"],
                            "total_charge": row_charge,
                            "valley_usage": tou_values.get("valley_usage", 0.0),
                            "flat_usage": tou_values.get("flat_usage", 0.0),
                            "peak_usage": tou_values.get("peak_usage", 0.0),
                            "tip_usage": tou_values.get("tip_usage", 0.0),
                        }
                    )
                    if row_date == last_daily_date:
                        last_daily_charge = row_charge
                        valley_usage = tou_values.get("valley_usage", 0.0)
                        flat_usage = tou_values.get("flat_usage", 0.0)
                        peak_usage = tou_values.get("peak_usage", 0.0)
                        tip_usage = tou_values.get("tip_usage", 0.0)
            else:
                month_usage_before = self.db.get_month_total_usage_before(last_daily_date) if last_daily_date else 0.0
                last_daily_charge = self._calculate_latest_daily_charge(
                    last_daily_date,
                    valley_usage,
                    flat_usage,
                    peak_usage,
                    tip_usage,
                    month_usage_before,
                )
                if last_daily_date and last_daily_usage is not None and last_daily_charge is not None:
                    self.db.insert_daily_data(
                        {
                            "date": last_daily_date,
                            "total_usage": last_daily_usage,
                            "total_charge": last_daily_charge,
                            "valley_usage": valley_usage or 0,
                            "flat_usage": flat_usage or 0,
                            "peak_usage": peak_usage or 0,
                            "tip_usage": tip_usage or 0,
                        }
                    )

            if month:
                reference_year = str(last_daily_date)[:4] if last_daily_date else datetime.now().strftime("%Y")
                for index in range(len(month)):
                    try:
                        billing.upsert_visible_month(
                            month=month[index],
                            total_usage=month_usage[index],
                            total_charge=month_charge[index],
                            reference_year=reference_year,
                        )
                    except Exception as exc:
                        logging.debug("The electricity consumption of %s failed to save to the database: %s", month[index], exc)

            current_month_key = str(last_daily_date)[:7] if last_daily_date else None
            if current_month_key:
                billing.upsert_calculated_from_daily(current_month_key)

            if yearly_usage is not None:
                if last_daily_date:
                    year = str(last_daily_date)[:4]
                elif month:
                    year = str(month[0]).strip()[:4]
                else:
                    year = datetime.now().strftime("%Y")
                existing_tou = self.db.get_period_tou_values("yearly_usage", "year", year)
                self.db.insert_yearly_data(
                    {
                        "year": year,
                        "total_usage": yearly_usage,
                        "total_charge": yearly_charge,
                        "valley_usage": existing_tou.get("valley_usage", 0.0),
                        "flat_usage": existing_tou.get("flat_usage", 0.0),
                        "peak_usage": existing_tou.get("peak_usage", 0.0),
                        "tip_usage": existing_tou.get("tip_usage", 0.0),
                    }
                )

            if current_month_key:
                billing.refresh_year(current_month_key[:4])
            elif month:
                billing.refresh_years_for_months(month, datetime.now().strftime("%Y"))
        finally:
            self.db.close_connect()

        return last_daily_charge

import logging
import re
from datetime import datetime
from typing import Any, Optional

from scripts.support.db import SqliteDB
from scripts.support.tou_price import TimeOfUsePriceResolver


class DataPersister:
    def __init__(self, db: Optional[SqliteDB], tou_price_resolver: TimeOfUsePriceResolver):
        self.db = db
        self.tou_price_resolver = tou_price_resolver

    @staticmethod
    def _normalize_month_value(raw_month, reference_year):
        month_text = str(raw_month).strip()
        if full_match := re.search(r"(\d{4}-\d{2})", month_text):
            return full_match.group(1)
        month_match = re.search(r"(\d{1,2})", month_text)
        if month_match and reference_year:
            return f"{reference_year}-{int(month_match.group(1)):02d}"
        return month_text

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
        if self.db is None:
            return last_daily_charge

        daily_tou_map = daily_tou_map or {}

        if not self.db.connect_user_db(user_id):
            logging.info("The database creation failed and the data was not written correctly.")
            return last_daily_charge

        try:
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
                        month_key = self._normalize_month_value(month[index], reference_year)
                        existing_tou = self.db.get_period_tou_values("monthly_usage", "month", month_key)
                        self.db.insert_monthly_data(
                            {
                                "month": month_key,
                                "total_usage": month_usage[index],
                                "total_charge": month_charge[index],
                                "valley_usage": existing_tou.get("valley_usage", 0.0),
                                "flat_usage": existing_tou.get("flat_usage", 0.0),
                                "peak_usage": existing_tou.get("peak_usage", 0.0),
                                "tip_usage": existing_tou.get("tip_usage", 0.0),
                            }
                        )
                    except Exception as exc:
                        logging.debug("The electricity consumption of %s failed to save to the database: %s", month[index], exc)

            current_month_key = str(last_daily_date)[:7] if last_daily_date else None
            if current_month_key:
                self.db.upsert_calculated_monthly_from_daily(current_month_key)

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
                self.db.refresh_year_from_months(current_month_key[:4])
            elif month:
                for month_value in month:
                    normalized_month = self._normalize_month_value(month_value, datetime.now().strftime("%Y"))
                    self.db.refresh_year_from_months(normalized_month[:4])
        finally:
            self.db.close_connect()

        return last_daily_charge

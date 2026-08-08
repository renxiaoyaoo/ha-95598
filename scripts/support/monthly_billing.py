from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Iterable

from scripts.support.data_rows import MonthlyBillRow, MonthlyUsageRow


class MonthlyBillingService:
    def __init__(self, db) -> None:
        self.db = db

    @staticmethod
    def normalize_month_value(raw_month: Any, reference_year: str | int | None) -> str:
        month_text = str(raw_month).strip()
        if len(month_text) >= 7 and month_text[:4].isdigit() and month_text[4] == "-" and month_text[5:7].isdigit():
            return month_text[:7]

        if full_match := re.search(r"(\d{4}-\d{2})", month_text):
            return full_match.group(1)
        month_match = re.search(r"(\d{1,2})", month_text)
        if month_match and reference_year:
            return f"{str(reference_year)[:4]}-{int(month_match.group(1)):02d}"
        return month_text

    def upsert_visible_month(
        self,
        *,
        month: Any,
        total_usage: Any,
        total_charge: Any,
        reference_year: str | int | None,
    ) -> str:
        month_key = self.normalize_month_value(month, reference_year)
        existing_tou = self.db.get_period_tou_values("monthly_usage", "month", month_key)
        self.db.insert_monthly_data(
            MonthlyUsageRow(
                month=month_key,
                total_usage=total_usage,
                total_charge=total_charge,
                valley_usage=existing_tou.get("valley_usage", 0.0),
                flat_usage=existing_tou.get("flat_usage", 0.0),
                peak_usage=existing_tou.get("peak_usage", 0.0),
                tip_usage=existing_tou.get("tip_usage", 0.0),
            ).to_dict()
        )
        return month_key

    def upsert_official_bill(self, row: dict[str, Any]) -> str:
        month_key = str(row["month"]).strip()
        existing = self.db.get_period_row("monthly_usage", "month", month_key) or {}
        self.db.upsert_official_monthly_bill(
            MonthlyBillRow(
                month=month_key,
                total_usage=row.get("total_usage")
                if row.get("total_usage") is not None
                else existing.get("total_usage", 0.0),
                total_charge=row.get("total_charge")
                if row.get("total_charge") is not None
                else existing.get("total_charge"),
                valley_usage=row.get("valley_usage", 0.0),
                flat_usage=row.get("flat_usage", 0.0),
                peak_usage=row.get("peak_usage", 0.0),
                tip_usage=row.get("tip_usage", 0.0),
            ).to_official_dict()
        )
        return month_key

    def upsert_calculated_from_daily(self, month: str | None) -> bool:
        if not month:
            return False
        return self.db.upsert_calculated_monthly_from_daily(month)

    def refresh_year(self, year: str | int | None) -> bool:
        if not year:
            return False
        return self.db.refresh_year_from_months(str(year)[:4])

    def refresh_years_for_months(self, months: Iterable[Any], reference_year: str | int | None = None) -> None:
        fallback_year = str(reference_year or datetime.now().year)[:4]
        years = {
            self.normalize_month_value(month, fallback_year)[:4]
            for month in months
            if month is not None
        }
        for year in sorted(years):
            self.refresh_year(year)

    def upsert_official_bills_and_refresh_years(self, rows: Iterable[dict[str, Any]]) -> set[str]:
        touched_years: set[str] = set()
        for row in rows:
            try:
                month_key = self.upsert_official_bill(row)
                touched_years.add(month_key[:4])
            except Exception as exc:
                logging.debug("Failed to save official monthly bill row: %s", exc)

        for year in sorted(touched_years):
            self.refresh_year(year)
        return touched_years

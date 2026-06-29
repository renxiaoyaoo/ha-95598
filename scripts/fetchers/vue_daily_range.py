import logging
from datetime import datetime
from typing import Any

from selenium.webdriver.common.by import By


class VueDailyRangeCollector:
    """Collect daily usage rows by invoking the 95598 daily Vue component."""

    def __init__(self, click_button, step_sleep, log_page_state):
        self._click_button = click_button
        self._step_sleep = step_sleep
        self._log_page_state = log_page_state

    def collect(self, driver, start_date: str, end_date: str) -> list[dict[str, Any]]:
        self._validate_date(start_date)
        self._validate_date(end_date)
        if start_date > end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")

        self._click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-second']")
        self._step_sleep(driver, "after_open_daily_tab_for_range")

        result = self._query_vue_daily_range(driver, start_date, end_date)
        rows = [self._normalize_row(row) for row in result]
        rows = [row for row in rows if row is not None]
        rows.sort(key=lambda row: row["date"])
        logging.info(
            "Collected %s daily usage rows from 95598 range %s to %s.",
            len(rows),
            start_date,
            end_date,
        )
        return rows

    def _query_vue_daily_range(self, driver, start_date: str, end_date: str) -> list[dict[str, Any]]:
        script = """
        const start = arguments[0];
        const end = arguments[1];
        const candidates = Array.from(document.querySelectorAll('*'))
          .map((el) => el.__vue__)
          .filter((vm) => vm && typeof vm.getdata === 'function' && Array.isArray(vm.sevenEleList));
        const vm = candidates.find((item) =>
          Object.prototype.hasOwnProperty.call(item, 'start') &&
          Object.prototype.hasOwnProperty.call(item, 'end')
        ) || candidates[0];
        if (!vm) {
          return { ok: false, reason: 'daily_vue_component_not_found' };
        }
        vm.start = start;
        vm.end = end;
        vm.dateradio = '';
        vm.sevenEleList = [];
        vm.getdata();
        return { ok: true, start: vm.start, end: vm.end };
        """
        result = driver.execute_script(script, start_date, end_date)
        if not result or not result.get("ok"):
            self._log_page_state(driver, "daily_range_vue_not_found")
            raise RuntimeError((result or {}).get("reason", "daily range Vue component not found"))
        self._step_sleep(driver, "after_query_daily_range")

        rows = driver.execute_script(
            """
            const candidates = Array.from(document.querySelectorAll('*'))
              .map((el) => el.__vue__)
              .filter((vm) => vm && Array.isArray(vm.sevenEleList));
            const vm = candidates.find((item) =>
              Object.prototype.hasOwnProperty.call(item, 'start') &&
              Object.prototype.hasOwnProperty.call(item, 'end')
            ) || candidates[0];
            if (!vm) return [];
            return (vm.sevenEleList || []).map((row) => ({
              date: row.day,
              total_usage: row.dayElePq,
              valley_usage: row.thisVPq,
              flat_usage: row.thisNPq,
              peak_usage: row.thisPPq,
              tip_usage: row.thisTPq,
            }));
            """
        )
        return rows or []

    @staticmethod
    def _validate_date(date_text: str) -> None:
        datetime.strptime(date_text, "%Y-%m-%d")

    @classmethod
    def _normalize_row(cls, row: dict[str, Any]) -> dict[str, Any] | None:
        date_text = str(row.get("date") or "").strip()
        if not date_text:
            return None
        usage_values = [
            row.get("total_usage"),
            row.get("valley_usage"),
            row.get("flat_usage"),
            row.get("peak_usage"),
            row.get("tip_usage"),
        ]
        # The site includes an unfinished day as a dated row with every value blank.
        # Keep explicit 0.00 readings, but do not persist this placeholder as real usage.
        if all(cls._is_missing_value(value) for value in usage_values):
            return None
        return {
            "date": date_text,
            "total_usage": cls._safe_float(row.get("total_usage"), 0.0),
            "valley_usage": cls._safe_float(row.get("valley_usage"), 0.0),
            "flat_usage": cls._safe_float(row.get("flat_usage"), 0.0),
            "peak_usage": cls._safe_float(row.get("peak_usage"), 0.0),
            "tip_usage": cls._safe_float(row.get("tip_usage"), 0.0),
        }

    @staticmethod
    def _is_missing_value(value: Any) -> bool:
        return value is None or str(value).strip() in ("", "-", "—", "None")

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            text = str(value).strip()
            if text in ("", "-", "—", "None"):
                return default
            return float(text)
        except (TypeError, ValueError):
            return default

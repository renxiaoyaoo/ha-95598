import logging
import re
from datetime import datetime
from typing import Any, Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from scripts.const import ELECTRIC_BILL_SUMMARY_URL
from scripts.fetchers.vue_state import normalize_bill_detail, selected_vue_data


class MonthlyBillFetcher:
    def __init__(
        self,
        *,
        db,
        driver_wait_time: int,
        log_page_state: Callable[[Any, str], None],
        step_sleep: Callable[[Any, str], None],
    ) -> None:
        self.db = db
        self.driver_wait_time = driver_wait_time
        self.log_page_state = log_page_state
        self.step_sleep = step_sleep

    def open_summary_page(self, driver) -> None:
        driver.get(ELECTRIC_BILL_SUMMARY_URL)
        self.log_page_state(driver, "after_open_bill_summary_url")
        self.step_sleep(driver, "after_open_bill_summary_url")
        WebDriverWait(driver, self.driver_wait_time).until(
            EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'billContent_bill')]"))
        )

    def sync(self, driver, user_id: str):
        if self.db is None:
            return [], False
        if not self.db.connect_user_db(user_id):
            return [], False
        rows = []
        touched_years = set()
        verified = False
        try:
            self.open_summary_page(driver)
            available_years = self.get_available_years(driver)
            current_year = datetime.now().year
            current_month = datetime.now().month
            target_years = [year for year in available_years if year == current_year]
            if current_month <= 2 and (current_year - 1) in available_years:
                target_years.append(current_year - 1)

            for target_year in target_years:
                if not self.select_year(driver, target_year):
                    continue
                verified = True

                existing_year = self.db.get_period_row("yearly_usage", "year", str(target_year))
                needs_deep_sync = not self._row_has_nonzero_tou(existing_year)

                visible_months = self.get_visible_month_keys(driver)
                pending_months = [month_key for month_key in visible_months if self._needs_sync(month_key)]

                if needs_deep_sync:
                    self.expand_summary(driver)
                    visible_months = self.get_visible_month_keys(driver)
                    pending_months = [month_key for month_key in visible_months if self._needs_sync(month_key)]

                if not pending_months:
                    logging.info("Monthly bill TOU is already complete for visible months in %s.", target_year)
                    continue

                for bill_index, month_key in enumerate(visible_months):
                    if month_key not in pending_months:
                        continue
                    if not self.open_detail_by_index(driver, bill_index):
                        continue
                    detail = self.parse_detail(driver)
                    if detail is not None:
                        rows.append(detail)
                    driver.back()
                    self.step_sleep(driver, f"after_return_bill_summary_{target_year}_{bill_index}")
                    WebDriverWait(driver, self.driver_wait_time).until(
                        EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'billContent_bill')]"))
                    )
                    if needs_deep_sync:
                        self.expand_summary(driver)

            for row in rows:
                existing = self.db.get_period_row("monthly_usage", "month", row["month"]) or {}
                self.db.upsert_official_monthly_bill(
                    {
                        "month": row["month"],
                        "total_usage": row.get("total_usage")
                        if row.get("total_usage") is not None
                        else existing.get("total_usage", 0.0),
                        "total_charge": row.get("total_charge")
                        if row.get("total_charge") is not None
                        else existing.get("total_charge"),
                        "valley_usage": row.get("valley_usage", 0.0),
                        "flat_usage": row.get("flat_usage", 0.0),
                        "peak_usage": row.get("peak_usage", 0.0),
                        "tip_usage": row.get("tip_usage", 0.0),
                    }
                )
                touched_years.add(row["month"][:4])

            for year in sorted(touched_years):
                self.db.refresh_year_from_months(year)
        finally:
            self.db.close_connect()

        return rows, verified

    def get_available_years(self, driver) -> list[int]:
        years = []
        year_nodes = WebDriverWait(driver, self.driver_wait_time).until(
            EC.visibility_of_all_elements_located(
                (By.XPATH, "//div[contains(@class,'billList_timeSelection')]//div[contains(@class,'content_year')]/span")
            )
        )
        for option in year_nodes:
            try:
                years.append(int(option.text.strip().replace("年", "")))
            except (TypeError, ValueError):
                continue
        return sorted(set(years), reverse=True)

    def select_year(self, driver, target_year: int) -> bool:
        target_year = int(target_year)
        try:
            active_year = driver.find_element(
                By.XPATH,
                "//div[contains(@class,'billList_timeSelection')]//div[contains(@class,'content_sleectYear')]/span",
            ).text.strip()
            if active_year == f"{target_year}年":
                return True

            option = WebDriverWait(driver, self.driver_wait_time).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        f"//div[contains(@class,'billList_timeSelection')]//div[contains(@class,'content_year')]/span[normalize-space()='{target_year}年']",
                    )
                )
            )
            driver.execute_script("arguments[0].click();", option)
            self.step_sleep(driver, f"after_select_bill_year_{target_year}")
            WebDriverWait(driver, self.driver_wait_time).until(
                lambda d: d.find_element(
                    By.XPATH,
                    "//div[contains(@class,'billList_timeSelection')]//div[contains(@class,'content_sleectYear')]/span",
                ).text.strip()
                == f"{target_year}年"
            )
            WebDriverWait(driver, self.driver_wait_time).until(
                EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'billContent_bill')]"))
            )
            return True
        except Exception as exc:
            logging.warning("Failed to switch bill year to %s: %s", target_year, exc)
            return False

    def expand_summary(self, driver) -> None:
        for _ in range(6):
            buttons = driver.find_elements(By.XPATH, "//div[contains(@class,'content_button')]//*[contains(text(),'查看更多')]")
            if not buttons:
                return
            previous_count = len(driver.find_elements(By.XPATH, "//div[contains(@class,'billContent_bill')]"))
            driver.execute_script("arguments[0].click();", buttons[0])
            self.step_sleep(driver, "after_expand_bill_summary")
            current_count = len(driver.find_elements(By.XPATH, "//div[contains(@class,'billContent_bill')]"))
            if current_count <= previous_count:
                return

    def get_visible_month_keys(self, driver) -> list[str]:
        month_keys = []
        month_nodes = driver.find_elements(By.XPATH, "//div[contains(@class,'bill_time')]/span[1]")
        for node in month_nodes:
            month_key = self.parse_month_key(node.text)
            if month_key:
                month_keys.append(month_key)
        return month_keys

    def open_detail_by_index(self, driver, bill_index: int) -> bool:
        month_rows = driver.find_elements(By.XPATH, "//div[contains(@class,'billList_content')]")
        if bill_index >= len(month_rows):
            return False
        arrow = month_rows[bill_index].find_element(By.XPATH, ".//img[contains(@class,'back_right')]")
        driver.execute_script("arguments[0].click();", arrow)
        self.step_sleep(driver, f"after_open_bill_detail_{bill_index}")
        WebDriverWait(driver, self.driver_wait_time).until(
            EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'billInfo_cycle')]"))
        )
        return True

    def parse_detail(self, driver):
        try:
            detail = normalize_bill_detail(selected_vue_data(driver))
            if detail.get("month"):
                return {
                    "month": detail.get("month"),
                    "total_usage": detail.get("usage"),
                    "total_charge": detail.get("charge"),
                    "valley_usage": detail.get("valley_usage") or 0.0,
                    "flat_usage": detail.get("flat_usage") or 0.0,
                    "peak_usage": detail.get("peak_usage") or 0.0,
                    "tip_usage": detail.get("tip_usage") or 0.0,
                }
        except Exception as exc:
            logging.debug("Failed to parse monthly bill detail from Vue state, fallback to DOM: %s", exc)

        try:
            cycle_text = driver.find_element(By.XPATH, "//div[contains(@class,'billInfo_cycle')]").text
            month_key = self.parse_month_key(cycle_text)
            if month_key is None:
                return None

            total_usage = self._read_total_usage(driver)
            tou_values = self._read_tou_values(driver)
            if total_usage is None:
                total_usage = round(sum(tou_values.values()), 2)

            return {
                "month": month_key,
                "total_usage": total_usage,
                "total_charge": self._read_total_charge(driver),
                **tou_values,
            }
        except Exception as exc:
            logging.warning("Failed to parse monthly bill detail: %s", exc)
            return None

    def parse_month_key(self, bill_time_text: str) -> str | None:
        match = re.search(r"(\d{4})/(\d{2})/\d{2}", str(bill_time_text).strip())
        if not match:
            return None
        return f"{match.group(1)}-{match.group(2)}"

    def _needs_sync(self, month_key: str) -> bool:
        return not self.db.is_official_monthly_bill(month_key)

    def _row_has_nonzero_tou(self, row) -> bool:
        if not row:
            return False
        return any(float(row.get(field, 0.0) or 0.0) > 0 for field in ("valley_usage", "flat_usage", "peak_usage", "tip_usage"))

    def _read_total_usage(self, driver):
        try:
            total_usage_text = driver.find_element(
                By.XPATH,
                "//span[contains(text(),'正向有功(总)')]/ancestor::div[contains(@class,'item_item')][1]/span[contains(@class,'thisReadPq')]",
            ).text
            return float(total_usage_text.strip())
        except Exception:
            return None

    def _read_tou_values(self, driver) -> dict[str, float]:
        tou_values = {
            "valley_usage": 0.0,
            "flat_usage": 0.0,
            "peak_usage": 0.0,
            "tip_usage": 0.0,
        }
        tou_items = driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'wrap_pvQtyJm')]//div[contains(@class,'right_top')]//div[contains(@class,'top_item')]",
        )
        for item in tou_items:
            label = item.find_element(By.XPATH, ".//span[contains(@class,'name')]").text.strip()
            value_text = item.find_element(By.XPATH, ".//div[contains(@class,'item_right')]/span").text.strip()
            value = float(value_text or 0)
            if "低谷" in label or "谷" in label:
                tou_values["valley_usage"] = value
            elif "平" in label:
                tou_values["flat_usage"] = value
            elif "峰" in label:
                tou_values["peak_usage"] = value
            elif "尖" in label:
                tou_values["tip_usage"] = value
        return tou_values

    def _read_total_charge(self, driver):
        total_charge = None
        matched_charge_count = 0
        charge_items = driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'wrap_electricChargeJm')]//div[contains(@class,'prcGroup_amtGroup')]//div[contains(@class,'amt_item')]",
        )
        for item in charge_items:
            spans = item.find_elements(By.XPATH, "./span")
            if len(spans) < 4:
                continue
            label = spans[0].text.strip()
            amount_text = spans[3].text.strip()
            amount = float(amount_text or 0)
            if "峰" in label or "平" in label or "谷" in label or "尖" in label:
                total_charge = (total_charge or 0.0) + amount
                matched_charge_count += 1
        if matched_charge_count:
            return round(total_charge or 0.0, 2)
        return None

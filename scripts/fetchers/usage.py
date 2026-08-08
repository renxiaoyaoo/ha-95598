import logging
import os
from datetime import datetime
from typing import Any, Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from scripts.fetchers.vue_state import normalize_usage, selected_vue_data


class UsageFetcher:
    def __init__(
        self,
        *,
        driver_wait_time: int,
        click_button: Callable[[Any, str, str], None],
        step_sleep: Callable[[Any, str], None],
    ) -> None:
        self.driver_wait_time = driver_wait_time
        self.click_button = click_button
        self.step_sleep = step_sleep

    def select_usage_year(self, driver, target_year: int) -> bool:
        target_year = int(target_year)
        input_xpath = '//*[@id="pane-first"]/div[1]/div/div[1]/div/div/input'
        try:
            year_input = driver.find_element(By.XPATH, input_xpath)
            current_value = (year_input.get_attribute("value") or "").strip()
            if current_value == str(target_year):
                return True

            self.click_button(driver, By.XPATH, input_xpath)
            self.step_sleep(driver, f"after_open_usage_year_selector_{target_year}")
            option = WebDriverWait(driver, self.driver_wait_time).until(
                EC.element_to_be_clickable((By.XPATH, f"//span[text() = '{target_year}']"))
            )
            driver.execute_script("arguments[0].click();", option)
            self.step_sleep(driver, f"after_select_usage_year_{target_year}")
            WebDriverWait(driver, self.driver_wait_time).until(
                lambda d: (d.find_element(By.XPATH, input_xpath).get_attribute("value") or "").strip() == str(target_year)
            )
            return True
        except Exception as exc:
            logging.warning("Failed to switch usage year to %s: %s", target_year, exc)
            return False

    def get_yearly_data(self, driver, target_year=None):
        try:
            self.click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-first']")
            self.step_sleep(driver, "after_open_yearly_tab")
            desired_year = target_year
            if desired_year is None and datetime.now().month == 1:
                desired_year = datetime.now().year - 1
            if desired_year is not None and not self.select_usage_year(driver, desired_year):
                return None, None
            WebDriverWait(driver, self.driver_wait_time).until(
                EC.visibility_of_element_located((By.XPATH, "//*[@id='pane-first']//ul[contains(@class,'total')]"))
            )
            usage_data = normalize_usage(selected_vue_data(driver))
            if usage_data.get("yearly_usage") is not None:
                logging.info(
                    "Read yearly usage data from Vue state: usage=%s, charge=%s",
                    usage_data.get("yearly_usage"),
                    usage_data.get("yearly_charge"),
                )
                return usage_data.get("yearly_usage"), usage_data.get("yearly_charge")
        except Exception as exc:
            logging.error("The yearly data get failed : %s", exc)
            return None, None

        try:
            yearly_usage = driver.find_element(By.XPATH, "//*[@id='pane-first']//ul[contains(@class,'total')]/li[1]/span").text
        except Exception as exc:
            logging.error("The yearly_usage data get failed : %s", exc)
            yearly_usage = None

        try:
            yearly_charge = driver.find_element(By.XPATH, "//*[@id='pane-first']//ul[contains(@class,'total')]/li[2]/span").text
        except Exception as exc:
            logging.error("The yearly_charge data get failed : %s", exc)
            yearly_charge = None

        return yearly_usage, yearly_charge

    def get_yesterday_usage(self, driver):
        try:
            self.click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-second']")
            self.step_sleep(driver, "after_open_daily_tab_for_yesterday")
            usage_element = driver.find_element(
                By.XPATH,
                "//div[@class='el-tab-pane dayd']//div[@class='el-table__body-wrapper is-scrolling-none']/table/tbody/tr[1]/td[2]/div",
            )
            WebDriverWait(driver, self.driver_wait_time).until(EC.visibility_of(usage_element))

            date_element = driver.find_element(
                By.XPATH,
                "//div[@class='el-tab-pane dayd']//div[@class='el-table__body-wrapper is-scrolling-none']/table/tbody/tr[1]/td[1]/div",
            )
            last_daily_date = date_element.text
            return last_daily_date, float(usage_element.text)
        except Exception as exc:
            logging.error("The yesterday data get failed : %s", exc)
            return None, None

    def get_latest_daily_usage_breakdown(self, driver):
        selectors = (
            ".//p[.//text()[contains(.,'谷用电')]]//span[contains(@class,'num')]",
            ".//p[.//text()[contains(.,'平用电')]]//span[contains(@class,'num')]",
            ".//p[.//text()[contains(.,'峰用电')]]//span[contains(@class,'num')]",
            ".//p[.//text()[contains(.,'尖用电')]]//span[contains(@class,'num')]",
        )
        try:
            self.click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-second']")
            self.step_sleep(driver, "after_open_daily_tab_for_tou_breakdown")
            usage_data = normalize_usage(selected_vue_data(driver))
            daily_rows = [row for row in usage_data.get("daily", []) if row.get("usage") is not None]
            if daily_rows:
                latest = daily_rows[0]
                logging.info("Read latest daily TOU data from Vue state: %s", latest.get("date"))
                return (
                    latest.get("valley_usage"),
                    latest.get("flat_usage"),
                    latest.get("peak_usage"),
                    latest.get("tip_usage"),
                )
            expand_icon = driver.find_element(
                By.XPATH,
                "//div[@class='el-tab-pane dayd']//div[contains(@class,'el-table__body-wrapper')]//table/tbody/tr[1]//div[contains(@class,'el-table__expand-icon')]",
            )
            if "el-table__expand-icon--expanded" not in (expand_icon.get_attribute("class") or ""):
                driver.execute_script("arguments[0].click();", expand_icon)
            expanded_cell = WebDriverWait(driver, self.driver_wait_time).until(
                EC.visibility_of_element_located(
                    (
                        By.XPATH,
                        "//div[@class='el-tab-pane dayd']//table/tbody/tr[1]/following-sibling::tr[1]//td[contains(@class,'el-table__expanded-cell')]",
                    )
                )
            )
            values = []
            for selector in selectors:
                values.append(float(expanded_cell.find_element(By.XPATH, selector).text.strip()))
            return tuple(values)
        except Exception as exc:
            logging.error("The latest daily usage breakdown data get failed : %s", exc)
            return None, None, None, None

    def get_recent_daily_usage_breakdown_map(self, driver, limit_days=7):
        selectors = {
            "valley_usage": ".//p[.//text()[contains(.,'谷用电')]]//span[contains(@class,'num')]",
            "flat_usage": ".//p[.//text()[contains(.,'平用电')]]//span[contains(@class,'num')]",
            "peak_usage": ".//p[.//text()[contains(.,'峰用电')]]//span[contains(@class,'num')]",
            "tip_usage": ".//p[.//text()[contains(.,'尖用电')]]//span[contains(@class,'num')]",
        }
        daily_tou_map = {}
        try:
            self.click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-second']")
            self.step_sleep(driver, "after_open_daily_tab_for_recent_tou_breakdown")
            if not self.set_daily_retention_days(driver, retention_days=7):
                return daily_tou_map

            usage_data = normalize_usage(selected_vue_data(driver))
            for row in usage_data.get("daily", [])[:limit_days]:
                row_date = row.get("date")
                if not row_date:
                    continue
                daily_tou_map[row_date] = {
                    "valley_usage": row.get("valley_usage", 0.0) or 0.0,
                    "flat_usage": row.get("flat_usage", 0.0) or 0.0,
                    "peak_usage": row.get("peak_usage", 0.0) or 0.0,
                    "tip_usage": row.get("tip_usage", 0.0) or 0.0,
                }
            if daily_tou_map:
                logging.info("Read %s recent daily TOU rows from Vue state.", len(daily_tou_map))
                return daily_tou_map

            data_rows = WebDriverWait(driver, self.driver_wait_time).until(
                EC.presence_of_all_elements_located(
                    (
                        By.XPATH,
                        "//*[@id='pane-second']//div[contains(@class,'el-table__body-wrapper')]//table/tbody/tr[./td[1]/div and ./td[2]/div]",
                    )
                )
            )
            for row in data_rows[:limit_days]:
                row_date = (row.find_element(By.XPATH, "./td[1]/div").text or "").strip()
                if not row_date:
                    continue
                expand_icon = row.find_element(By.XPATH, ".//div[contains(@class,'el-table__expand-icon')]")
                if "el-table__expand-icon--expanded" not in (expand_icon.get_attribute("class") or ""):
                    driver.execute_script("arguments[0].click();", expand_icon)

                expanded_cell = WebDriverWait(driver, self.driver_wait_time).until(
                    EC.visibility_of_element_located(
                        (
                            By.XPATH,
                            f"//*[@id='pane-second']//div[contains(@class,'el-table__body-wrapper')]//table/tbody/tr[./td[1]/div and normalize-space(./td[1]/div)='{row_date}']/following-sibling::tr[1]//td[contains(@class,'el-table__expanded-cell')]",
                        )
                    )
                )
                values = {}
                for key, selector in selectors.items():
                    try:
                        values[key] = float(expanded_cell.find_element(By.XPATH, selector).text.strip())
                    except Exception:
                        values[key] = 0.0
                daily_tou_map[row_date] = values
            return daily_tou_map
        except Exception as exc:
            logging.error("The recent daily usage breakdown data get failed : %s", exc)
            return daily_tou_map

    def set_daily_retention_days(self, driver, retention_days=30) -> bool:
        self.click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-second']")
        self.step_sleep(driver, "after_open_daily_tab_for_retention")
        try:
            if retention_days == 7:
                self.click_button(driver, By.XPATH, "//*[@id='pane-second']/div[1]/div/label[1]/span[1]")
            elif retention_days == 30:
                self.click_button(driver, By.XPATH, "//*[@id='pane-second']/div[1]/div/label[2]/span[1]")
            else:
                logging.error("Unsupported retention days value: %s", retention_days)
                return False
            self.step_sleep(driver, f"after_set_daily_retention_{retention_days}")
            return True
        except Exception as exc:
            logging.warning("Failed to switch daily retention days to %s: %s", retention_days, exc)
            return False

    def extract_daily_usage_rows(self, driver):
        try:
            usage_data = normalize_usage(selected_vue_data(driver))
            daily_rows = [row for row in usage_data.get("daily", []) if row.get("date")]
            if daily_rows:
                return [row["date"] for row in daily_rows], [str(row.get("usage", 0.0)) for row in daily_rows]
        except Exception as exc:
            logging.debug("Failed to read daily rows from Vue state, fallback to DOM: %s", exc)

        usage_element = driver.find_element(
            By.XPATH,
            "//div[@class='el-tab-pane dayd']//div[@class='el-table__body-wrapper is-scrolling-none']/table/tbody/tr[1]/td[2]/div",
        )
        WebDriverWait(driver, self.driver_wait_time).until(EC.visibility_of(usage_element))

        days_element = driver.find_elements(
            By.XPATH,
            "//*[@id='pane-second']/div[2]/div[2]/div[1]/div[3]/table/tbody/tr",
        )
        date = []
        usages = []
        for row in days_element:
            cells = row.find_elements(By.XPATH, "./td")
            if len(cells) < 2:
                logging.debug("Skip non-data daily row, td count=%s, text=%s", len(cells), row.text)
                continue

            day_elements = row.find_elements(By.XPATH, "./td[1]/div")
            usage_elements = row.find_elements(By.XPATH, "./td[2]/div")
            if not day_elements or not usage_elements:
                logging.debug("Skip malformed daily row, text=%s", row.text)
                continue

            day = (day_elements[0].text or "").strip()
            usage = (usage_elements[0].text or "").strip()
            if day and usage:
                usages.append(usage)
                date.append(day)
        return date, usages

    def get_month_usage(self, driver, target_year=None):
        try:
            self.click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-first']")
            self.step_sleep(driver, "after_open_monthly_tab")
            desired_year = target_year
            if desired_year is None and datetime.now().month == 1:
                desired_year = datetime.now().year - 1
            if desired_year is not None and not self.select_usage_year(driver, desired_year):
                return None, None, None
            WebDriverWait(driver, self.driver_wait_time).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//*[@id='pane-first']//div[contains(@class,'el-table__body-wrapper')]//table/tbody")
                )
            )
            usage_data = normalize_usage(selected_vue_data(driver))
            month_rows = usage_data.get("months", [])
            if month_rows:
                logging.info("Read %s monthly usage rows from Vue state.", len(month_rows))
                return (
                    [row.get("month") for row in month_rows],
                    [row.get("usage") for row in month_rows],
                    [row.get("charge") for row in month_rows],
                )
            month_element = driver.find_element(
                By.XPATH,
                "//*[@id='pane-first']//div[contains(@class,'el-table__body-wrapper')]//table/tbody",
            ).text
            month_element = month_element.split("\n")
            month_element = [x for x in month_element if x != "MAX"]
            if len(month_element) % 3 != 0:
                month_element = month_element[: -(len(month_element) % 3)]
            month = []
            usage = []
            charge = []
            for index in range(0, len(month_element), 3):
                month.append(month_element[index])
                usage.append(month_element[index + 1])
                charge.append(month_element[index + 2])
            return month, usage, charge
        except Exception as exc:
            logging.error("The month data get failed : %s", exc)
            return None, None, None

    def get_daily_usage_data(self, driver):
        retention_days = self.get_daily_usage_window_days()
        if not self.set_daily_retention_days(driver, retention_days=retention_days):
            return None
        return self.extract_daily_usage_rows(driver)

    @staticmethod
    def get_daily_usage_window_days() -> int:
        raw_value = os.getenv("DAILY_USAGE_WINDOW_DAYS")
        try:
            return int(raw_value)
        except Exception:
            logging.warning("Invalid daily usage window value %r, fallback to 7.", raw_value)
            return 7

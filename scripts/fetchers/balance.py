import logging
import re

from selenium.webdriver.common.by import By

from scripts.fetchers.vue_state import normalize_balance, selected_vue_data


class BalanceFetcher:
    def get_balance(self, driver):
        try:
            balance = normalize_balance(selected_vue_data(driver)).get("balance")
            if balance is not None:
                logging.info("Read electricity balance from Vue state: %s CNY", balance)
                return balance
        except Exception as exc:
            logging.debug("Failed to read balance from Vue state, fallback to DOM: %s", exc)

        try:
            try:
                title_text = driver.find_element(
                    By.XPATH,
                    "//p[contains(@class, 'balance_title') and contains(text(), '应交金额')]",
                ).text
                if "应交金额" in title_text:
                    balance_content = driver.find_element(
                        By.XPATH,
                        "//p[contains(@class, 'balance_title') and contains(text(), '账户余额')]",
                    )
                    balance_text = re.sub(r"[^\d.]", "", balance_content.text)
                    if balance_text:
                        return float(balance_text)
            except Exception:
                pass

            balance_text = driver.find_element(By.CLASS_NAME, "cff8").text
            balance = balance_text.replace("元", "")
            if "欠费" in balance_text:
                return -float(balance)
            return float(balance)
        except Exception as exc:
            logging.error("Failed to get balance: %s", exc)
            return None

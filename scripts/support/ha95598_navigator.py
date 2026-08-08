import logging
import re
from typing import Callable, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from scripts.const import BALANCE_URL, HOME_URL, LOGIN_URL
from scripts.pages import navigator_selectors as selectors


class Ha95598Navigator:
    """Navigation helpers for authenticated 95598 pages."""

    def __init__(
        self,
        driver_wait_time: int,
        login_manager,
        tencent_captcha,
        log_page_state: Callable,
        step_sleep: Callable,
        click_button: Callable,
    ) -> None:
        self.driver_wait_time = driver_wait_time
        self.login_manager = login_manager
        self.tencent_captcha = tencent_captcha
        self._log_page_state = log_page_state
        self._step_sleep = step_sleep
        self._click_button = click_button

    def click_button(self, driver, button_search_type, button_search_key) -> None:
        self._click_button(driver, button_search_type, button_search_key)

    def get_user_ids(self, driver) -> list[str]:
        try:
            self.open_my_page(driver)
            self.tencent_captcha.clear_overlay(driver)
            WebDriverWait(driver, self.driver_wait_time).until(
                lambda d: not (d.current_url or "").startswith(LOGIN_URL)
            )
            self.tencent_captcha.clear_overlay(driver)
            current_userid = WebDriverWait(driver, self.driver_wait_time).until(
                lambda d: self.read_current_userid(d)
            )
            userid_list = [current_userid] if current_userid else []

            options = self.open_user_selector(driver)
            self._step_sleep(driver, "after_user_dropdown_visible")
            option_count = len(options)
            self._step_sleep(driver, "after_user_dropdown_text_ready")
            if option_count <= 1:
                logging.info("Only one visible account was found on the my page, using current user id.")
                return userid_list

            for option_index in range(option_count):
                if option_index > 0:
                    self.open_user_selector(driver)
                    options = self.get_visible_user_options(driver)
                if option_index >= len(options):
                    break
                driver.execute_script("arguments[0].click();", options[option_index])
                self._step_sleep(driver, f"after_probe_user_option_{option_index}")
                probed_userid = WebDriverWait(driver, self.driver_wait_time).until(
                    lambda d: self.read_current_userid(d)
                )
                if probed_userid and probed_userid not in userid_list:
                    userid_list.append(probed_userid)
            if not userid_list:
                raise RuntimeError("no user ids were parsed from balance page")
            return userid_list
        except Exception as exc:
            self._log_page_state(driver, "get_user_ids_failed")
            raise RuntimeError(f"get user_id list failed: {exc}") from exc

    def open_my_page(self, driver) -> None:
        current_url = driver.current_url or ""
        if not current_url.startswith(HOME_URL):
            driver.get(HOME_URL)
            self._log_page_state(driver, "after_open_home_before_my")
            self._step_sleep(driver, "after_open_home_before_my")
        self._click_my_page(driver, "after_click_my_page")
        if self.has_session_expired_modal(driver):
            self.relogin_after_session_expired(driver)
            if not (driver.current_url or "").startswith(HOME_URL):
                driver.get(HOME_URL)
                self._log_page_state(driver, "after_relogin_open_home")
                self._step_sleep(driver, "after_relogin_open_home")
            self._click_my_page(driver, "after_reclick_my_page")
        WebDriverWait(driver, self.driver_wait_time).until(
            lambda d: bool(d.find_elements(By.XPATH, selectors.SWITCH_USER_TEXT))
            or bool(d.find_elements(By.XPATH, selectors.USER_ID_LABEL))
            or (d.current_url or "").startswith(BALANCE_URL)
            or self.has_session_expired_modal(d)
        )
        if self.has_session_expired_modal(driver):
            raise RuntimeError("session expired while opening my page")
        self._log_page_state(driver, "after_open_my_page")

    def _click_my_page(self, driver, sleep_label: str) -> None:
        my_entry = WebDriverWait(driver, self.driver_wait_time).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    selectors.MY_PAGE_ENTRY,
                )
            )
        )
        driver.execute_script("arguments[0].click();", my_entry)
        self._step_sleep(driver, sleep_label)

    def relogin_after_session_expired(self, driver) -> None:
        logging.info("Detected expired session on my page, relogin and retry user list parsing.")
        try:
            confirm_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        selectors.SESSION_EXPIRED_CONFIRM,
                    )
                )
            )
            driver.execute_script("arguments[0].click();", confirm_button)
        except Exception:
            pass
        self.tencent_captcha.clear_overlay(driver)
        driver.get(LOGIN_URL)
        self._log_page_state(driver, "after_reopen_login_for_user_ids")
        self._step_sleep(driver, "after_reopen_login_for_user_ids")
        if not self.login_manager.login(driver):
            raise RuntimeError("relogin failed after session expired")
        self.login_manager.log_login_success(driver)
        self._step_sleep(driver, "after_relogin_for_user_ids")

    def has_session_expired_modal(self, driver) -> bool:
        try:
            modal_text = driver.execute_script(
                """
                const modal = document.querySelector('.el-message-box__wrapper');
                if (!modal) return '';
                return (modal.innerText || modal.textContent || '').trim();
                """
            )
            if modal_text and ("登录已过期" in modal_text or "重新登录" in modal_text):
                return True
        except Exception:
            pass
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text or ""
            if "登录已过期" in body_text or "重新登录" in body_text:
                return True
        except Exception:
            pass
        return False

    def read_current_userid(self, driver) -> Optional[str]:
        try:
            label = driver.find_element(By.XPATH, selectors.USER_ID_LABEL).text or ""
            matches = re.findall(r"\b\d{13}\b", label)
            if matches:
                return matches[-1]
        except Exception:
            pass
        try:
            page_source = driver.page_source or ""
            match = re.search(r"用电户号[:：\s]*([0-9]{13})", page_source)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def require_current_userid(self, driver) -> str:
        user_id = self.read_current_userid(driver)
        if user_id:
            return user_id
        raise RuntimeError("current user id not found on page")

    def ensure_target_userid(self, driver, userid_index: int, expected_user_id: Optional[str] = None) -> str:
        try:
            current_userid = self.require_current_userid(driver)
            if expected_user_id and current_userid == expected_user_id:
                return current_userid
            if expected_user_id is None and userid_index == 0:
                return current_userid
        except Exception:
            pass

        self.choose_userid_by_index(driver, userid_index)
        return self.require_current_userid(driver)

    def choose_userid_by_index(self, driver, userid_index: int) -> None:
        self.tencent_captcha.clear_overlay(driver)
        elements = driver.find_elements(By.CLASS_NAME, selectors.USER_CONFIRM_BUTTON_CLASS)
        if elements:
            self._click_button(driver, By.XPATH, selectors.USER_CONFIRM_BUTTON)
        self._step_sleep(driver, f"after_user_confirm_dialog_{userid_index}")
        try:
            self._click_button(driver, By.XPATH, selectors.SWITCH_USER_TEXT)
        except Exception:
            self._click_button(driver, By.CLASS_NAME, selectors.USER_SELECTOR_SUFFIX_CLASS)
        self._step_sleep(driver, f"after_open_user_selector_{userid_index}")
        options = WebDriverWait(driver, self.driver_wait_time).until(lambda d: self.get_visible_user_options(d))
        if userid_index >= len(options):
            raise IndexError(
                f"user selector option index {userid_index} is out of range, available={len(options)}"
            )
        driver.execute_script("arguments[0].click();", options[userid_index])

    def open_user_selector(self, driver):
        trigger = WebDriverWait(driver, self.driver_wait_time).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    selectors.USER_SELECTOR_TRIGGER,
                )
            )
        )
        driver.execute_script("arguments[0].click();", trigger)
        self._step_sleep(driver, "after_open_user_dropdown")
        return WebDriverWait(driver, self.driver_wait_time).until(lambda d: self.get_visible_user_options(d))

    def get_visible_user_options(self, driver):
        return [
            option
            for option in driver.find_elements(
                By.XPATH,
                selectors.USER_OPTIONS,
            )
            if option.is_displayed()
            and "is-disabled" not in (option.get_attribute("class") or "")
            and "disabled" not in (option.get_attribute("class") or "")
        ]

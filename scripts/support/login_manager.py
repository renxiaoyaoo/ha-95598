import base64
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from captcha_solver.tencent import TencentCaptchaHandler
from scripts.const import BALANCE_URL, LOGIN_URL
from scripts.support.credentials import LoginCredential, mask_account
from scripts.support.error_watcher import ErrorWatcher
from scripts.support.notifier import build_notifier
from scripts.support.session_manager import SessionManager


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
LOGIN_STATE_FILE = DATA_DIR / "login_state.json"
PASSWORD_ERROR_COOLDOWN_HOURS = int(os.getenv("PASSWORD_LOGIN_ERROR_COOLDOWN_HOURS", "1"))


class LoginManager:
    """Owns all 95598 login, session restore, and login fallback behavior."""

    def __init__(
        self,
        credentials: list[LoginCredential],
        session_manager: SessionManager,
        driver_wait_time: int,
        qr_wait_count: int,
        qr_wait_interval: int,
        qr_refresh_limit: int,
        trace_dir: Callable[[], Path],
        log_page_state: Callable,
        step_sleep: Callable,
        click_button: Callable,
    ) -> None:
        self._credentials = credentials
        self._credential_index = 0
        self._account = credentials[0].account
        self._password = credentials[0].password
        self.session_manager = session_manager
        self.driver_wait_time = driver_wait_time
        self.qr_wait_count = qr_wait_count
        self.qr_wait_interval = qr_wait_interval
        self.qr_refresh_limit = qr_refresh_limit
        self._trace_dir = trace_dir
        self._log_page_state = log_page_state
        self._step_sleep = step_sleep
        self._click_button = click_button
        self.notifier = build_notifier()
        self.login_method = "unknown"
        self._password_login_blocked_this_run = False
        self.tencent_captcha = TencentCaptchaHandler(
            trace_dir=self._trace_dir,
            log_page_state=self._log_page_state,
            step_sleep=self._step_sleep,
            confirm_login_success=self._confirm_login_success,
        )

    def restore_or_login(self, driver) -> str:
        self._set_login_method("unknown")
        if self.session_manager.restore(driver):
            self._set_login_method("restored-session")
            logging.info("Skip interactive login because a valid session was restored.")
        elif self._login_with_credential_rotation(driver):
            if self.login_method == "unknown":
                self._set_login_method("password")
        else:
            raise RuntimeError("login unsuccessed")

        self.log_login_success(driver)
        return self.login_method

    def log_login_success(self, driver) -> None:
        logging.info("Login success via %s on %s", self.login_method, LOGIN_URL)
        if driver is not None:
            self.session_manager.save(driver)

    def clear_session(self) -> None:
        self.session_manager.clear()

    def save_session(self, driver) -> None:
        self.session_manager.save(driver)

    def _activate_credential(self, index: int) -> LoginCredential:
        self._credential_index = index % len(self._credentials)
        credential = self._credentials[self._credential_index]
        self._account = credential.account
        self._password = credential.password
        return credential

    def _set_login_method(self, method: str) -> None:
        self.login_method = method

    def _confirm_login_success(self, driver) -> bool:
        try:
            current_url = driver.current_url or ""
            if current_url.startswith(LOGIN_URL):
                return False
            if SessionManager.is_session_usable(driver):
                return True

            driver.get(BALANCE_URL)
            WebDriverWait(driver, min(self.driver_wait_time, 10)).until(
                lambda d: not (d.current_url or "").startswith(LOGIN_URL)
            )
            return SessionManager.is_session_usable(driver)
        except Exception as exc:
            logging.debug("Failed to confirm login success after redirect: %s", exc)
            return False

    def _wait_for_post_password_login_state(self, driver, timeout: int = 12) -> str:
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: self._confirm_login_success(d)
                or self.tencent_captcha.has_captcha(d)
                or bool(self._get_error_message(d, "//div[@class='errmsg-tip']//span"))
            )
        except Exception:
            pass

        if self._confirm_login_success(driver):
            return "success"
        if self.tencent_captcha.has_captcha(driver):
            return "captcha"
        if self._get_error_message(driver, "//div[@class='errmsg-tip']//span"):
            return "error"
        return "unknown"

    def _login_with_credential_rotation(self, driver, phone_code: bool = False) -> bool:
        if self._is_password_login_in_cooldown():
            logging.info("Password login is in cooldown because recent attempts hit RK001. Skip this unattended run instead of switching to QR-code login.")
            return False

        total_credentials = len(self._credentials)
        self._password_login_blocked_this_run = False
        for attempt in range(total_credentials):
            credential = self._activate_credential(
                self._credential_index if attempt == 0 else self._credential_index + 1
            )
            logging.info(
                "Try interactive login with credential [%s/%s]: %s",
                attempt + 1,
                total_credentials,
                credential.label,
            )
            if self.login(driver, phone_code=phone_code, allow_fallback=False):
                self._clear_password_login_cooldown()
                return True
            logging.info("Login credential %s did not complete password login.", credential.label)
            if self._password_login_blocked_this_run:
                logging.info("Stop trying remaining credentials because password login hit RK001. Skip QR-code fallback for unattended operation.")
                return False

        logging.info("All configured login credentials failed password login. Switch to configured fallback.")
        return self._fallback_login(driver)

    def _open_login_page(self, driver) -> None:
        try:
            driver.get(LOGIN_URL)
            self._log_page_state(driver, "after_open_login_url")
            WebDriverWait(driver, self.driver_wait_time * 3).until(
                EC.visibility_of_element_located((By.CLASS_NAME, "user"))
            )
        except Exception:
            logging.debug("Login failed, open URL: %s failed.", LOGIN_URL)
        logging.info("Open LOGIN_URL:%s.\r", LOGIN_URL)
        self._step_sleep(driver, "login_page_load")

    @ErrorWatcher.watch
    def login(self, driver, phone_code=False, allow_fallback: bool = True) -> bool:
        self._open_login_page(driver)

        driver.implicitly_wait(0)
        try:
            WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.CLASS_NAME, "el-loading-mask")))
        finally:
            driver.implicitly_wait(self.driver_wait_time)

        element = WebDriverWait(driver, self.driver_wait_time).until(
            EC.presence_of_element_located((By.CLASS_NAME, "user"))
        )
        driver.execute_script("arguments[0].click();", element)
        logging.info("find_element 'user'.\r")
        self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[1]/div[1]/div[2]/span')
        self._step_sleep(driver, "after_switch_to_password_tab")

        self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[2]/div[1]/form/div[1]/div[3]/div/span[2]')
        logging.info("Click the Agree option.\r")
        self._step_sleep(driver, "after_click_agree")
        if phone_code:
            self._set_login_method("phone-code")
            self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[1]/div[1]/div[3]/span')
            input_elements = driver.find_elements(By.CLASS_NAME, "el-input__inner")
            input_elements[2].send_keys(self._account)
            logging.info("input_elements account : %s\r", mask_account(self._account))
            self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[2]/div[2]/form/div[1]/div[2]/div[2]/div/a')
            code = input("Input your phone verification code: ")
            input_elements[3].send_keys(code)
            logging.info("input_elements verification code: %s.\r", code)
            self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[2]/div[2]/form/div[2]/div/button/span')
            self._step_sleep(driver, "after_submit_phone_code_login")
            logging.info("Click login button.\r")
            return True

        if self._password is not None and len(self._password) > 0:
            self._set_login_method("password")
            input_elements = driver.find_elements(By.CLASS_NAME, "el-input__inner")
            input_elements[0].send_keys(self._account)
            logging.info("input_elements account : %s\r", mask_account(self._account))
            input_elements[1].send_keys(self._password)
            logging.info("input_elements password : ********\r")

            self._click_button(driver, By.CLASS_NAME, "el-button.el-button--primary")
            self._step_sleep(driver, "after_submit_password_login")
            logging.info("Click login button.\r")
            post_login_state = self._wait_for_post_password_login_state(driver)
            logging.info("Post password-login state: %s", post_login_state)
            if post_login_state == "captcha":
                captcha_info = self.tencent_captcha.get_info(driver)
                logging.info(
                    "Tencent captcha widget detected after password submit, mode=%s, prompt=%s.",
                    captcha_info.get("mode"),
                    captcha_info.get("prompt", ""),
                )
                self.tencent_captcha.capture_state(driver, "after_submit_password_login_tencent_captcha")
                if captcha_info.get("mode") == "point_click" and self.tencent_captcha.solve_point_click_captcha(driver):
                    return True
                if not allow_fallback:
                    return False
                logging.info("Tencent captcha local solver did not complete login. Switch to QR-code login fallback.")
                return self._fallback_login(driver)
            if self._confirm_login_success(driver):
                return True
            if post_login_state == "error":
                error_message = self._get_error_message(driver, "//div[@class='errmsg-tip']//span")
                logging.info(
                    "Password login returned a page error without a usable session: %s. Switch to QR-code login fallback.",
                    error_message or "<empty>",
                )
                if self._is_rk001_error(error_message):
                    self._record_password_login_cooldown(error_message)
                self._log_page_state(driver, "after_submit_password_login_error")
                self._save_tencent_presence(driver)
                if self.tencent_captcha.has_captcha(driver):
                    self.tencent_captcha.capture_state(driver, "after_submit_password_login_error_tencent_captcha")
                if not allow_fallback:
                    return False
                return self._fallback_login(driver)
            if post_login_state == "unknown":
                logging.info("Password login result is still unknown after waiting. Capture page state before QR-code fallback.")
                self._log_page_state(driver, "after_submit_password_login_unknown")
            logging.info("Tencent captcha was not detected after password submit. Switch to QR-code login fallback.")
        if not allow_fallback:
            return False
        return self._fallback_login(driver)

    def _save_tencent_presence(self, driver) -> None:
        try:
            presence = self.tencent_captcha.get_presence_snapshot(driver)
            presence_path = self._trace_dir() / "after_submit_password_login_error.tencent_presence.json.txt"
            presence_path.write_text(json.dumps(presence, ensure_ascii=False, indent=2), encoding="utf-8")
            logging.info("Saved Tencent presence snapshot to %s", presence_path)
        except Exception as exc:
            logging.info("Failed to save Tencent presence snapshot: %s", exc)

    def _get_error_message(self, driver, path) -> Optional[str]:
        driver.implicitly_wait(0)
        try:
            element = driver.find_element(By.XPATH, path)
            return element.text
        except Exception:
            return None
        finally:
            driver.implicitly_wait(self.driver_wait_time)

    @staticmethod
    def _is_rk001_error(error_message: Optional[str]) -> bool:
        return bool(error_message and "RK001" in error_message)

    def _load_login_state(self) -> dict:
        try:
            if LOGIN_STATE_FILE.exists():
                return json.loads(LOGIN_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning("Failed to load login state file %s: %s", LOGIN_STATE_FILE, exc)
        return {}

    def _save_login_state(self, state: dict) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            LOGIN_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logging.warning("Failed to save login state file %s: %s", LOGIN_STATE_FILE, exc)

    def _record_password_login_cooldown(self, error_message: Optional[str]) -> None:
        self._password_login_blocked_this_run = True
        if PASSWORD_ERROR_COOLDOWN_HOURS <= 0:
            logging.info("Password login RK001 detected; persistent cooldown is disabled.")
            return
        now = datetime.now(timezone.utc)
        state = self._load_login_state()
        state["password_login_error"] = {
            "reason": "RK001",
            "message": error_message or "",
            "blocked_until": (now + timedelta(hours=PASSWORD_ERROR_COOLDOWN_HOURS)).isoformat(),
            "updated_at": now.isoformat(),
        }
        self._save_login_state(state)
        logging.info("Password login cooldown recorded for %s hour(s) after RK001.", PASSWORD_ERROR_COOLDOWN_HOURS)

    def _clear_password_login_cooldown(self) -> None:
        state = self._load_login_state()
        if "password_login_error" not in state:
            return
        state.pop("password_login_error", None)
        self._save_login_state(state)
        self._password_login_blocked_this_run = False
        logging.info("Password login cooldown cleared after successful password login.")

    def _is_password_login_in_cooldown(self) -> bool:
        if PASSWORD_ERROR_COOLDOWN_HOURS <= 0:
            return False
        state = self._load_login_state()
        password_error = state.get("password_login_error") if isinstance(state, dict) else None
        if not isinstance(password_error, dict):
            return False
        if password_error.get("reason") != "RK001":
            return False
        try:
            updated_at = password_error.get("updated_at")
            if updated_at:
                updated = datetime.fromisoformat(updated_at)
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                until = updated + timedelta(hours=PASSWORD_ERROR_COOLDOWN_HOURS)
            else:
                blocked_until = password_error.get("blocked_until")
                if not blocked_until:
                    return False
                until = datetime.fromisoformat(blocked_until)
                if until.tzinfo is None:
                    until = until.replace(tzinfo=timezone.utc)
        except Exception:
            return False
        if datetime.now(timezone.utc) < until:
            return True
        state.pop("password_login_error", None)
        self._save_login_state(state)
        return False

    def _fallback_login(self, driver) -> bool:
        fallback = os.getenv("LOGIN_FALLBACK")
        if fallback == "qrcode":
            self._set_login_method("qrcode")
            return self._qr_login(driver)
        return False

    def _qr_login(self, driver) -> bool:
        logging.info("qrcode login start")
        if not self._open_qr_login_tab(driver):
            return False

        qr_code_path = DATA_DIR / "login_qr_code.png"
        previous_qr_src: Optional[str] = None
        for refresh_index in range(self.qr_refresh_limit + 1):
            try:
                qr_element, img_screenshot, current_qr_src = self._wait_for_fresh_qr_code(driver, previous_qr_src)
            except Exception as exc:
                logging.warning("Failed to wait for a fresh QR code image: %s", exc)
                return False
            previous_qr_src = current_qr_src

            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(qr_code_path, "wb") as file:
                file.write(img_screenshot)
                logging.info("save qrcode to %s", qr_code_path)

            if self.notifier.send_qr_code(img_screenshot):
                logging.info("QRCode notification sent successfully.")
            else:
                logging.info("Please scan the local QR code file at %s", qr_code_path)

            should_refresh = False
            for index in range(1, self.qr_wait_count + 1):
                logging.info(
                    "qrcode check login wait[%s] count[%s] refresh[%s/%s]",
                    self.qr_wait_interval,
                    index,
                    refresh_index,
                    self.qr_refresh_limit,
                )
                time.sleep(self.qr_wait_interval)
                if driver.current_url != LOGIN_URL:
                    self._set_login_method("qrcode")
                    logging.info("Login success via qrcode.")
                    return True

                error = self._get_error_message(driver, "//div[@class='sweepCodePic']//div[@class='erwBg']//p")
                if error is None:
                    continue

                logging.error("qrcode login error[%s]", error)
                if "二维码失效" in error and refresh_index < self.qr_refresh_limit:
                    logging.info(
                        "QR code expired, refreshing QR code and retrying [%s/%s].",
                        refresh_index + 1,
                        self.qr_refresh_limit,
                    )
                    if not self._reload_qr_login_page(driver):
                        return False
                    previous_qr_src = None
                    should_refresh = True
                    break

                if self.tencent_captcha.has_captcha(driver):
                    captcha_info = self.tencent_captcha.get_info(driver)
                    logging.info(
                        "Tencent captcha still visible during QR fallback, mode=%s, prompt=%s",
                        captcha_info.get("mode"),
                        captcha_info.get("prompt", ""),
                    )
                    self.tencent_captcha.capture_state(driver, "qrcode_login_error_tencent_captcha")
                return False

            if should_refresh:
                continue

            if refresh_index < self.qr_refresh_limit:
                logging.warning(
                    "qrcode Login timeout, refreshing QR code and retrying [%s/%s].",
                    refresh_index + 1,
                    self.qr_refresh_limit,
                )
                if not self._reload_qr_login_page(driver):
                    return False
                previous_qr_src = None
                continue

            logging.warning("qrcode Login timeout")
            break

        if self.tencent_captcha.has_captcha(driver):
            captcha_info = self.tencent_captcha.get_info(driver)
            logging.info(
                "Tencent captcha still visible after QR timeout, mode=%s, prompt=%s",
                captcha_info.get("mode"),
                captcha_info.get("prompt", ""),
            )
            self.tencent_captcha.capture_state(driver, "qrcode_login_timeout_tencent_captcha")

        return False

    def _wait_for_fresh_qr_code(self, driver, previous_qr_src: Optional[str]) -> tuple[object, bytes, str]:
        def read_qr_code(d):
            element = d.find_element(By.XPATH, "//div[@class='sweepCodePic']//img")
            if not element.is_displayed():
                return False
            img_src = element.get_attribute("src") or ""
            if not img_src or img_src == previous_qr_src:
                return False
            error = self._get_error_message(d, "//div[@class='sweepCodePic']//div[@class='erwBg']//p")
            if error and "二维码失效" in error:
                return False
            if img_src.startswith("data:image"):
                image_bytes = base64.b64decode(img_src.split(",", 1)[1])
            else:
                logging.info("qrcode img src not base64")
                image_bytes = element.screenshot_as_png
            return element, image_bytes, img_src

        result = WebDriverWait(driver, self.driver_wait_time).until(read_qr_code)
        logging.info("find fresh qrcode image")
        return result

    def _open_qr_login_tab(self, driver) -> bool:
        try:
            element = WebDriverWait(driver, self.driver_wait_time).until(
                EC.presence_of_element_located((By.CLASS_NAME, "qr_code"))
            )
            driver.execute_script("arguments[0].click();", element)
            logging.info("switch to qrcode mode")
            self._step_sleep(driver, "after_switch_to_qrcode_mode")
            return True
        except Exception as exc:
            logging.warning("Failed to switch to QR-code login mode: %s", exc)
            return False

    def _reload_qr_login_page(self, driver) -> bool:
        try:
            logging.info("Reload login page to request a new QR code.")
            self._open_login_page(driver)
            return self._open_qr_login_tab(driver)
        except Exception as exc:
            logging.warning("Failed to reload QR-code login page: %s", exc)
            return False

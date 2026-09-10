"""Capture screenshots and page artifacts when decorated scraper steps fail."""

import functools
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


class ErrorWatcher:
    _instance = None

    @classmethod
    def init(cls, **kwargs):
        if cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def instance(cls):
        if cls._instance is None:
            raise ValueError("ErrorWatcher has not been initialized. Call init() first.")
        return cls._instance

    @classmethod
    def watch(cls, func: Optional[Callable] = None, **options) -> Callable:
        def decorator(target):
            @functools.wraps(target)
            def wrapped(*args, **kwargs):
                instance = cls.instance()
                return instance._watch_impl(target, *args, **kwargs)

            return wrapped

        return decorator(func) if func is not None else decorator

    def __init__(self, **kwargs):
        self.root_dir = Path(kwargs.get("root_dir", Path.cwd()))
        self.screenshot_dir = Path(kwargs.get("screenshot_dir", self.root_dir / "pages"))
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.driver = kwargs.get("driver")
        self._last_prune_day: str | None = None

    def set_driver(self, driver):
        self.driver = driver

    def watch_this(self, func, **options):
        error_type = options.get("error_type", Exception)

        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except error_type as exc:
                self._handle_error(exc, **options)
                raise

        return wrapper

    def _watch_impl(self, func, *args, **options):
        error_type = options.get("error_type", Exception)
        try:
            return func(*args, **options)
        except error_type as exc:
            self._handle_error(exc, **options)
            raise

    def _handle_error(self, error, **options):
        driver = options.get("driver", self.driver)
        if not driver:
            logging.error("No driver set for taking screenshots.")
            return
        self._prune_old_artifacts()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_path = self.screenshot_dir / f"error_{timestamp}"
        screenshot_path = base_path.with_suffix(".png")

        try:
            driver.save_screenshot(str(screenshot_path))
            self._save_debug_artifacts(driver, base_path, error)
            logging.error("Error occurred (%s). Screenshot saved to %s", type(error).__name__, screenshot_path)
        except Exception as exc:
            logging.error("Failed to save screenshot: %s", exc)

    def _save_debug_artifacts(self, driver, base_path: Path, error: Exception) -> None:
        current_url = self._read_driver_value(lambda: driver.current_url, "current_url")
        current_title = self._read_driver_value(lambda: driver.title, "title")
        debug_state = self._collect_debug_state(driver)
        browser_logs = self._read_driver_logs(driver, "browser")
        performance_logs = self._read_driver_logs(driver, "performance", keep_last=50)
        cookie_summary = self._collect_cookies(driver)
        storage_state = self._collect_storage_state(driver)

        if self._detail_trace_enabled():
            page_source = self._read_driver_value(lambda: driver.page_source or "", "page_source")
            self._write_text(
                base_path.with_suffix(".html.txt"),
                f"url={current_url}\ntitle={current_title}\nerror={error!r}\n\n{page_source}",
                "error html artifact",
            )
        self._write_text(
            base_path.with_suffix(".meta.txt"),
            "url={}\ntitle={}\nerror={}\n\n{}".format(
                current_url,
                current_title,
                repr(error),
                json.dumps(
                    {
                        "page_state": debug_state,
                        "cookies": cookie_summary,
                        "storage": storage_state,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ),
            "error meta artifact",
        )
        self._write_text(
            base_path.with_suffix(".browser.log.txt"),
            json.dumps(browser_logs, ensure_ascii=False, indent=2),
            "browser log artifact",
        )
        self._write_text(
            base_path.with_suffix(".performance.log.txt"),
            json.dumps(performance_logs, ensure_ascii=False, indent=2),
            "performance log artifact",
        )

    @staticmethod
    def _read_driver_value(reader, label: str):
        try:
            return reader()
        except Exception as exc:
            return f"<failed to read {label}: {exc}>"

    @staticmethod
    def _read_driver_logs(driver, log_type: str, keep_last: Optional[int] = None):
        try:
            logs = driver.get_log(log_type)
            return logs[-keep_last:] if keep_last else logs
        except Exception as exc:
            return [{"message": f"<failed to read {log_type} logs: {exc}>"}]

    @staticmethod
    def _collect_cookies(driver):
        try:
            cookies = driver.get_cookies()
            return [
                {
                    "name": item.get("name"),
                    "domain": item.get("domain"),
                    "path": item.get("path"),
                    "expiry": item.get("expiry"),
                }
                for item in cookies
            ]
        except Exception as exc:
            return [{"failed_to_collect_cookies": str(exc)}]

    @staticmethod
    def _collect_storage_state(driver):
        try:
            return driver.execute_script(
                """
                return {
                  local_storage_keys: Object.keys(window.localStorage || {}),
                  session_storage_keys: Object.keys(window.sessionStorage || {})
                };
                """
            )
        except Exception as exc:
            return {"failed_to_collect_storage_state": str(exc)}

    @staticmethod
    def _collect_debug_state(driver):
        try:
            return driver.execute_script(
                """
                const visible = (el) => {
                  if (!el) return false;
                  const style = window.getComputedStyle(el);
                  return style && style.display !== 'none' && style.visibility !== 'hidden';
                };
                return {
                  ready_state: document.readyState,
                  active_element: document.activeElement ? document.activeElement.tagName : null,
                  iframe_count: document.querySelectorAll('iframe').length,
                  visible_inputs: Array.from(document.querySelectorAll('input, textarea, select'))
                    .filter(visible)
                    .slice(0, 20)
                    .map((el) => ({
                      tag: el.tagName,
                      type: el.type || '',
                      class_name: el.className || '',
                      placeholder: el.placeholder || '',
                      has_value: Boolean(el.value)
                    })),
                  visible_buttons: Array.from(document.querySelectorAll('button, [role="button"]'))
                    .filter(visible)
                    .slice(0, 20)
                    .map((el) => (el.innerText || el.textContent || '').trim()),
                  body_text_excerpt: (document.body && (document.body.innerText || '').trim().slice(0, 2000)) || ''
                };
                """
            )
        except Exception as exc:
            return {"failed_to_collect_debug_state": str(exc)}

    @staticmethod
    def _detail_trace_enabled() -> bool:
        return os.getenv("DEBUG_ERROR_TRACE_DETAIL", "false").lower() == "true"

    @staticmethod
    def _write_text(path: Path, content: str, label: str) -> None:
        try:
            path.write_text(content, encoding="utf-8")
        except Exception as exc:
            logging.warning("Failed to write %s: %s", label, exc)

    def _prune_old_artifacts(self) -> None:
        try:
            retention_days = max(int(os.getenv("TRACE_RETENTION_DAYS", "7")), 0)
        except Exception:
            retention_days = 7
        if retention_days <= 0:
            return

        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_prune_day == today:
            return

        cutoff = datetime.now().timestamp() - retention_days * 86400
        try:
            for path in self.screenshot_dir.rglob("*"):
                if path.is_file():
                    try:
                        if path.stat().st_mtime < cutoff:
                            path.unlink(missing_ok=True)
                    except Exception:
                        continue
            self._last_prune_day = today
        except Exception as exc:
            logging.debug("Failed to prune error artifacts: %s", exc)

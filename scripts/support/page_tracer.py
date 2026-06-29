import base64
import inspect
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class PageTracer:
    """Persist browser page diagnostics without coupling it to scraper logic."""

    def __init__(self, trace_dir: Path):
        self.trace_dir = trace_dir
        self._last_prune_day: str | None = None

    def ensure_trace_dir(self) -> Path:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._prune_old_artifacts()
        return self.trace_dir

    @staticmethod
    def _trace_retention_days() -> int:
        try:
            return max(int(os.getenv("TRACE_RETENTION_DAYS", "7")), 0)
        except Exception:
            return 7

    @staticmethod
    def _detail_trace_enabled() -> bool:
        return os.getenv("DEBUG_PAGE_TRACE_DETAIL", "false").lower() == "true"

    def _prune_old_artifacts(self) -> None:
        retention_days = self._trace_retention_days()
        if retention_days <= 0:
            return

        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_prune_day == today:
            return

        cutoff = datetime.now() - timedelta(days=retention_days)
        try:
            for path in self.trace_dir.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                        path.unlink(missing_ok=True)
                except Exception:
                    continue
            self._last_prune_day = today
        except Exception as exc:
            logging.debug("Failed to prune page trace artifacts: %s", exc)

    @staticmethod
    def resolve_label(label: Optional[str] = None, caller_depth: int = 2) -> str:
        if label:
            return label
        frame = inspect.stack()[caller_depth]
        return f"{frame.function}_line_{frame.lineno}"

    def log_page_state(self, driver, label: Optional[str] = None) -> None:
        if driver is None:
            return

        step_label = self.resolve_label(label)
        safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", step_label)[:80]
        base_path = self.ensure_trace_dir() / safe_label
        detailed_trace = self._detail_trace_enabled()

        try:
            current_url = driver.current_url
        except Exception as exc:
            current_url = f"<failed to read current_url: {exc}>"
        try:
            current_title = driver.title
        except Exception as exc:
            current_title = f"<failed to read title: {exc}>"
        try:
            debug_state = driver.execute_script(
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
                  visible_buttons: Array.from(document.querySelectorAll('button, [role=\"button\"]'))
                    .filter(visible)
                    .slice(0, 20)
                    .map((el) => (el.innerText || el.textContent || '').trim()),
                  body_text_excerpt: (document.body && (document.body.innerText || '').trim().slice(0, 2000)) || ''
                };
                """
            )
        except Exception as exc:
            debug_state = {"failed_to_collect_debug_state": str(exc)}
        try:
            cookies = driver.get_cookies()
            cookie_summary = [
                {
                    "name": item.get("name"),
                    "domain": item.get("domain"),
                    "path": item.get("path"),
                    "expiry": item.get("expiry"),
                }
                for item in cookies
            ]
        except Exception as exc:
            cookie_summary = [{"failed_to_collect_cookies": str(exc)}]
        try:
            storage_state = driver.execute_script(
                """
                return {
                  local_storage_keys: Object.keys(window.localStorage || {}),
                  session_storage_keys: Object.keys(window.sessionStorage || {})
                };
                """
            )
        except Exception as exc:
            storage_state = {"failed_to_collect_storage_state": str(exc)}

        logging.info("Page trace [%s] url=%s title=%s", step_label, current_url, current_title)
        self._write_text(
            base_path.with_suffix(".meta.txt"),
            "step={}\nurl={}\ntitle={}\n\n{}".format(
                step_label,
                current_url,
                current_title,
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
            step_label,
            "meta",
        )
        if detailed_trace:
            try:
                page_source = driver.page_source or ""
            except Exception as exc:
                page_source = f"<failed to read page_source: {exc}>"
            try:
                browser_logs = driver.get_log("browser")
            except Exception as exc:
                browser_logs = [{"level": "ERROR", "message": f"<failed to read browser logs: {exc}>"}]
            try:
                performance_logs = driver.get_log("performance")[-50:]
            except Exception as exc:
                performance_logs = [{"message": f"<failed to read performance logs: {exc}>"}]
            self._write_text(
                base_path.with_suffix(".html.txt"),
                f"step={step_label}\nurl={current_url}\ntitle={current_title}\n\n{page_source}",
                step_label,
                "HTML",
            )
            self._write_text(base_path.with_suffix(".browser.log.txt"), json.dumps(browser_logs, ensure_ascii=False, indent=2), step_label, "browser")
            self._write_text(base_path.with_suffix(".performance.log.txt"), json.dumps(performance_logs, ensure_ascii=False, indent=2), step_label, "performance")

        try:
            self.save_page_snapshot(driver, base_path.with_suffix(".png"))
        except Exception as exc:
            logging.warning("Failed to save screenshot for [%s]: %s", step_label, exc)

    @staticmethod
    def _write_text(path: Path, content: str, label: str, kind: str) -> None:
        try:
            path.write_text(content, encoding="utf-8")
        except Exception as exc:
            logging.warning("Failed to write %s trace for [%s]: %s", kind, label, exc)

    @staticmethod
    def save_page_snapshot(driver, target_path: Path) -> None:
        use_full_page = os.getenv("DEBUG_FULL_PAGE_SCREENSHOT", "false").lower() == "true"
        if not use_full_page:
            lower_name = target_path.name.lower()
            use_full_page = "failed" in lower_name or "error" in lower_name
        if use_full_page:
            try:
                metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
                content_size = metrics.get("contentSize", {})
                width = max(1280, int(content_size.get("width", 1280)))
                height = max(720, int(content_size.get("height", 720)))
                driver.execute_cdp_cmd(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "mobile": False,
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                    },
                )
                result = driver.execute_cdp_cmd(
                    "Page.captureScreenshot",
                    {
                        "format": "png",
                        "captureBeyondViewport": True,
                        "fromSurface": True,
                    },
                )
                target_path.write_bytes(base64.b64decode(result["data"]))
                logging.info("Saved full-page screenshot to %s", target_path)
                return
            except Exception as exc:
                logging.warning("Full-page screenshot failed, fallback to viewport screenshot: %s", exc)
            finally:
                try:
                    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
                except Exception:
                    pass

        driver.save_screenshot(str(target_path))
        logging.info("Saved viewport screenshot to %s", target_path)

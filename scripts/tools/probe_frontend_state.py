"""Dump 95598 frontend Vue state and network summaries for API research."""

from __future__ import annotations

import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.const import BALANCE_URL, ELECTRIC_BILL_SUMMARY_URL, ELECTRIC_USAGE_URL, LOGIN_URL
from scripts.data_fetcher import DataFetcher
from scripts.fetchers.vue_state import (
    normalize_balance,
    normalize_bill_detail,
    normalize_bill_summary,
    normalize_usage,
    selected_vue_data,
)
from scripts.main import LOCAL_DATA_DIR, logger_init
from scripts.sensor_updater import SensorUpdater
from scripts.support.credentials import load_login_credentials
from scripts.support.error_watcher import ErrorWatcher
from scripts.support.credentials import mask_user_id


OUT_DIR = LOCAL_DATA_DIR / "pages"


def _dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Wrote %s", path)


def _drain_performance_logs(driver) -> None:
    try:
        driver.get_log("performance")
    except Exception:
        pass


def _network_summary(driver) -> list[dict[str, Any]]:
    summary = []
    try:
        logs = driver.get_log("performance")
    except Exception as exc:
        return [{"error": f"failed_to_read_performance_logs: {exc}"}]

    for item in logs:
        try:
            message = json.loads(item.get("message", "{}")).get("message", {})
            method = message.get("method")
            params = message.get("params", {})
            if method == "Network.requestWillBeSent":
                request = params.get("request", {})
                summary.append(
                    {
                        "event": "request",
                        "request_id": params.get("requestId"),
                        "method": request.get("method"),
                        "url": request.get("url"),
                        "type": params.get("type"),
                    }
                )
            elif method == "Network.responseReceived":
                response = params.get("response", {})
                summary.append(
                    {
                        "event": "response",
                        "request_id": params.get("requestId"),
                        "status": response.get("status"),
                        "url": response.get("url"),
                        "mime_type": response.get("mimeType"),
                    }
                )
        except Exception:
            continue
    return summary


def _vue_summary(driver) -> list[dict[str, Any]]:
    return driver.execute_script(
        """
        const summarizeValue = (value) => {
          if (value === null || value === undefined) return { type: String(value) };
          if (Array.isArray(value)) {
            const first = value[0];
            return {
              type: 'array',
              length: value.length,
              firstKeys: first && typeof first === 'object' ? Object.keys(first).slice(0, 50) : [],
              firstValue: first && typeof first !== 'object' ? String(first).slice(0, 80) : undefined
            };
          }
          if (typeof value === 'object') {
            return { type: 'object', keys: Object.keys(value).slice(0, 80) };
          }
          if (typeof value === 'function') {
            return { type: 'function' };
          }
          return { type: typeof value, value: String(value).slice(0, 120) };
        };

        const visibleText = (el) => (el.innerText || el.textContent || '').trim().slice(0, 200);
        return Array.from(document.querySelectorAll('*'))
          .map((el, index) => {
            const vm = el.__vue__;
            if (!vm) return null;
            const ownKeys = Object.keys(vm).filter((key) => !key.startsWith('$') && !key.startsWith('_'));
            const samples = {};
            ownKeys.slice(0, 160).forEach((key) => {
              try { samples[key] = summarizeValue(vm[key]); } catch (e) {}
            });
            return {
              index,
              tag: el.tagName,
              id: el.id || '',
              className: String(el.className || '').slice(0, 160),
              text: visibleText(el),
              keys: ownKeys.slice(0, 200),
              samples
            };
          })
          .filter(Boolean);
        """
    )


def _dump_page(fetcher: DataFetcher, driver, label: str) -> None:
    fetcher.log_page_state(driver, f"probe_{label}")
    selected_data = selected_vue_data(driver)
    _dump_json(OUT_DIR / f"probe_{label}_vue.json", _vue_summary(driver))
    _dump_json(OUT_DIR / f"probe_{label}_data.json", selected_data)
    _dump_json(OUT_DIR / f"probe_{label}_normalized.json", _normalize_page(label, selected_data))
    _dump_json(OUT_DIR / f"probe_{label}_network.json", _network_summary(driver))


def _normalize_page(label: str, selected_data: list[dict[str, Any]]) -> dict[str, Any]:
    if label == "balance":
        return normalize_balance(selected_data)
    if label == "usage":
        return normalize_usage(selected_data)
    if label == "bill_summary":
        return normalize_bill_summary(selected_data)
    if label == "bill_detail":
        return normalize_bill_detail(selected_data)
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe 95598 frontend Vue state and network requests.")
    parser.add_argument("--user-id", help="Known 95598 user id. When set, the probe can skip user list parsing.")
    parser.add_argument("--skip-user-list", action="store_true", help="Do not open the My page to parse user ids.")
    parser.add_argument("--qr-only", action="store_true", help="Skip password login and use QR-code login directly.")
    args = parser.parse_args()

    logger_init("INFO")
    ErrorWatcher.init(root_dir=str(LOCAL_DATA_DIR), screenshot_dir=str(OUT_DIR))

    credentials = load_login_credentials()
    if not credentials:
        raise RuntimeError("No login credentials configured")

    updater = SensorUpdater()
    fetcher = DataFetcher(
        credentials[0].account,
        credentials[0].password,
        updater=updater,
        credentials=credentials,
    )

    driver = fetcher.create_webdriver()
    ErrorWatcher.instance().set_driver(driver)
    try:
        fetcher.step_sleep(driver, "probe_after_webdriver_init")
        if args.qr_only:
            driver.get(LOGIN_URL)
            fetcher.log_page_state(driver, "probe_after_open_login_url")
            fetcher.step_sleep(driver, "probe_after_open_login_url")
            if not fetcher.login_manager._fallback_login(driver):
                raise RuntimeError("QR-code login failed")
            fetcher.login_manager.log_login_success(driver)
        else:
            fetcher.login_manager.restore_or_login(driver)
        fetcher.step_sleep(driver, "probe_after_login")
        if args.skip_user_list:
            if not args.user_id:
                raise RuntimeError("--skip-user-list requires --user-id")
            user_id = args.user_id
        else:
            user_ids = fetcher.navigator.get_user_ids(driver)
            if not user_ids:
                raise RuntimeError("No user ids found")
            user_id = user_ids[0]
        logging.info("Probe user_id=%s at %s", mask_user_id(user_id), datetime.now().isoformat(timespec="seconds"))

        _drain_performance_logs(driver)
        driver.get(BALANCE_URL)
        fetcher.step_sleep(driver, "probe_after_open_balance")
        _dump_page(fetcher, driver, "balance")

        _drain_performance_logs(driver)
        if args.skip_user_list:
            driver.get(ELECTRIC_USAGE_URL)
            fetcher.log_page_state(driver, f"probe_usage_{mask_user_id(user_id)}")
            fetcher.step_sleep(driver, f"probe_usage_{mask_user_id(user_id)}")
        else:
            fetcher.usage_page.open_for_user(driver, user_id, 0, label_prefix="probe_usage")
        _dump_page(fetcher, driver, "usage")

        _drain_performance_logs(driver)
        driver.get(ELECTRIC_BILL_SUMMARY_URL)
        fetcher.step_sleep(driver, "probe_after_open_bill_summary")
        _dump_page(fetcher, driver, "bill_summary")
        if fetcher._open_bill_detail_by_index(driver, 0):
            _dump_page(fetcher, driver, "bill_detail")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()

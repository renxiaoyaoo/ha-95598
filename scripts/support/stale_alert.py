from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Callable

from scripts.support.notifier import Notifier


class StaleDataAlertChecker:
    def __init__(
        self,
        notifier: Notifier,
        update_progress: Callable[..., None],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.notifier = notifier
        self.update_progress = update_progress
        self.now = now or datetime.now

    def check(self, user_id: str, entry: dict) -> None:
        stale_days_threshold = int(os.getenv("STALE_DATA_ALERT_DAYS", 2))
        user_data = entry.get("data", {}) if isinstance(entry, dict) else {}
        progress = entry.get("progress", {}) if isinstance(entry, dict) else {}
        latest_date = user_data.get("last_daily_date")
        if not latest_date:
            return

        try:
            latest_dt = datetime.strptime(latest_date, "%Y-%m-%d").date()
        except Exception:
            logging.warning("Failed to parse last_daily_date for stale data alert: %s", latest_date)
            return

        stale_days = (self.now().date() - latest_dt).days
        alert_key = f"{latest_date}:{stale_days}"
        sent_key = progress.get("stale_alert_sent_key")

        if stale_days > stale_days_threshold:
            if sent_key == alert_key:
                return
            if self.notifier.send_stale_data_alert(user_id, latest_date, stale_days):
                self.update_progress(user_id, stale_alert_sent_key=alert_key)
        elif sent_key:
            self.update_progress(user_id, stale_alert_sent_key=None)

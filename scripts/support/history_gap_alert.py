from __future__ import annotations

import logging
import os
from typing import Callable

from scripts.support.db import SqliteDB
from scripts.support.notifier import Notifier


class HistoryGapAlertChecker:
    def __init__(
        self,
        notifier: Notifier,
        update_progress: Callable[..., None],
        db: SqliteDB,
    ) -> None:
        self.notifier = notifier
        self.update_progress = update_progress
        self.db = db

    @staticmethod
    def _window_days() -> int:
        try:
            return max(int(os.getenv("HISTORY_GAP_ALERT_DAYS", "30")), 2)
        except ValueError:
            logging.warning("Invalid HISTORY_GAP_ALERT_DAYS; using 30 days.")
            return 30

    def check(self, user_id: str, entry: dict) -> None:
        progress = entry.get("progress", {}) if isinstance(entry, dict) else {}
        sent_key = progress.get("history_gap_alert_sent_key")

        if not self.db.connect_user_db(user_id):
            return
        try:
            missing_dates = self.db.get_missing_daily_dates(self._window_days())
        finally:
            self.db.close_connect()

        if not missing_dates:
            if sent_key:
                self.update_progress(user_id, history_gap_alert_sent_key=None)
            return

        first_missing = missing_dates[0]
        last_missing = missing_dates[-1]
        alert_key = f"{first_missing}:{last_missing}:{len(missing_dates)}"
        if sent_key == alert_key:
            return
        if self.notifier.send_history_gap_alert(
            user_id, first_missing, last_missing, len(missing_dates)
        ):
            self.update_progress(user_id, history_gap_alert_sent_key=alert_key)

from datetime import datetime

from scripts.support.stale_alert import StaleDataAlertChecker


class FakeNotifier:
    def __init__(self):
        self.stale_alerts = []

    def send_qr_code(self, qrcode: bytes) -> bool:
        return False

    def send_stale_data_alert(self, user_id: str, latest_date: str, stale_days: int) -> bool:
        self.stale_alerts.append((user_id, latest_date, stale_days))
        return True


def test_stale_alert_sends_once_for_same_alert_key(monkeypatch):
    monkeypatch.setenv("STALE_DATA_ALERT_DAYS", "2")
    notifier = FakeNotifier()
    progress_updates = []
    checker = StaleDataAlertChecker(
        notifier,
        lambda user_id, **fields: progress_updates.append((user_id, fields)),
        now=lambda: datetime(2026, 8, 9, 12, 0, 0),
    )
    entry = {"data": {"last_daily_date": "2026-08-06"}, "progress": {}}

    checker.check("test_user", entry)

    assert notifier.stale_alerts == [("test_user", "2026-08-06", 3)]
    assert progress_updates == [("test_user", {"stale_alert_sent_key": "2026-08-06:3"})]

    entry["progress"]["stale_alert_sent_key"] = "2026-08-06:3"
    checker.check("test_user", entry)

    assert notifier.stale_alerts == [("test_user", "2026-08-06", 3)]


def test_stale_alert_clears_sent_key_when_data_is_fresh(monkeypatch):
    monkeypatch.setenv("STALE_DATA_ALERT_DAYS", "2")
    notifier = FakeNotifier()
    progress_updates = []
    checker = StaleDataAlertChecker(
        notifier,
        lambda user_id, **fields: progress_updates.append((user_id, fields)),
        now=lambda: datetime(2026, 8, 9, 12, 0, 0),
    )
    entry = {
        "data": {"last_daily_date": "2026-08-08"},
        "progress": {"stale_alert_sent_key": "2026-08-06:3"},
    }

    checker.check("test_user", entry)

    assert notifier.stale_alerts == []
    assert progress_updates == [("test_user", {"stale_alert_sent_key": None})]

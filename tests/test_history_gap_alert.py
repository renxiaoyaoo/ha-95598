from scripts.support.history_gap_alert import HistoryGapAlertChecker


class FakeDB:
    def __init__(self, missing_dates):
        self.missing_dates = missing_dates
        self.closed = False

    def connect_user_db(self, _user_id):
        return True

    def get_missing_daily_dates(self, _days):
        return self.missing_dates

    def close_connect(self):
        self.closed = True


class FakeNotifier:
    def __init__(self):
        self.gap_alerts = []

    def send_history_gap_alert(self, user_id, first_missing_date, last_missing_date, missing_days):
        self.gap_alerts.append((user_id, first_missing_date, last_missing_date, missing_days))
        return True


def test_history_gap_alert_sends_once_for_same_gap(monkeypatch):
    monkeypatch.setenv("HISTORY_GAP_ALERT_DAYS", "30")
    db = FakeDB(["2026-09-09", "2026-09-10", "2026-09-12"])
    notifier = FakeNotifier()
    progress_updates = []
    checker = HistoryGapAlertChecker(
        notifier,
        lambda user_id, **fields: progress_updates.append((user_id, fields)),
        db,
    )
    entry = {"progress": {}}

    checker.check("test_user", entry)

    assert notifier.gap_alerts == [("test_user", "2026-09-09", "2026-09-12", 3)]
    assert progress_updates == [
        ("test_user", {"history_gap_alert_sent_key": "2026-09-09:2026-09-12:3"})
    ]
    assert db.closed is True

    entry["progress"]["history_gap_alert_sent_key"] = "2026-09-09:2026-09-12:3"
    checker.check("test_user", entry)
    assert len(notifier.gap_alerts) == 1


def test_history_gap_alert_clears_record_when_history_is_continuous():
    db = FakeDB([])
    notifier = FakeNotifier()
    progress_updates = []
    checker = HistoryGapAlertChecker(
        notifier,
        lambda user_id, **fields: progress_updates.append((user_id, fields)),
        db,
    )

    checker.check("test_user", {"progress": {"history_gap_alert_sent_key": "old"}})

    assert notifier.gap_alerts == []
    assert progress_updates == [("test_user", {"history_gap_alert_sent_key": None})]

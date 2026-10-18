from scripts.fetchers.monthly_bill import MonthlyBillFetcher
from scripts.support.db import SqliteDB


class FakeDb:
    MONTHLY_SOURCE_CALCULATED = SqliteDB.MONTHLY_SOURCE_CALCULATED

    def __init__(self, rows):
        self.rows = rows

    def get_recent_monthly_history(self, months):
        assert months == 24
        return self.rows


def make_fetcher(rows):
    return MonthlyBillFetcher(
        db=FakeDb(rows),
        driver_wait_time=1,
        log_page_state=lambda *_args: None,
        step_sleep=lambda *_args: None,
    )


def test_deep_sync_detects_calculated_closed_month():
    fetcher = make_fetcher(
        [
            {"month": "2026-08", "source": "calculated"},
            {"month": "2026-09", "source": "official"},
            {"month": "2026-10", "source": "calculated"},
        ]
    )

    assert fetcher._has_calculated_closed_months(2026, "2026-10") is True


def test_deep_sync_ignores_current_and_other_years():
    fetcher = make_fetcher(
        [
            {"month": "2025-12", "source": "calculated"},
            {"month": "2026-10", "source": "calculated"},
        ]
    )

    assert fetcher._has_calculated_closed_months(2026, "2026-10") is False

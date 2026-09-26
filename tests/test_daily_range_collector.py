import os

from scripts.fetchers.daily_range import DailyRangeFetchService
from scripts.fetchers.vue_daily_range import VueDailyRangeCollector
from scripts.support.db import SqliteDB


def test_normalize_daily_range_row_maps_95598_fields():
    row = VueDailyRangeCollector._normalize_row(
        {
            "date": "2026-05-01",
            "total_usage": "8.31",
            "valley_usage": "2.50",
            "flat_usage": "1.80",
            "peak_usage": "4.01",
            "tip_usage": "—",
        }
    )

    assert row == {
        "date": "2026-05-01",
        "total_usage": 8.31,
        "valley_usage": 2.5,
        "flat_usage": 1.8,
        "peak_usage": 4.01,
        "tip_usage": 0.0,
    }


def test_normalize_daily_range_row_skips_empty_date():
    assert VueDailyRangeCollector._normalize_row({"date": "", "total_usage": "1"}) is None


def test_daily_range_from_fetcher_uses_shared_user_id_resolution():
    class FakeFetcher:
        updater = object()
        IGNORE_USER_ID = []
        create_webdriver = object()
        login_manager = object()
        navigator = type(
            "Navigator",
            (),
            {
                "get_user_ids": lambda self, _driver: ["page_user"],
                "click_button": lambda self, *_args: None,
            },
        )()
        step_sleep = object()
        log_page_state = object()
        db = None
        tou_price_resolver = object()

        def _resolve_user_id_list(self, _driver, updater):
            assert updater is self.updater
            return ["cached_user"]

    service = DailyRangeFetchService.from_data_fetcher(FakeFetcher())

    assert service.user_id_resolver(object()) == ["cached_user"]


def test_range_backfill_recalculates_later_daily_charges(tmp_path):
    class CumulativeResolver:
        def calculate_daily_charge(
            self, _date, valley_usage, flat_usage, peak_usage, tip_usage, month_usage_before
        ):
            return month_usage_before + valley_usage + flat_usage + peak_usage + tip_usage

    os.environ["DB_NAME"] = str(tmp_path / "range_backfill.db")
    db = SqliteDB()
    try:
        assert db.connect_user_db("test_user")
        for date_text, old_charge in (("2026-09-01", 10.0), ("2026-09-03", 20.0)):
            assert db.insert_daily_data(
                {
                    "date": date_text,
                    "total_usage": 10.0,
                    "total_charge": old_charge,
                    "valley_usage": 10.0,
                }
            )
        db.close_connect()

        service = DailyRangeFetchService.__new__(DailyRangeFetchService)
        service.db = db
        service.tou_price_resolver = CumulativeResolver()
        assert service._persist_rows(
            "test_user",
            [
                {
                    "date": "2026-09-02",
                    "total_usage": 10.0,
                    "valley_usage": 10.0,
                    "flat_usage": 0.0,
                    "peak_usage": 0.0,
                    "tip_usage": 0.0,
                }
            ],
        ) == 1

        assert db.connect_user_db("test_user")
        rows = db.get_daily_rows_for_month("2026-09")
        assert [row["total_charge"] for row in rows] == [10.0, 20.0, 30.0]
    finally:
        db.close_connect()
        os.environ.pop("DB_NAME", None)

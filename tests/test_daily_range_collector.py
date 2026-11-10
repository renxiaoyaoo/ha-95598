import os

import pytest

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


def test_automatic_backfill_fills_internal_gap(tmp_path, monkeypatch):
    class FlatResolver:
        def calculate_daily_charge(
            self, _date, valley_usage, flat_usage, peak_usage, tip_usage, _month_usage_before
        ):
            return valley_usage + flat_usage + peak_usage + tip_usage

    class FakeCollector:
        def collect(self, _driver, start_date, end_date):
            assert (start_date, end_date) == ("2026-09-02", "2026-09-02")
            return [
                {
                    "date": "2026-09-02",
                    "total_usage": 4.0,
                    "valley_usage": 1.0,
                    "flat_usage": 1.0,
                    "peak_usage": 2.0,
                    "tip_usage": 0.0,
                }
            ]

    monkeypatch.setenv("DB_NAME", str(tmp_path / "automatic_backfill.db"))
    db = SqliteDB()
    try:
        assert db.connect_user_db("test_user")
        for date_text in ("2026-09-01", "2026-09-03"):
            assert db.insert_daily_data(
                {
                    "date": date_text,
                    "total_usage": 4.0,
                    "total_charge": 4.0,
                    "valley_usage": 1.0,
                    "flat_usage": 1.0,
                    "peak_usage": 2.0,
                    "tip_usage": 0.0,
                }
            )
        db.close_connect()

        service = DailyRangeFetchService.__new__(DailyRangeFetchService)
        service.db = db
        service.collector = FakeCollector()
        service.tou_price_resolver = FlatResolver()

        assert service.backfill_missing(object(), "test_user") == 1
        assert db.connect_user_db("test_user")
        assert db.get_missing_daily_dates(30) == []
    finally:
        db.close_connect()


def test_automatic_backfill_fails_when_gap_remains(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_NAME", str(tmp_path / "incomplete_backfill.db"))
    db = SqliteDB()
    try:
        assert db.connect_user_db("test_user")
        for date_text in ("2026-09-01", "2026-09-03"):
            assert db.insert_daily_data(
                {
                    "date": date_text,
                    "total_usage": 1.0,
                    "total_charge": 1.0,
                    "valley_usage": 1.0,
                }
            )
        db.close_connect()

        service = DailyRangeFetchService.__new__(DailyRangeFetchService)
        service.db = db
        service.collector = type("EmptyCollector", (), {"collect": lambda *_args: []})()
        service.tou_price_resolver = object()

        with pytest.raises(RuntimeError, match="left 1 gap"):
            service.backfill_missing(object(), "test_user")
    finally:
        db.close_connect()


def test_automatic_backfill_splits_non_contiguous_gaps(tmp_path, monkeypatch):
    class FakeCollector:
        calls = []

        def collect(self, _driver, start_date, end_date):
            self.calls.append((start_date, end_date))
            return []

    monkeypatch.setenv("DB_NAME", str(tmp_path / "split_backfill.db"))
    db = SqliteDB()
    try:
        assert db.connect_user_db("test_user")
        for date_text in ("2026-09-01", "2026-09-03", "2026-09-05"):
            assert db.insert_daily_data({"date": date_text, "total_usage": 1.0, "total_charge": 1.0})
        db.close_connect()

        service = DailyRangeFetchService.__new__(DailyRangeFetchService)
        service.db = db
        service.collector = FakeCollector()
        service.tou_price_resolver = object()

        with pytest.raises(RuntimeError, match="left 2 gap"):
            service.backfill_missing(object(), "test_user")
        assert service.collector.calls == [
            ("2026-09-02", "2026-09-02"),
            ("2026-09-04", "2026-09-04"),
        ]
    finally:
        db.close_connect()


def test_missing_daily_dates_can_scan_all_stored_history(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_NAME", str(tmp_path / "all_history_gaps.db"))
    db = SqliteDB()
    try:
        assert db.connect_user_db("test_user")
        for date_text in ("2026-07-01", "2026-07-03", "2026-09-01"):
            assert db.insert_daily_data({"date": date_text, "total_usage": 1.0, "total_charge": 1.0})

        assert "2026-07-02" not in db.get_missing_daily_dates(30)
        assert "2026-07-02" in db.get_missing_daily_dates(days=None)
    finally:
        db.close_connect()

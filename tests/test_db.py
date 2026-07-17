import os
import sqlite3
from datetime import datetime, timedelta

from scripts.const import DAILY_HISTORY_PUBLISH_DAYS, MONTHLY_HISTORY_PUBLISH_MONTHS
from scripts.support.db import SqliteDB


def test_sqlite_three_table_schema(tmp_path) -> None:
    db_path = tmp_path / "test_homeassistant.db"
    os.environ["DB_NAME"] = str(db_path)
    db = SqliteDB()

    try:
        assert db.connect_user_db("test_user") is True
        assert db.insert_daily_data(
            {
                "date": "2026-04-15",
                "total_usage": 5.26,
                "total_charge": None,
                "valley_usage": 1.0,
                "flat_usage": 2.0,
                "peak_usage": 2.26,
                "tip_usage": 0.0,
            }
        ) is True
        assert db.insert_monthly_data(
            {
                "month": "2026-04",
                "total_usage": 146,
                "total_charge": 64.17,
                "valley_usage": 0,
                "flat_usage": 0,
                "peak_usage": 0,
                "tip_usage": 0,
            }
        ) is True
        assert db.insert_yearly_data(
            {
                "year": "2026",
                "total_usage": 495,
                "total_charge": 228.91,
                "valley_usage": 0,
                "flat_usage": 0,
                "peak_usage": 0,
                "tip_usage": 0,
            }
        ) is True
        db.close_connect()

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT user_id, date, total_usage FROM daily_usage")
        assert cur.fetchone() == ("test_user", "2026-04-15", 5.26)

        cur.execute("SELECT user_id, month, total_usage, total_charge FROM monthly_usage")
        assert cur.fetchone() == ("test_user", "2026-04", 146.0, 64.17)

        cur.execute("SELECT user_id, year, total_usage, total_charge FROM yearly_usage")
        assert cur.fetchone() == ("test_user", "2026", 495.0, 228.91)
        conn.close()
    finally:
        os.environ.pop("DB_NAME", None)


def test_sqlite_initializes_clean_schema_without_legacy_migration(tmp_path) -> None:
    db_path = tmp_path / "clean.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE dailytest_user (date DATE PRIMARY KEY NOT NULL, usage REAL NOT NULL)")
    cur.execute("CREATE TABLE datatest_user (name TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)")
    conn.commit()
    conn.close()

    os.environ["DB_NAME"] = str(db_path)
    db = SqliteDB()
    try:
        assert db.connect_user_db("test_user") is True
        db.close_connect()

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM daily_usage WHERE user_id = ?", ("test_user",))
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM monthly_usage WHERE user_id = ?", ("test_user",))
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM yearly_usage WHERE user_id = ?", ("test_user",))
        assert cur.fetchone()[0] == 0
        conn.close()
    finally:
        os.environ.pop("DB_NAME", None)


def test_sync_yearly_from_monthly_aggregates_tou(tmp_path) -> None:
    db_path = tmp_path / "aggregate.db"
    os.environ["DB_NAME"] = str(db_path)
    db = SqliteDB()
    try:
        assert db.connect_user_db("test_user") is True
        assert db.insert_monthly_data(
            {
                "month": "2026-02",
                "total_usage": 100,
                "total_charge": 43.63,
                "valley_usage": 32,
                "flat_usage": 33,
                "peak_usage": 35,
                "tip_usage": 0,
            }
        )
        assert db.insert_monthly_data(
            {
                "month": "2026-03",
                "total_usage": 146,
                "total_charge": 64.17,
                "valley_usage": 45,
                "flat_usage": 47,
                "peak_usage": 54,
                "tip_usage": 0,
            }
        )
        assert db.sync_yearly_from_monthly("2026") is True
        db.close_connect()

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, year, total_usage, total_charge, valley_usage, flat_usage, peak_usage, tip_usage FROM yearly_usage WHERE user_id = ?",
            ("test_user",),
        )
        row = cur.fetchone()
        assert row[0] == "test_user"
        assert row[1] == "2026"
        assert row[2] == 246.0
        assert round(row[3], 2) == 107.8
        assert row[4:] == (77.0, 80.0, 89.0, 0.0)
        conn.close()
    finally:
        os.environ.pop("DB_NAME", None)


def test_sqlite_summary_helpers(tmp_path) -> None:
    db_path = tmp_path / "summary.db"
    os.environ["DB_NAME"] = str(db_path)
    db = SqliteDB()
    today = datetime.now().strftime("%Y-%m-%d")
    current_month = datetime.now().strftime("%Y-%m")
    current_year = datetime.now().strftime("%Y")
    try:
        assert db.connect_user_db("test_user") is True
        assert db.insert_daily_data(
            {
                "date": today,
                "total_usage": 5.26,
                "total_charge": 2.11,
                "valley_usage": 1.0,
                "flat_usage": 2.0,
                "peak_usage": 2.26,
                "tip_usage": 0.0,
            }
        ) is True
        assert db.insert_monthly_data(
            {
                "month": current_month,
                "total_usage": 146,
                "total_charge": 64.17,
                "valley_usage": 32,
                "flat_usage": 33,
                "peak_usage": 35,
                "tip_usage": 0,
            }
        ) is True
        assert db.insert_yearly_data(
            {
                "year": current_year,
                "total_usage": 495,
                "total_charge": 228.91,
                "valley_usage": 77,
                "flat_usage": 80,
                "peak_usage": 89,
                "tip_usage": 0,
            }
        ) is True

        month_summary = db.get_current_month_daily_summary()
        year_summary = db.get_current_year_daily_summary()
        total_monthly_summary = db.get_total_monthly_summary()
        history = db.get_recent_daily_history(days=30)

        assert month_summary is not None
        assert month_summary["period"] == current_month
        assert month_summary["usage"] == 5.26
        assert year_summary is not None
        assert year_summary["period"] == current_year
        assert year_summary["charge"] == 2.11
        assert total_monthly_summary == {"usage": 146.0, "charge": 64.17}
        assert history is not None
        assert history["latest_date"] == today
        assert history["series_days"] == 1
    finally:
        os.environ.pop("DB_NAME", None)


def test_recent_daily_history_default_keeps_180_days_with_usage_and_charge_only(tmp_path) -> None:
    db_path = tmp_path / "history_window.db"
    os.environ["DB_NAME"] = str(db_path)
    db = SqliteDB()
    start_date = datetime(2026, 1, 1)
    try:
        assert db.connect_user_db("test_user") is True
        for offset in range(DAILY_HISTORY_PUBLISH_DAYS + 5):
            day = start_date + timedelta(days=offset)
            assert db.insert_daily_data(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "total_usage": float(offset + 1),
                    "total_charge": float(offset + 1) / 2,
                    "valley_usage": 0.0,
                    "flat_usage": 0.0,
                    "peak_usage": 0.0,
                    "tip_usage": 0.0,
                }
            ) is True

        history = db.get_recent_daily_history()

        assert history is not None
        assert history["series_days"] == DAILY_HISTORY_PUBLISH_DAYS
        assert history["series"][0] == ["2026-01-06", 6.0, 3.0]
        assert history["latest_date"] == "2026-07-04"
        assert history["series"][-1] == ["2026-07-04", 185.0, 92.5]
    finally:
        os.environ.pop("DB_NAME", None)


def test_recent_monthly_history_default_keeps_12_months(tmp_path) -> None:
    db_path = tmp_path / "monthly_history_window.db"
    os.environ["DB_NAME"] = str(db_path)
    db = SqliteDB()
    try:
        assert db.connect_user_db("test_user") is True
        year = 2025
        month = 1
        for offset in range(MONTHLY_HISTORY_PUBLISH_MONTHS + 2):
            period = f"{year:04d}-{month:02d}"
            assert db.insert_monthly_data(
                {
                    "month": period,
                    "total_usage": float(offset + 10),
                    "total_charge": float(offset + 10) / 2,
                    "valley_usage": 1.0,
                    "flat_usage": 2.0,
                    "peak_usage": 3.0,
                    "tip_usage": 0.0,
                }
            ) is True
            month += 1
            if month == 13:
                month = 1
                year += 1

        history = db.get_recent_monthly_history()

        assert len(history) == MONTHLY_HISTORY_PUBLISH_MONTHS
        assert history[0]["month"] == "2025-03"
        assert history[-1]["month"] == "2026-02"
        assert history[-1]["charge"] == 11.5
    finally:
        os.environ.pop("DB_NAME", None)

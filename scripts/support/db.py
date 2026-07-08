import logging
from scripts.support.credentials import mask_user_id
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from scripts.const import DAILY_HISTORY_PUBLISH_DAYS, MONTHLY_HISTORY_PUBLISH_MONTHS


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
LOCAL_DATA_DIR = ROOT_DIR / "data"


class SqliteDB:
    DAILY_TABLE = "daily_usage"
    MONTHLY_TABLE = "monthly_usage"
    YEARLY_TABLE = "yearly_usage"

    def __init__(self) -> None:
        self.connect: Optional[sqlite3.Connection] = None
        self.user_id: Optional[str] = None
        self.db_path = self._resolve_db_path()

    def _resolve_db_path(self) -> Path:
        db_name = os.getenv("DB_NAME", "homeassistant.db")
        db_path = Path(db_name)
        if db_path.is_absolute():
            return db_path
        return LOCAL_DATA_DIR / db_path.name

    def connect_user_db(self, user_id: Any) -> bool:
        try:
            self.user_id = self._normalize_user_id(user_id)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.connect = sqlite3.connect(self.db_path, timeout=30)
            self._configure_connection()
            self._create_schema()
            logging.info("SQLite database ready at %s for user %s", self.db_path, mask_user_id(self.user_id))
            return True
        except (sqlite3.Error, ValueError) as exc:
            logging.error("Failed to prepare sqlite database: %s", exc)
            return False

    def _normalize_user_id(self, user_id: Any) -> str:
        value = str(user_id).strip()
        if not value:
            raise ValueError("user_id can not be empty")
        return value

    def _create_schema(self) -> None:
        assert self.connect is not None
        self.connect.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.DAILY_TABLE} (
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                total_usage REAL NOT NULL,
                total_charge REAL,
                valley_usage REAL NOT NULL DEFAULT 0,
                flat_usage REAL NOT NULL DEFAULT 0,
                peak_usage REAL NOT NULL DEFAULT 0,
                tip_usage REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, date)
            )
            """
        )
        self.connect.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.MONTHLY_TABLE} (
                user_id TEXT NOT NULL,
                month TEXT NOT NULL,
                total_usage REAL NOT NULL,
                total_charge REAL,
                valley_usage REAL NOT NULL DEFAULT 0,
                flat_usage REAL NOT NULL DEFAULT 0,
                peak_usage REAL NOT NULL DEFAULT 0,
                tip_usage REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, month)
            )
            """
        )
        self.connect.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.YEARLY_TABLE} (
                user_id TEXT NOT NULL,
                year TEXT NOT NULL,
                total_usage REAL NOT NULL,
                total_charge REAL,
                valley_usage REAL NOT NULL DEFAULT 0,
                flat_usage REAL NOT NULL DEFAULT 0,
                peak_usage REAL NOT NULL DEFAULT 0,
                tip_usage REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, year)
            )
            """
        )
        self.connect.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.DAILY_TABLE}_user_date ON {self.DAILY_TABLE}(user_id, date)"
        )
        self.connect.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.MONTHLY_TABLE}_user_month ON {self.MONTHLY_TABLE}(user_id, month)"
        )
        self.connect.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self.YEARLY_TABLE}_user_year ON {self.YEARLY_TABLE}(user_id, year)"
        )
        self.connect.commit()

    def _configure_connection(self) -> None:
        assert self.connect is not None
        self.connect.execute("PRAGMA journal_mode=WAL")
        self.connect.execute("PRAGMA synchronous=NORMAL")
        self.connect.execute("PRAGMA temp_store=MEMORY")
        self.connect.execute("PRAGMA foreign_keys=ON")
        self.connect.execute("PRAGMA busy_timeout=5000")

    def insert_daily_data(self, data: dict) -> bool:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return False

        try:
            date = str(data["date"]).strip()
            total_usage = float(data["total_usage"])
            total_charge = self._safe_float(data.get("total_charge"), default=None)
            valley_usage = self._safe_float(data.get("valley_usage"), default=0.0)
            flat_usage = self._safe_float(data.get("flat_usage"), default=0.0)
            peak_usage = self._safe_float(data.get("peak_usage"), default=0.0)
            tip_usage = self._safe_float(data.get("tip_usage"), default=0.0)
            self.connect.execute(
                f"""
                INSERT INTO {self.DAILY_TABLE} (
                    user_id, date, total_usage, total_charge,
                    valley_usage, flat_usage, peak_usage, tip_usage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    total_usage = excluded.total_usage,
                    total_charge = COALESCE(excluded.total_charge, {self.DAILY_TABLE}.total_charge),
                    valley_usage = COALESCE(excluded.valley_usage, {self.DAILY_TABLE}.valley_usage),
                    flat_usage = COALESCE(excluded.flat_usage, {self.DAILY_TABLE}.flat_usage),
                    peak_usage = COALESCE(excluded.peak_usage, {self.DAILY_TABLE}.peak_usage),
                    tip_usage = COALESCE(excluded.tip_usage, {self.DAILY_TABLE}.tip_usage),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    self.user_id,
                    date,
                    total_usage,
                    total_charge,
                    valley_usage,
                    flat_usage,
                    peak_usage,
                    tip_usage,
                ),
            )
            self.connect.commit()
            return True
        except (KeyError, TypeError, ValueError, sqlite3.Error) as exc:
            logging.error("Failed to insert daily data: %s", exc)
            return False

    def insert_monthly_data(self, data: dict) -> bool:
        return self._upsert_period_data(self.MONTHLY_TABLE, "month", data)

    def insert_yearly_data(self, data: dict) -> bool:
        return self._upsert_period_data(self.YEARLY_TABLE, "year", data)

    def get_month_total_usage_before(self, date_text: str) -> float:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return 0.0

        month = str(date_text).strip()[:7]
        cursor = self.connect.cursor()
        try:
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(total_usage), 0)
                FROM {self.DAILY_TABLE}
                WHERE user_id = ?
                  AND substr(date, 1, 7) = ?
                  AND date < ?
                """,
                (self.user_id, month, date_text),
            )
            result = cursor.fetchone()
            return float(result[0] or 0.0)
        finally:
            cursor.close()

    def get_period_tou_values(self, table_name: str, period_key: str, period_value: str) -> dict[str, float]:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return {}

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                f"""
                SELECT valley_usage, flat_usage, peak_usage, tip_usage
                FROM {table_name}
                WHERE user_id = ? AND {period_key} = ?
                """,
                (self.user_id, str(period_value).strip()),
            )
            row = cursor.fetchone()
            if row is None:
                return {}
            return {
                "valley_usage": float(row[0] or 0.0),
                "flat_usage": float(row[1] or 0.0),
                "peak_usage": float(row[2] or 0.0),
                "tip_usage": float(row[3] or 0.0),
            }
        finally:
            cursor.close()

    def get_daily_tou_values(self, date_text: str) -> dict[str, float]:
        return self.get_period_tou_values(self.DAILY_TABLE, "date", date_text)

    def get_period_row(self, table_name: str, period_key: str, period_value: str) -> dict[str, Optional[float]] | None:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return None

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                f"""
                SELECT total_usage, total_charge, valley_usage, flat_usage, peak_usage, tip_usage
                FROM {table_name}
                WHERE user_id = ? AND {period_key} = ?
                """,
                (self.user_id, str(period_value).strip()),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "total_usage": self._safe_float(row[0], default=None),
                "total_charge": self._safe_float(row[1], default=None),
                "valley_usage": self._safe_float(row[2], default=0.0),
                "flat_usage": self._safe_float(row[3], default=0.0),
                "peak_usage": self._safe_float(row[4], default=0.0),
                "tip_usage": self._safe_float(row[5], default=0.0),
            }
        finally:
            cursor.close()

    def _get_daily_month_summary(self, month: str) -> dict[str, Optional[float]] | None:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return None

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(total_usage), 0),
                    COALESCE(SUM(COALESCE(total_charge, 0)), 0),
                    COALESCE(SUM(valley_usage), 0),
                    COALESCE(SUM(flat_usage), 0),
                    COALESCE(SUM(peak_usage), 0),
                    COALESCE(SUM(tip_usage), 0),
                    COUNT(*)
                FROM daily_usage
                WHERE user_id = ? AND substr(date, 1, 7) = ?
                """,
                (self.user_id, month),
            )
            row = cursor.fetchone()
            if row is None or row[6] == 0:
                return None
            return {
                "period": month,
                "usage": round(self._safe_float(row[0], default=0.0), 2),
                "charge": round(self._safe_float(row[1], default=0.0), 2),
                "valley_usage": round(self._safe_float(row[2], default=0.0), 2),
                "flat_usage": round(self._safe_float(row[3], default=0.0), 2),
                "peak_usage": round(self._safe_float(row[4], default=0.0), 2),
                "tip_usage": round(self._safe_float(row[5], default=0.0), 2),
            }
        finally:
            cursor.close()

    def get_current_month_daily_summary(self) -> dict[str, Optional[float]] | None:
        return self._get_daily_month_summary(datetime.now().strftime("%Y-%m"))

    def get_latest_daily_row(self) -> dict[str, Optional[float]] | None:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return None

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                """
                SELECT date, total_usage, total_charge, valley_usage, flat_usage, peak_usage, tip_usage
                FROM daily_usage
                WHERE user_id = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (self.user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "date": row[0],
                "usage": self._safe_float(row[1], default=0.0),
                "charge": self._safe_float(row[2], default=0.0),
                "valley_usage": self._safe_float(row[3], default=0.0),
                "flat_usage": self._safe_float(row[4], default=0.0),
                "peak_usage": self._safe_float(row[5], default=0.0),
                "tip_usage": self._safe_float(row[6], default=0.0),
            }
        finally:
            cursor.close()

    def get_latest_daily_month_summary(self) -> dict[str, Optional[float]] | None:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return None

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                """
                SELECT MAX(substr(date, 1, 7))
                FROM daily_usage
                WHERE user_id = ?
                """,
                (self.user_id,),
            )
            row = cursor.fetchone()
            month = row[0] if row else None
        finally:
            cursor.close()
        return self._get_daily_month_summary(month) if month else None

    def get_current_year_daily_summary(self) -> dict[str, Optional[float]] | None:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return None

        year = datetime.now().strftime("%Y")
        cursor = self.connect.cursor()
        try:
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(total_usage), 0),
                    COALESCE(SUM(COALESCE(total_charge, 0)), 0),
                    COALESCE(SUM(valley_usage), 0),
                    COALESCE(SUM(flat_usage), 0),
                    COALESCE(SUM(peak_usage), 0),
                    COALESCE(SUM(tip_usage), 0),
                    COUNT(*)
                FROM daily_usage
                WHERE user_id = ? AND substr(date, 1, 4) = ?
                """,
                (self.user_id, year),
            )
            row = cursor.fetchone()
            if row is None or row[6] == 0:
                return None
            return {
                "period": year,
                "usage": round(self._safe_float(row[0], default=0.0), 2),
                "charge": round(self._safe_float(row[1], default=0.0), 2),
                "valley_usage": round(self._safe_float(row[2], default=0.0), 2),
                "flat_usage": round(self._safe_float(row[3], default=0.0), 2),
                "peak_usage": round(self._safe_float(row[4], default=0.0), 2),
                "tip_usage": round(self._safe_float(row[5], default=0.0), 2),
            }
        finally:
            cursor.close()

    def get_total_monthly_summary(self) -> dict[str, Optional[float]] | None:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return None

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(total_usage), 0),
                    COALESCE(SUM(COALESCE(total_charge, 0)), 0),
                    COUNT(*)
                FROM monthly_usage
                WHERE user_id = ?
                """,
                (self.user_id,),
            )
            row = cursor.fetchone()
            if row is None or row[2] == 0:
                return None
            return {
                "usage": round(self._safe_float(row[0], default=0.0), 2),
                "charge": round(self._safe_float(row[1], default=0.0), 2),
            }
        finally:
            cursor.close()

    def get_recent_daily_history(self, days: int = DAILY_HISTORY_PUBLISH_DAYS) -> dict[str, Any] | None:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return None

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                """
                SELECT date, total_usage, COALESCE(total_charge, 0)
                FROM daily_usage
                WHERE user_id = ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (self.user_id, days),
            )
            rows = cursor.fetchall()
            if not rows:
                return None
            rows.reverse()
            series = [
                {
                    "date": row[0],
                    "usage": self._safe_float(row[1], default=0.0),
                    "charge": self._safe_float(row[2], default=0.0),
                }
                for row in rows
            ]
            latest = series[-1]
            return {
                "state": latest["usage"],
                "latest_date": latest["date"],
                "series_days": len(series),
                "series": series,
            }
        finally:
            cursor.close()

    def get_recent_monthly_history(self, months: int = MONTHLY_HISTORY_PUBLISH_MONTHS) -> list[dict[str, Any]]:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return []

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                """
                SELECT month, total_usage, COALESCE(total_charge, 0), valley_usage, flat_usage, peak_usage, tip_usage
                FROM monthly_usage
                WHERE user_id = ?
                ORDER BY month DESC
                LIMIT ?
                """,
                (self.user_id, months),
            )
            rows = cursor.fetchall()
            rows.reverse()
            return [
                {
                    "month": row[0],
                    "usage": self._safe_float(row[1], default=0.0),
                    "charge": self._safe_float(row[2], default=0.0),
                    "valley_usage": self._safe_float(row[3], default=0.0),
                    "flat_usage": self._safe_float(row[4], default=0.0),
                    "peak_usage": self._safe_float(row[5], default=0.0),
                    "tip_usage": self._safe_float(row[6], default=0.0),
                }
                for row in rows
            ]
        finally:
            cursor.close()

    def sync_yearly_from_monthly(self, year: str) -> bool:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return False

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                f"""
                SELECT
                    COALESCE(SUM(total_usage), 0),
                    COALESCE(SUM(total_charge), 0),
                    COALESCE(SUM(valley_usage), 0),
                    COALESCE(SUM(flat_usage), 0),
                    COALESCE(SUM(peak_usage), 0),
                    COALESCE(SUM(tip_usage), 0)
                FROM {self.MONTHLY_TABLE}
                WHERE user_id = ? AND substr(month, 1, 4) = ?
                """,
                (self.user_id, str(year).strip()),
            )
            monthly_sum = cursor.fetchone()
            if monthly_sum is None:
                return False

            return self.insert_yearly_data(
                {
                    "year": year,
                    "total_usage": self._safe_float(monthly_sum[0], default=0.0),
                    "total_charge": self._safe_float(monthly_sum[1], default=0.0),
                    "valley_usage": self._safe_float(monthly_sum[2], default=0.0),
                    "flat_usage": self._safe_float(monthly_sum[3], default=0.0),
                    "peak_usage": self._safe_float(monthly_sum[4], default=0.0),
                    "tip_usage": self._safe_float(monthly_sum[5], default=0.0),
                }
            )
        finally:
            cursor.close()

    def sync_monthly_from_daily(self, month: str) -> bool:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return False

        cursor = self.connect.cursor()
        try:
            cursor.execute(
                f"""
                SELECT
                    COALESCE(SUM(total_usage), 0),
                    COALESCE(SUM(total_charge), 0),
                    COALESCE(SUM(valley_usage), 0),
                    COALESCE(SUM(flat_usage), 0),
                    COALESCE(SUM(peak_usage), 0),
                    COALESCE(SUM(tip_usage), 0),
                    COUNT(*)
                FROM {self.DAILY_TABLE}
                WHERE user_id = ? AND substr(date, 1, 7) = ?
                """,
                (self.user_id, str(month).strip()),
            )
            daily_sum = cursor.fetchone()
            if daily_sum is None or daily_sum[6] == 0:
                return False

            return self.insert_monthly_data(
                {
                    "month": month,
                    "total_usage": self._safe_float(daily_sum[0], default=0.0),
                    "total_charge": self._safe_float(daily_sum[1], default=0.0),
                    "valley_usage": self._safe_float(daily_sum[2], default=0.0),
                    "flat_usage": self._safe_float(daily_sum[3], default=0.0),
                    "peak_usage": self._safe_float(daily_sum[4], default=0.0),
                    "tip_usage": self._safe_float(daily_sum[5], default=0.0),
                }
            )
        finally:
            cursor.close()

    def _upsert_period_data(self, table_name: str, period_key: str, data: dict) -> bool:
        if self.connect is None or self.user_id is None:
            logging.error("Database connection is not established.")
            return False

        try:
            period_value = str(data[period_key]).strip()
            total_usage = float(data["total_usage"])
            total_charge = self._safe_float(data.get("total_charge"), default=None)
            valley_usage = self._safe_float(data.get("valley_usage"), default=0.0)
            flat_usage = self._safe_float(data.get("flat_usage"), default=0.0)
            peak_usage = self._safe_float(data.get("peak_usage"), default=0.0)
            tip_usage = self._safe_float(data.get("tip_usage"), default=0.0)
            self.connect.execute(
                f"""
                INSERT INTO {table_name} (
                    user_id, {period_key}, total_usage, total_charge,
                    valley_usage, flat_usage, peak_usage, tip_usage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, {period_key}) DO UPDATE SET
                    total_usage = excluded.total_usage,
                    total_charge = COALESCE(excluded.total_charge, {table_name}.total_charge),
                    valley_usage = COALESCE(excluded.valley_usage, {table_name}.valley_usage),
                    flat_usage = COALESCE(excluded.flat_usage, {table_name}.flat_usage),
                    peak_usage = COALESCE(excluded.peak_usage, {table_name}.peak_usage),
                    tip_usage = COALESCE(excluded.tip_usage, {table_name}.tip_usage),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    self.user_id,
                    period_value,
                    total_usage,
                    total_charge,
                    valley_usage,
                    flat_usage,
                    peak_usage,
                    tip_usage,
                ),
            )
            self.connect.commit()
            return True
        except (KeyError, TypeError, ValueError, sqlite3.Error) as exc:
            logging.error("Failed to insert %s data: %s", table_name, exc)
            return False

    def _safe_float(self, value: Any, default: Optional[float] = 0.0) -> Optional[float]:
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        try:
            return float(text)
        except (TypeError, ValueError):
            logging.debug("Failed to parse float value: %s", value)
            return default

    def close_connect(self) -> None:
        if self.connect is not None:
            self.connect.close()
            self.connect = None
            self.user_id = None
            logging.info("SQLite database connection closed.")

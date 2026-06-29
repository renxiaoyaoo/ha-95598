import logging
import os
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.tools.backfill_ha_energy_statistics import (
    backfill_one_statistic,
    backup_db,
    build_daily_boundary_points,
    load_daily_rows,
    normalize_sum_to_state,
)


class HaEnergyStatisticsBackfiller:
    """Synchronize daily rows into Home Assistant long-term statistics.

    MQTT publishes the current cumulative sensor state. Home Assistant's energy
    dashboard, however, reads the recorder statistics tables. If several missed
    days are fetched at once, this optional backfill writes the cumulative points
    to each real day boundary so the energy dashboard does not assign all usage
    to the catch-up day.
    """

    def __init__(self, source_db: Path):
        self.source_db = source_db

    @staticmethod
    def enabled() -> bool:
        return os.getenv("HA_ENERGY_BACKFILL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

    def run(self, user_id: str) -> bool:
        if not self.enabled():
            return False

        ha_db = Path(os.getenv("HA_RECORDER_DB_PATH", "").strip())
        if not str(ha_db):
            logging.warning("HA energy backfill is enabled but HA_RECORDER_DB_PATH is missing.")
            return False
        if not ha_db.exists():
            logging.warning("HA recorder database does not exist: %s", ha_db)
            return False
        if not self.source_db.exists():
            logging.warning("Local source database does not exist: %s", self.source_db)
            return False

        timezone_name = os.getenv("HA_ENERGY_BACKFILL_TIMEZONE", "Asia/Shanghai")
        reconcile_monthly = self._truthy("HA_ENERGY_BACKFILL_RECONCILE_MONTHLY", "true")
        clamp_after_last = self._truthy("HA_ENERGY_BACKFILL_CLAMP_AFTER_LAST", "true")
        create_backup = self._truthy("HA_ENERGY_BACKFILL_BACKUP", "false")

        try:
            daily_rows = load_daily_rows(self.source_db, user_id, reconcile_monthly_totals=reconcile_monthly)
            if not daily_rows:
                logging.info("No local daily rows found; skip HA energy statistics backfill.")
                return False
            usage_points = build_daily_boundary_points(daily_rows, ZoneInfo(timezone_name), "usage")
            charge_points = build_daily_boundary_points(daily_rows, ZoneInfo(timezone_name), "charge")

            conn = sqlite3.connect(ha_db, timeout=30)
            try:
                usage_statistic_id = os.getenv("HA_ENERGY_USAGE_STATISTIC_ID", "").strip() or self._find_statistic_id(
                    conn, user_id, "total_electricity_usage"
                )
                charge_statistic_id = os.getenv("HA_ENERGY_CHARGE_STATISTIC_ID", "").strip() or self._find_statistic_id(
                    conn, user_id, "total_electricity_charge"
                )
                if not usage_statistic_id or not charge_statistic_id:
                    logging.warning("HA energy statistic ids were not found; skip recorder backfill.")
                    return False

                if create_backup:
                    logging.info("HA recorder backup created at %s", backup_db(ha_db))

                usage_result = backfill_one_statistic(
                    conn,
                    usage_statistic_id,
                    usage_points,
                    clamp_after_last=clamp_after_last,
                )
                charge_result = backfill_one_statistic(
                    conn,
                    charge_statistic_id,
                    charge_points,
                    clamp_after_last=clamp_after_last,
                )
                usage_result["normalized"] = normalize_sum_to_state(conn, usage_result["metadata_id"])
                charge_result["normalized"] = normalize_sum_to_state(conn, charge_result["metadata_id"])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

            logging.info(
                "HA energy statistics backfilled: days=%s latest=%s usage_total=%.2f charge_total=%.2f",
                len(daily_rows),
                daily_rows[-1].day,
                usage_points[-1].sum,
                charge_points[-1].sum,
            )
            return True
        except Exception as exc:
            logging.warning("HA energy statistics backfill failed: %s", exc)
            return False

    @staticmethod
    def _truthy(name: str, default: str = "false") -> bool:
        return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _find_statistic_id(conn: sqlite3.Connection, user_id: str, metric: str) -> str | None:
        suffix = user_id[-4:]
        exact_candidates = [
            f"sensor.95598_{suffix}_{metric}_{suffix}",
            f"sensor.{metric}_{suffix}",
        ]
        for candidate in exact_candidates:
            row = conn.execute("SELECT statistic_id FROM statistics_meta WHERE statistic_id = ?", (candidate,)).fetchone()
            if row:
                return str(row[0])

        rows = conn.execute(
            """
            SELECT statistic_id
            FROM statistics_meta
            WHERE statistic_id LIKE ?
            ORDER BY length(statistic_id), statistic_id
            """,
            (f"%{metric}%{suffix}%",),
        ).fetchall()
        return str(rows[0][0]) if rows else None

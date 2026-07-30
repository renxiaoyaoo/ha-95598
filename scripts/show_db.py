import argparse
import json
import sqlite3
from pathlib import Path

from scripts.support.credentials import mask_user_id
from scripts.support.tou_price import TimeOfUsePriceResolver


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "homeassistant.db"
CACHE_PATH = DATA_DIR / "ha_95598_cache.json"


def show_sqlite_db() -> None:
    if not DB_PATH.exists():
        print(f"SQLite database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    tables = []
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cur.fetchall()]

    print(f"SQLite database: {DB_PATH}")
    print(f"Tables: {', '.join(tables) if tables else '(none)'}")

    for table in ("daily_usage", "monthly_usage", "yearly_usage"):
        if table not in tables:
            continue
        print(f"\n[{table}]")
        order_column = "date" if table == "daily_usage" else "month" if table == "monthly_usage" else "year"
        cur.execute(
            f"""
            SELECT user_id, MIN({order_column}), MAX({order_column}), COUNT(*)
            FROM {table}
            GROUP BY user_id
            ORDER BY user_id
            """
        )
        summary_rows = cur.fetchall()
        if not summary_rows:
            print("(empty)")
            continue
        for user_id, first_period, latest_period, count in summary_rows:
            print(
                f"user={mask_user_id(user_id)} first={first_period} latest={latest_period} rows={count}"
            )
    conn.close()


def show_cache(*, details: bool = False) -> None:
    if not CACHE_PATH.exists():
        print(f"\nCache file not found: {CACHE_PATH}")
        return

    print(f"\nCache file: {CACHE_PATH}")
    with open(CACHE_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        print("Cache content is not an object")
        return

    print(f"Users: {len(data)}")
    for user_id, entry in data.items():
        user_data = entry.get("data", {}) if isinstance(entry, dict) else {}
        progress = entry.get("progress", {}) if isinstance(entry, dict) else {}
        print(
            "user=%s latest_daily_date=%s stage=%s"
            % (
                mask_user_id(user_id),
                user_data.get("last_daily_date"),
                progress.get("stage"),
            )
        )
        if details:
            safe_entry = {
                "data_keys": sorted(user_data.keys()) if isinstance(user_data, dict) else [],
                "progress": progress,
            }
            print(json.dumps(safe_entry, ensure_ascii=False, indent=2))


def show_tou_config() -> None:
    resolver = TimeOfUsePriceResolver()
    print(f"\nTOU config: {resolver.config_path}")
    if not resolver.config_path.exists():
        print("TOU config not found")
        return
    with open(resolver.config_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    versions = data.get("versions", []) if isinstance(data, dict) else []
    print(f"Versions: {len(versions)}")
    for version in versions:
        if not isinstance(version, dict):
            continue
        print(
            "effective_from=%s rules=%s"
            % (
                version.get("effective_from"),
                len(version.get("season_rules") or []),
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show a privacy-safe summary of local ha-95598 data.")
    parser.add_argument("--details", action="store_true", help="Show cache metadata keys. Database rows are never printed.")
    args = parser.parse_args()

    show_sqlite_db()
    show_cache(details=args.details)
    show_tou_config()

#!/usr/bin/env python3
"""Update the public field-data badge endpoint JSON."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_START_DATE = "2025-09-01"
DEFAULT_LAG_DAYS = "3"
DEFAULT_BADGE_PATH = "docs/field-data-badge.json"


def _read_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    start_date = _read_date(os.getenv("FIELD_DATA_START_DATE", DEFAULT_START_DATE))
    lag_days = int(os.getenv("FIELD_DATA_LAG_DAYS", DEFAULT_LAG_DAYS))
    badge_path = root / os.getenv("FIELD_DATA_BADGE_PATH", DEFAULT_BADGE_PATH)

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    verified_until = today - timedelta(days=lag_days)
    field_days = max((verified_until - start_date).days + 1, 0)

    badge = {
        "schemaVersion": 1,
        "label": "field data",
        "message": f"{field_days} days",
        "color": "2ea44f",
        "style": "for-the-badge",
        "namedLogo": "homeassistant",
        "logoColor": "white",
    }

    badge_path.parent.mkdir(parents=True, exist_ok=True)
    badge_path.write_text(json.dumps(badge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"field data badge updated: {field_days} days")


if __name__ == "__main__":
    main()

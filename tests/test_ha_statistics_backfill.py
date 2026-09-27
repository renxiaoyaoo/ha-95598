from datetime import date
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.tools.backfill_ha_energy_statistics import (
    DailyEnergyRow,
    build_daily_boundary_points,
    prune_backups,
)


def test_build_daily_boundary_points_uses_previous_day_cumulative_sum():
    rows = [
        DailyEnergyRow(day=date(2026, 1, 1), usage=1.5, charge=0.7),
        DailyEnergyRow(day=date(2026, 1, 2), usage=2.0, charge=0.9),
    ]

    points = build_daily_boundary_points(rows, ZoneInfo("Asia/Shanghai"), "usage")

    assert [point.sum for point in points] == [0.0, 1.5, 3.5]
    assert [point.state for point in points] == [0.0, 1.5, 3.5]


def test_prune_backups_keeps_newest_files(tmp_path: Path):
    database = tmp_path / "recorder.db"
    database.write_text("current", encoding="utf-8")
    for index in range(4):
        backup = tmp_path / f"recorder.db.bak.{index}"
        backup.write_text(str(index), encoding="utf-8")
        os.utime(backup, (index, index))

    assert prune_backups(database, keep=2) == 2
    assert len(list(tmp_path.glob("recorder.db.bak.*"))) == 2

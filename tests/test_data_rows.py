from scripts.support.data_rows import DailyUsageRow


def test_daily_usage_row_default_dict_matches_existing_shape():
    row = DailyUsageRow(
        date="2026-08-01",
        total_usage=8.31,
        valley_usage=2.5,
        flat_usage=1.8,
        peak_usage=4.01,
    )

    assert row.to_dict() == {
        "date": "2026-08-01",
        "total_usage": 8.31,
        "valley_usage": 2.5,
        "flat_usage": 1.8,
        "peak_usage": 4.01,
        "tip_usage": 0.0,
    }


def test_daily_usage_row_can_include_charge_when_needed():
    row = DailyUsageRow(date="2026-08-01", total_usage=8.31, total_charge=4.12)

    assert row.to_dict(include_charge=True)["total_charge"] == 4.12

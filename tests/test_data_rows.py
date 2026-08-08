from scripts.support.data_rows import DailyUsageRow, MonthlyBillRow, MonthlyUsageRow


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


def test_monthly_usage_row_default_dict_matches_db_shape():
    row = MonthlyUsageRow(
        month="2026-08",
        total_usage=77.75,
        total_charge=33.1,
        valley_usage=20.0,
        flat_usage=30.0,
        peak_usage=27.75,
    )

    assert row.to_dict() == {
        "month": "2026-08",
        "total_usage": 77.75,
        "total_charge": 33.1,
        "valley_usage": 20.0,
        "flat_usage": 30.0,
        "peak_usage": 27.75,
        "tip_usage": 0.0,
    }


def test_monthly_usage_row_can_include_source():
    row = MonthlyUsageRow(
        month="2026-08",
        total_usage=77.75,
        total_charge=33.1,
        source="calculated",
    )

    assert row.to_dict(include_source=True)["source"] == "calculated"


def test_monthly_bill_row_uses_official_dict_shape():
    row = MonthlyBillRow(month="2026-07", total_usage=576.0, total_charge=298.04)

    assert row.to_official_dict() == {
        "month": "2026-07",
        "total_usage": 576.0,
        "total_charge": 298.04,
        "valley_usage": 0.0,
        "flat_usage": 0.0,
        "peak_usage": 0.0,
        "tip_usage": 0.0,
    }

from scripts.support.monthly_billing import MonthlyBillingService


class FakeMonthlyDb:
    def __init__(self):
        self.rows = {
            "2026-07": {
                "month": "2026-07",
                "total_usage": 576.0,
                "total_charge": 298.04,
                "valley_usage": 10.0,
                "flat_usage": 20.0,
                "peak_usage": 30.0,
                "tip_usage": 0.0,
            }
        }
        self.official_rows = []
        self.refreshed_years = []

    def get_period_row(self, table_name, period_key, period_value):
        assert table_name == "monthly_usage"
        assert period_key == "month"
        return self.rows.get(period_value)

    def upsert_official_monthly_bill(self, row):
        self.official_rows.append(row)
        self.rows[row["month"]] = row
        return True

    def get_period_tou_values(self, table_name, period_key, period_value):
        assert table_name == "monthly_usage"
        assert period_key == "month"
        return self.rows.get(period_value, {})

    def insert_monthly_data(self, row):
        self.rows[row["month"]] = row
        return True

    def upsert_calculated_monthly_from_daily(self, month):
        self.rows[month] = {"month": month, "source": "calculated"}
        return True

    def refresh_year_from_months(self, year):
        self.refreshed_years.append(year)
        return True


def test_official_bill_uses_existing_usage_when_detail_is_partial():
    db = FakeMonthlyDb()
    service = MonthlyBillingService(db)

    month = service.upsert_official_bill(
        {
            "month": "2026-07",
            "total_usage": None,
            "total_charge": None,
            "valley_usage": 166,
            "flat_usage": 224,
            "peak_usage": 186,
            "tip_usage": 0,
        }
    )

    assert month == "2026-07"
    assert db.official_rows == [
        {
            "month": "2026-07",
            "total_usage": 576.0,
            "total_charge": 298.04,
            "valley_usage": 166,
            "flat_usage": 224,
            "peak_usage": 186,
            "tip_usage": 0,
        }
    ]


def test_visible_month_keeps_existing_tou_values():
    db = FakeMonthlyDb()
    service = MonthlyBillingService(db)

    month = service.upsert_visible_month(
        month="7月",
        total_usage=500,
        total_charge=250,
        reference_year="2026",
    )

    assert month == "2026-07"
    assert db.rows["2026-07"] == {
        "month": "2026-07",
        "total_usage": 500,
        "total_charge": 250,
        "valley_usage": 10.0,
        "flat_usage": 20.0,
        "peak_usage": 30.0,
        "tip_usage": 0.0,
    }


def test_refresh_years_for_months_deduplicates_years():
    db = FakeMonthlyDb()
    service = MonthlyBillingService(db)

    service.refresh_years_for_months(["2026-07", "8月", "2025-12"], reference_year="2026")

    assert db.refreshed_years == ["2025", "2026"]

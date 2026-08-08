from scripts.support.fetch_result import FetchResult


def test_fetch_result_keeps_legacy_tuple_order():
    result = FetchResult(
        balance=1,
        last_daily_date="2026-08-01",
        last_daily_usage=2,
        last_daily_charge=3,
        yearly_charge=4,
        yearly_usage=5,
        month_charge=6,
        month_usage=7,
        valley_usage=8,
        flat_usage=9,
        peak_usage=10,
        tip_usage=11,
    )

    assert tuple(result) == (1, "2026-08-01", 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)

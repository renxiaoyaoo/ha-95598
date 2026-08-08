from scripts.support.user_state import UserStateSnapshot


def test_user_state_snapshot_round_trips_cache_data():
    snapshot = UserStateSnapshot(
        balance=60.52,
        last_daily_date="2026-08-06",
        last_daily_usage=12.18,
        last_daily_charge=5.03,
        timestamp="2026-08-09T12:00:00",
    )

    cache_data = snapshot.to_cache_data()

    assert cache_data["balance"] == 60.52
    assert cache_data["last_daily_date"] == "2026-08-06"
    assert cache_data["timestamp"] == "2026-08-09T12:00:00"
    assert UserStateSnapshot.from_cache_data(cache_data).to_update_kwargs()["last_daily_charge"] == 5.03


def test_user_state_snapshot_ignores_unknown_cache_fields():
    snapshot = UserStateSnapshot.from_cache_data(
        {
            "balance": 1.23,
            "unexpected": "ignored",
        }
    )

    assert snapshot.to_update_kwargs()["balance"] == 1.23
    assert "unexpected" not in snapshot.to_cache_data()

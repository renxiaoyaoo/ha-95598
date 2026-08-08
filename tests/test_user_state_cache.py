from scripts.support.cache_store import CacheStore
from scripts.support.user_state import UserStateSnapshot
from scripts.support.user_state_cache import UserStateCache


def test_user_state_cache_saves_typed_snapshot(tmp_path):
    cache = UserStateCache(CacheStore(tmp_path / "cache.json"))

    cache.save_snapshot(
        "user1",
        UserStateSnapshot(
            balance=60.52,
            last_daily_date="2026-08-06",
            last_daily_usage=12.18,
            last_daily_charge=5.03,
        ),
    )

    snapshots = list(cache.iter_snapshots())

    assert len(snapshots) == 1
    user_id, snapshot = snapshots[0]
    assert user_id == "user1"
    assert snapshot.to_update_kwargs()["balance"] == 60.52
    assert snapshot.to_update_kwargs()["last_daily_date"] == "2026-08-06"


def test_user_state_cache_ignores_invalid_entries(tmp_path):
    store = CacheStore(tmp_path / "cache.json")
    store.save({"user1": "invalid"})
    cache = UserStateCache(store)

    assert list(cache.iter_snapshots()) == []

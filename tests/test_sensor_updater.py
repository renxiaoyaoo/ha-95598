from scripts.sensor_updater import SensorUpdater
from scripts.support.user_state import UserStateSnapshot


def test_public_sensor_name_removes_account_suffix():
    assert SensorUpdater._public_sensor_name("sensor.last_electricity_usage_0000") == "sensor.last_electricity_usage"
    assert SensorUpdater._public_sensor_name("sensor.last_electricity_usage") == "sensor.last_electricity_usage"


def test_discovery_is_published_once_per_sensor(monkeypatch):
    updater = SensorUpdater()
    published = []

    def fake_publish(topic, payload, retain=None):
        published.append((topic, payload, retain))
        return True

    monkeypatch.setattr(updater, "_publish_mqtt", fake_publish)

    updater._publish_sensor_state(
        "sensor.test_history_0000",
        "test-user-0000",
        1.0,
        unit="kWh",
        icon="mdi:test-tube",
        device_class="energy",
        state_class="",
        extra_attributes={"series": [["2026-01-01", 1.0, 0.5]]},
    )
    updater._publish_sensor_state(
        "sensor.test_history_0000",
        "test-user-0000",
        2.0,
        unit="kWh",
        icon="mdi:test-tube",
        device_class="energy",
        state_class="",
        extra_attributes={"series": [["2026-01-02", 2.0, 1.0]]},
    )

    discovery = [item for item in published if item[0].endswith("/config")]
    states = [item for item in published if item[0].endswith("/state")]
    assert len(discovery) == 1
    assert len(states) == 2


def test_discovery_is_retried_when_publish_is_skipped(monkeypatch):
    updater = SensorUpdater()
    published = []

    def fake_publish(topic, payload, retain=None):
        published.append((topic, payload, retain))
        return not topic.endswith("/config")

    monkeypatch.setattr(updater, "_publish_mqtt", fake_publish)

    for state in (1.0, 2.0):
        updater._publish_sensor_state(
            "sensor.test_history_0000",
            "test-user-0000",
            state,
            unit="kWh",
            icon="mdi:test-tube",
            device_class="energy",
            state_class="",
        )

    discovery = [item for item in published if item[0].endswith("/config")]
    assert len(discovery) == 2


def test_mark_cached_fetches_failed_updates_each_non_ignored_user(monkeypatch):
    updater = SensorUpdater()
    monkeypatch.setattr(
        updater.cache_store,
        "load",
        lambda: {
            "test-user-0000": {
                "data": {"last_daily_date": "2026-01-01", "last_fetch_success_at": "2026-01-02T00:00:00"},
                "progress": {"stage": "daily"},
            },
            "ignored-user-1111": {"data": {}, "progress": {}},
        },
    )
    statuses = []
    stale_checks = []
    monkeypatch.setattr(updater, "update_fetch_status", lambda *args, **kwargs: statuses.append((args, kwargs)))
    monkeypatch.setattr(updater, "_check_and_notify_stale_data", lambda user_id, entry: stale_checks.append(user_id))

    assert updater.mark_cached_fetches_failed("TimeoutError", ["ignored-user-1111"]) == 1
    assert statuses[0][0][2] == "failed"
    assert statuses[0][1]["error_type"] == "TimeoutError"
    assert statuses[0][1]["stage"] == "daily"
    assert stale_checks == ["test-user-0000"]


def test_republish_preserves_cached_fetch_status_timestamps(monkeypatch):
    updater = SensorUpdater()
    cached_entry = {
        "data": {
            "fetch_status": "ok",
            "last_daily_date": "2026-01-01",
            "last_fetch_success_at": "2026-01-02T03:04:05",
            "last_fetch_attempt_at": "2026-01-02T03:00:00",
            "last_fetch_error_type": None,
        },
        "progress": {"stage": "complete"},
    }
    monkeypatch.setattr(updater.cache_store, "load", lambda: {"test-user-0000": cached_entry})
    monkeypatch.setattr(
        updater.user_state_cache,
        "iter_snapshots",
        lambda: iter([("test-user-0000", UserStateSnapshot(last_daily_date="2026-01-01"))]),
    )
    user_updates = []
    status_updates = []
    monkeypatch.setattr(updater, "update_one_userid", lambda *args, **kwargs: user_updates.append((args, kwargs)))
    monkeypatch.setattr(updater, "update_fetch_status", lambda *args, **kwargs: status_updates.append((args, kwargs)))

    assert updater.republish() is True

    assert user_updates[0][1]["publish_fetch_status"] is False
    assert status_updates[0][0][2] == "ok"
    assert status_updates[0][1]["last_success_at"] == "2026-01-02T03:04:05"
    assert status_updates[0][1]["last_attempt_at"] == "2026-01-02T03:00:00"
    assert status_updates[0][1]["persist"] is False


def test_fetch_status_can_be_republished_without_mutating_cache(monkeypatch):
    updater = SensorUpdater()
    published = []
    monkeypatch.setattr(
        updater,
        "save_partial_data",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache mutated")),
    )
    monkeypatch.setattr(updater, "_publish_sensor_state", lambda *args, **kwargs: published.append((args, kwargs)))

    updater.update_fetch_status(
        "test-user-0000",
        "_0000",
        "ok",
        latest_daily_date="2026-01-01",
        last_success_at="2026-01-02T03:04:05",
        last_attempt_at="2026-01-02T03:00:00",
        stage="complete",
        persist=False,
    )

    assert published[0][0][2] == "ok"
    assert published[0][1]["extra_attributes"]["last_success_at"] == "2026-01-02T03:04:05"

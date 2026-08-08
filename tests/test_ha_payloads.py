from scripts.support.ha_payloads import HaSensorPayload, HistoryPayloadBuilder


def test_ha_sensor_payload_converts_to_legacy_dict_shape():
    payload = HaSensorPayload(
        state=1.23,
        attributes={"latest_date": "2026-08-06"},
        log={"series_days": 1},
    )

    assert payload.to_dict() == {
        "state": 1.23,
        "attributes": {"latest_date": "2026-08-06"},
        "log": {"series_days": 1},
    }


def test_daily_history_payload_keeps_state_and_series_attributes():
    history = {
        "state": 12.18,
        "latest_date": "2026-08-06",
        "series_days": 2,
        "series": [
            {"date": "2026-08-05", "usage": 11.81, "charge": 4.87},
            {"date": "2026-08-06", "usage": 12.18, "charge": 5.03},
        ],
    }

    payload = HistoryPayloadBuilder.daily_history(history)

    assert payload == {
        "state": 12.18,
        "attributes": {
            "latest_date": "2026-08-06",
            "series_days": 2,
            "series": history["series"],
        },
        "log": {
            "latest_date": "2026-08-06",
            "series_days": 2,
        },
    }


def test_monthly_history_payload_keeps_latest_state_and_series_attributes():
    series = [
        {"month": "2026-07", "usage": 576.0, "charge": 298.04},
        {"month": "2026-08", "usage": 77.75, "charge": 33.1},
    ]

    payload = HistoryPayloadBuilder.monthly_history(series)

    assert payload == {
        "state": 77.75,
        "attributes": {
            "latest_month": "2026-08",
            "series_months": 2,
            "series": series,
        },
        "log": {
            "latest_month": "2026-08",
            "series_months": 2,
        },
    }

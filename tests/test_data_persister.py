from scripts.support.data_persister import DataPersister, FetchedUserData


class DummyPriceResolver:
    def calculate_daily_charge(self, *args, **kwargs):
        return None


def test_save_fetched_user_data_returns_existing_charge_when_db_disabled():
    persister = DataPersister(None, DummyPriceResolver())

    result = persister.save_fetched_user_data(
        "test_user",
        FetchedUserData(last_daily_date="2026-08-01", last_daily_charge=1.23),
    )

    assert result == 1.23


def test_legacy_save_user_data_delegates_to_structured_payload_when_db_disabled():
    persister = DataPersister(None, DummyPriceResolver())

    result = persister.save_user_data(
        "test_user",
        "2026-08-01",
        2.0,
        1.23,
        [],
        [],
        [],
        [],
        [],
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert result == 1.23

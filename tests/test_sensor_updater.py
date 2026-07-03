from scripts.sensor_updater import SensorUpdater


def test_public_sensor_name_removes_account_suffix():
    assert SensorUpdater._public_sensor_name("sensor.last_electricity_usage_0000") == "sensor.last_electricity_usage"
    assert SensorUpdater._public_sensor_name("sensor.last_electricity_usage") == "sensor.last_electricity_usage"

from scripts.support.ha_mqtt_publisher import HaDiscoveryPublisher, SensorPublishPlan, SensorStatePublisher


def test_sensor_publish_plan_builds_state_payload():
    plan = SensorPublishPlan(
        sensor_name="sensor.test_0000",
        user_id="test-user-0000",
        state=1.23,
        unit="kWh",
        icon="mdi:test",
        device_class="energy",
        state_class="total",
        extra_attributes={"period": "2026-08"},
    )

    assert plan.state_payload() == {"state": 1.23, "period": "2026-08"}


def test_sensor_state_publisher_publishes_discovery_once_then_states():
    published = []

    def mqtt_publish(topic, payload, retain=None):
        published.append((topic, payload, retain))
        return True

    discovery = HaDiscoveryPublisher(
        discovery_prefix="homeassistant",
        state_prefix="ha_95598",
        mqtt_publish=mqtt_publish,
        friendly_label=lambda sensor_name, user_id: "Test Sensor",
        device_payload=lambda user_id: {"identifiers": [f"ha_95598_{user_id}"]},
    )
    publisher = SensorStatePublisher(discovery=discovery, mqtt_publish=mqtt_publish)

    for state in (1.0, 2.0):
        publisher.publish(
            "sensor.test_usage_0000",
            "test-user-0000",
            state,
            unit="kWh",
            icon="mdi:test-tube",
            device_class="energy",
            state_class="total",
            extra_attributes={"period": "2026-08"},
        )

    assert published[0] == (
        "homeassistant/sensor/test_usage_0000/config",
        {
            "name": "Test Sensor",
            "unique_id": "sensor.test_usage_0000",
            "object_id": "test_usage_0000",
            "state_topic": "ha_95598/test_usage_0000/state",
            "json_attributes_topic": "ha_95598/test_usage_0000/state",
            "value_template": "{{ value_json.state }}",
            "device": {"identifiers": ["ha_95598_test-user-0000"]},
            "icon": "mdi:test-tube",
            "state_class": "total",
            "unit_of_measurement": "kWh",
            "device_class": "energy",
        },
        True,
    )
    assert published[1] == (
        "ha_95598/test_usage_0000/state",
        {"state": 1.0, "period": "2026-08"},
        None,
    )
    assert published[2] == (
        "ha_95598/test_usage_0000/state",
        {"state": 2.0, "period": "2026-08"},
        None,
    )
    assert len(published) == 3


def test_discovery_is_retried_when_publish_returns_false():
    published = []

    def mqtt_publish(topic, payload, retain=None):
        published.append(topic)
        return not topic.endswith("/config")

    discovery = HaDiscoveryPublisher(
        discovery_prefix="homeassistant",
        state_prefix="ha_95598",
        mqtt_publish=mqtt_publish,
        friendly_label=lambda sensor_name, user_id: "Test Sensor",
        device_payload=lambda user_id: {},
    )

    discovery.publish("sensor.test_0000", "test-user-0000", "", "", "mdi:test", "")
    discovery.publish("sensor.test_0000", "test-user-0000", "", "", "mdi:test", "")

    assert published == [
        "homeassistant/sensor/test_0000/config",
        "homeassistant/sensor/test_0000/config",
    ]

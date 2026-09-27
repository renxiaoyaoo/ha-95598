import json

from scripts.support.mqtt_publisher import MqttPublisher


class FakeMessage:
    rc = 0

    def wait_for_publish(self, timeout=None):
        self.timeout = timeout
        return None

    def is_published(self):
        return True


class TimedOutMessage(FakeMessage):
    def is_published(self):
        return False


class FakeClient:
    def __init__(self, message=None):
        self.published = []
        self.message = message or FakeMessage()

    def publish(self, topic, payload, qos, retain):
        self.published.append({"topic": topic, "payload": payload, "qos": qos, "retain": retain})
        return self.message

    def loop_stop(self):
        return None

    def disconnect(self):
        return None


def test_publish_serializes_dict_payload_without_real_connection():
    publisher = MqttPublisher(
        host="mqtt.example.test",
        port=1883,
        client_id="test-client",
        qos=1,
        retain=True,
    )
    client = FakeClient()
    publisher._client = client
    publisher._connected = True

    assert publisher.publish("test/topic", {"state": 1.23}) is True

    assert client.published == [
        {
            "topic": "test/topic",
            "payload": json.dumps({"state": 1.23}, ensure_ascii=False),
            "qos": 1,
            "retain": True,
        }
    ]
    assert client.message.timeout == 10.0


def test_publish_times_out_instead_of_blocking_forever():
    publisher = MqttPublisher(
        host="mqtt.example.test",
        port=1883,
        client_id="test-client",
        publish_timeout_seconds=0.5,
    )
    publisher._client = FakeClient(TimedOutMessage())
    publisher._connected = True

    import pytest

    with pytest.raises(TimeoutError, match="timed out"):
        publisher.publish("test/topic", "payload")

    assert publisher._connected is False


def test_publish_returns_false_when_mqtt_is_disabled():
    publisher = MqttPublisher(host="", port=1883, client_id="test-client")

    assert publisher.publish("test/topic", {"state": 1.23}) is False


def test_close_resets_client_state():
    publisher = MqttPublisher(host="mqtt.example.test", port=1883, client_id="test-client")
    publisher._client = FakeClient()
    publisher._connected = True

    publisher.close()

    assert publisher._client is None
    assert publisher._connected is False

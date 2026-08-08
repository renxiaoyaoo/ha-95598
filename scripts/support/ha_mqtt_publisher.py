from __future__ import annotations

from typing import Callable


class HaDiscoveryPublisher:
    def __init__(
        self,
        *,
        discovery_prefix: str,
        state_prefix: str,
        mqtt_publish: Callable[..., bool],
        friendly_label: Callable[[str, str], str],
        device_payload: Callable[[str], dict],
    ) -> None:
        self.discovery_prefix = discovery_prefix
        self.state_prefix = state_prefix
        self.mqtt_publish = mqtt_publish
        self.friendly_label = friendly_label
        self.device_payload = device_payload
        self.published_topics: set[str] = set()

    @staticmethod
    def sensor_object_id(sensor_name: str) -> str:
        if sensor_name.startswith("sensor."):
            sensor_name = sensor_name.removeprefix("sensor.")
        return sensor_name.replace(".", "_")

    def state_topic(self, sensor_name: str) -> str:
        return f"{self.state_prefix}/{self.sensor_object_id(sensor_name)}/state"

    def discovery_topic(self, sensor_name: str) -> str:
        return f"{self.discovery_prefix}/sensor/{self.sensor_object_id(sensor_name)}/config"

    def publish(self, sensor_name: str, user_id: str, device_class: str, unit: str, icon: str, state_class: str) -> None:
        topic = self.discovery_topic(sensor_name)
        if topic in self.published_topics:
            return

        payload = {
            "name": self.friendly_label(sensor_name, user_id),
            "unique_id": sensor_name,
            "object_id": self.sensor_object_id(sensor_name),
            "state_topic": self.state_topic(sensor_name),
            "json_attributes_topic": self.state_topic(sensor_name),
            "value_template": "{{ value_json.state }}",
            "device": self.device_payload(user_id),
            "icon": icon,
        }
        if state_class:
            payload["state_class"] = state_class
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        if self.mqtt_publish(topic, payload, retain=True):
            self.published_topics.add(topic)


class SensorStatePublisher:
    def __init__(self, *, discovery: HaDiscoveryPublisher, mqtt_publish: Callable[..., bool]) -> None:
        self.discovery = discovery
        self.mqtt_publish = mqtt_publish

    def publish(
        self,
        sensor_name: str,
        user_id: str,
        state,
        *,
        unit: str,
        icon: str,
        device_class: str,
        state_class: str,
        extra_attributes: dict | None = None,
    ) -> None:
        if state is None:
            return
        self.discovery.publish(sensor_name, user_id, device_class, unit, icon, state_class)
        payload = {"state": state}
        if extra_attributes:
            payload.update(extra_attributes)
        self.mqtt_publish(self.discovery.state_topic(sensor_name), payload)

from __future__ import annotations

import json
import logging
import time
from typing import Any

import paho.mqtt.client as mqtt


class MqttPublisher:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        client_id: str,
        qos: int = 1,
        retain: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id
        self.qos = qos
        self.retain = retain
        self._client = None
        self._connected = False

    def enabled(self) -> bool:
        return bool(self.host)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        self._connected = rc == 0
        if self._connected:
            logging.info("Connected to MQTT broker.")
        else:
            logging.warning("MQTT connection failed with rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self._connected = False
        if rc != 0:
            logging.warning("Disconnected from MQTT broker unexpectedly (rc=%s).", rc)

    def _wait_for_connection(self, timeout_seconds: float = 5.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._connected:
                return True
            time.sleep(0.1)
        return self._connected

    def _connect_client(self, client, reconnect: bool = False) -> bool:
        try:
            if reconnect:
                client.reconnect()
            else:
                client.connect(self.host, self.port, keepalive=60)
            return self._wait_for_connection()
        except Exception as exc:
            self._connected = False
            action = "reconnect to" if reconnect else "connect to"
            logging.warning("Failed to %s MQTT broker (%s).", action, type(exc).__name__)
            return False

    def _ensure_client(self):
        if not self.enabled():
            logging.info("MQTT_HOST is missing, skip MQTT publishing.")
            return None

        if self._client is None:
            client = mqtt.Client(client_id=self.client_id)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            if self.username:
                client.username_pw_set(self.username, self.password or None)
            client.loop_start()
            self._client = client
            if not self._connect_client(client):
                return None
        elif not self._connected:
            if not self._connect_client(self._client, reconnect=True):
                return None

        return self._client

    def publish(self, topic: str, payload: Any, retain: bool | None = None) -> bool:
        client = self._ensure_client()
        if client is None:
            return False
        if retain is None:
            retain = self.retain
        if not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False)
        message = client.publish(topic, payload=payload, qos=self.qos, retain=retain)
        message.wait_for_publish()
        if message.rc != mqtt.MQTT_ERR_SUCCESS:
            self._connected = False
            raise RuntimeError(f"Message publish failed: {mqtt.error_string(message.rc)}")
        return True

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        finally:
            self._client = None
            self._connected = False

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import paho.mqtt.client as mqtt
from scripts.support.cache_store import CacheStore
from scripts.support.credentials import mask_user_id
from scripts.support.db import SqliteDB
from scripts.support.notifier import build_notifier
from scripts.support.sensor_catalog import TOU_DAILY_SENSORS, TOU_PERIOD_SENSORS, tou_detail_enabled
from scripts.const import (
    BALANCE_SENSOR_NAME,
    BALANCE_UNIT,
    DAILY_CHARGE_SENSOR_NAME,
    DAILY_HISTORY_SENSOR_NAME,
    DAILY_HISTORY_PUBLISH_DAYS,
    DAILY_USAGE_SENSOR_NAME,
    FETCH_STATUS_SENSOR_NAME,
    FLAT_USAGE_SENSOR_NAME,
    MONTH_CHARGE_SENSOR_NAME,
    MONTHLY_HISTORY_SENSOR_NAME,
    MONTHLY_HISTORY_PUBLISH_MONTHS,
    MONTH_FLAT_USAGE_SENSOR_NAME,
    MONTH_PEAK_USAGE_SENSOR_NAME,
    MONTH_TIP_USAGE_SENSOR_NAME,
    MONTH_USAGE_SENSOR_NAME,
    MONTH_VALLEY_USAGE_SENSOR_NAME,
    PEAK_USAGE_SENSOR_NAME,
    TIP_USAGE_SENSOR_NAME,
    TOTAL_CHARGE_SENSOR_NAME,
    TOTAL_USAGE_SENSOR_NAME,
    USAGE_UNIT,
    VALLEY_USAGE_SENSOR_NAME,
    YEARLY_CHARGE_SENSOR_NAME,
    YEARLY_FLAT_USAGE_SENSOR_NAME,
    YEARLY_PEAK_USAGE_SENSOR_NAME,
    YEARLY_TIP_USAGE_SENSOR_NAME,
    YEARLY_USAGE_SENSOR_NAME,
    YEARLY_VALLEY_USAGE_SENSOR_NAME,
    SENSOR_FRIENDLY_LABELS,
)


ROOT_DIR = Path(__file__).resolve().parent.parent


class SensorUpdater:
    FETCH_STAGES = ("none", "balance", "yearly", "monthly", "daily", "tou", "persist", "billing", "complete")

    def __init__(self):
        self.mqtt_host = os.getenv("MQTT_HOST", "").strip()
        self.mqtt_port = int(os.getenv("MQTT_PORT", 1883))
        self.mqtt_username = os.getenv("MQTT_USERNAME", "").strip()
        self.mqtt_password = os.getenv("MQTT_PASSWORD", "").strip()
        self.mqtt_client_id = os.getenv("MQTT_CLIENT_ID", f"ha-95598-{os.getpid()}")
        self.discovery_prefix = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant").strip("/") or "homeassistant"
        self.state_prefix = os.getenv("MQTT_STATE_PREFIX", "ha_95598").strip("/") or "ha_95598"
        self.mqtt_qos = int(os.getenv("MQTT_QOS", 1))
        self.mqtt_retain = os.getenv("MQTT_RETAIN", "true").lower() == "true"
        self.publish_tou_detail_sensors = tou_detail_enabled()
        self._mqtt_client = None
        self._mqtt_connected = False
        self._published_discovery_topics: set[str] = set()
        self.notifier = build_notifier()
        self.cache_store = CacheStore(ROOT_DIR / "data" / "ha_95598_cache.json")
        self.db = SqliteDB()

    def _device_payload(self, user_id: str):
        return {
            "identifiers": [f"ha_95598_{user_id}"],
            "name": f"95598-{user_id[-4:]}",
            "manufacturer": "ha-95598",
            "model": "ha-95598",
        }

    @staticmethod
    def _sensor_friendly_label(sensor_name: str, user_id: str):
        postfix = f"_{user_id[-4:]}"
        sensor_name_base = sensor_name.removeprefix("sensor.").removesuffix(postfix)
        return SENSOR_FRIENDLY_LABELS.get(
            f"sensor.{sensor_name_base}",
            sensor_name_base.replace("_", " "),
        )

    @staticmethod
    def _public_sensor_name(sensor_name: str) -> str:
        return re.sub(r"_\d{4}$", "", sensor_name)

    def _log_sensor_update(self, sensor_name: str, state, unit: str = "", **attributes) -> None:
        details = ", ".join(f"{key}={value}" for key, value in attributes.items() if value is not None)
        if details:
            logging.info(
                "Homeassistant sensor %s state updated: %s%s (%s)",
                self._public_sensor_name(sensor_name),
                state,
                f" {unit}" if unit else "",
                details,
            )
            return

        logging.info(
            "Homeassistant sensor %s state updated: %s%s",
            self._public_sensor_name(sensor_name),
            state,
            f" {unit}" if unit else "",
        )

    def _mqtt_enabled(self) -> bool:
        return bool(self.mqtt_host)

    def _on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        self._mqtt_connected = rc == 0
        if self._mqtt_connected:
            logging.info("Connected to MQTT broker %s:%s", self.mqtt_host, self.mqtt_port)
        else:
            logging.warning("MQTT connection failed with rc=%s", rc)

    def _on_mqtt_disconnect(self, client, userdata, rc, properties=None):
        self._mqtt_connected = False
        if rc != 0:
            logging.warning("Disconnected from MQTT broker unexpectedly (rc=%s).", rc)

    def _wait_for_mqtt_connection(self, timeout_seconds: float = 5.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._mqtt_connected:
                return True
            time.sleep(0.1)
        return self._mqtt_connected

    def _connect_mqtt_client(self, client, reconnect: bool = False) -> bool:
        try:
            if reconnect:
                client.reconnect()
            else:
                client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            return self._wait_for_mqtt_connection()
        except Exception as exc:
            self._mqtt_connected = False
            logging.warning("Failed to %s MQTT broker %s:%s: %s", "reconnect to" if reconnect else "connect to", self.mqtt_host, self.mqtt_port, exc)
            return False

    def _ensure_mqtt_client(self):
        if not self._mqtt_enabled():
            logging.info("MQTT_HOST is missing, skip MQTT publishing.")
            return None

        if self._mqtt_client is None:
            client = mqtt.Client(client_id=self.mqtt_client_id)
            client.on_connect = self._on_mqtt_connect
            client.on_disconnect = self._on_mqtt_disconnect
            if self.mqtt_username:
                client.username_pw_set(self.mqtt_username, self.mqtt_password or None)
            client.loop_start()
            self._mqtt_client = client
            if not self._connect_mqtt_client(client):
                return None
        elif not self._mqtt_connected:
            if not self._connect_mqtt_client(self._mqtt_client, reconnect=True):
                return None

        return self._mqtt_client

    def _publish_mqtt(self, topic: str, payload, retain: bool = None):
        client = self._ensure_mqtt_client()
        if client is None:
            return False
        if retain is None:
            retain = self.mqtt_retain
        if not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False)
        message = client.publish(topic, payload=payload, qos=self.mqtt_qos, retain=retain)
        message.wait_for_publish()
        if message.rc != mqtt.MQTT_ERR_SUCCESS:
            self._mqtt_connected = False
            raise RuntimeError(f"Message publish failed: {mqtt.error_string(message.rc)}")
        return True

    def close(self):
        if self._mqtt_client is None:
            return
        try:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
        finally:
            self._mqtt_client = None
            self._mqtt_connected = False

    def _sensor_object_id(self, sensor_name: str) -> str:
        if sensor_name.startswith("sensor."):
            sensor_name = sensor_name.removeprefix("sensor.")
        return sensor_name.replace(".", "_")

    def _state_topic(self, sensor_name: str) -> str:
        return f"{self.state_prefix}/{self._sensor_object_id(sensor_name)}/state"

    def _discovery_topic(self, sensor_name: str) -> str:
        return f"{self.discovery_prefix}/sensor/{self._sensor_object_id(sensor_name)}/config"

    def _publish_discovery(self, sensor_name: str, user_id: str, device_class: str, unit: str, icon: str, state_class: str):
        topic = self._discovery_topic(sensor_name)
        if topic in self._published_discovery_topics:
            return

        friendly_name = self._sensor_friendly_label(sensor_name, user_id)
        payload = {
            "name": friendly_name,
            "unique_id": sensor_name,
            "object_id": self._sensor_object_id(sensor_name),
            "state_topic": self._state_topic(sensor_name),
            "json_attributes_topic": self._state_topic(sensor_name),
            "value_template": "{{ value_json.state }}",
            "device": self._device_payload(user_id),
            "icon": icon,
        }
        if state_class:
            payload["state_class"] = state_class
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        if self._publish_mqtt(topic, payload, retain=True):
            self._published_discovery_topics.add(topic)

    def _publish_sensor_state(
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
    ):
        if state is None:
            return
        self._publish_discovery(sensor_name, user_id, device_class, unit, icon, state_class)
        payload = {"state": state}
        if extra_attributes:
            payload.update(extra_attributes)
        self._publish_mqtt(self._state_topic(sensor_name), payload)


    def update_one_userid(
        self,
        user_id: str,
        balance: float,
        last_daily_date: str,
        last_daily_usage: float,
        yearly_charge: float,
        yearly_usage: float,
        month_charge: float,
        month_usage: float,
        last_daily_charge: float = None,
        valley_usage: float = None,
        flat_usage: float = None,
        peak_usage: float = None,
        tip_usage: float = None,
        notify_stale: bool = True,
        log_success: bool = True,
    ):
        self._save_to_cache(
            user_id,
            balance,
            last_daily_date,
            last_daily_usage,
            last_daily_charge,
            yearly_charge,
            yearly_usage,
            month_charge,
            month_usage,
            valley_usage,
            flat_usage,
            peak_usage,
            tip_usage,
        )
        if notify_stale:
            self._check_and_notify_stale_data(user_id, self.cache_store.load().get(user_id, {}))
        postfix = f"_{user_id[-4:]}"
        if balance is not None:
            self.update_balance(user_id, postfix, balance)
        if last_daily_usage is not None:
            self.update_last_daily_usage(user_id, postfix, last_daily_date, last_daily_usage)
        if last_daily_charge is not None:
            self.update_last_daily_charge(user_id, postfix, last_daily_date, last_daily_charge)
        self.update_total_data(user_id, postfix, usage=True)
        self.update_total_data(user_id, postfix, usage=False)
        self.update_daily_history_data(user_id, postfix)
        self.update_monthly_history_data(user_id, postfix)
        if yearly_usage is not None:
            self.update_yearly_data(user_id, postfix, yearly_usage, usage=True)
        if yearly_charge is not None:
            self.update_yearly_data(user_id, postfix, yearly_charge)
        if month_usage is not None:
            self.update_month_data(user_id, postfix, month_usage, usage=True)
        if month_charge is not None:
            self.update_month_data(user_id, postfix, month_charge)
        if self.publish_tou_detail_sensors:
            self.update_tou_data(user_id, postfix, last_daily_date, valley_usage, flat_usage, peak_usage, tip_usage)
            self.update_period_tou_data(user_id, postfix)
        self.update_fetch_status(
            user_id,
            postfix,
            "ok",
            latest_daily_date=last_daily_date,
            last_success_at=datetime.now().isoformat(timespec="seconds"),
            stage="complete",
        )

        if log_success:
            logging.info("User %s state-refresh task run successfully!", mask_user_id(user_id))

    def _get_cache_file(self):
        return str(self.cache_store.cache_file)

    def _get_db_file(self):
        db_name = os.getenv("DB_NAME", "homeassistant.db")
        return str(ROOT_DIR / "data" / Path(db_name).name)

    def update_progress(self, user_id: str, **progress_fields):
        self.cache_store.update_progress(user_id, **progress_fields)

    def update_progress_stage(self, user_id: str, stage: str, fetch_date: str = None):
        self.cache_store.update_progress_stage(user_id, stage, fetch_date=fetch_date)

    def get_progress(self, user_id: str):
        return self.cache_store.get_progress(user_id)

    def save_partial_data(self, user_id: str, **fields):
        self.cache_store.save_partial_data(user_id, **fields)

    def get_cached_user_data(self, user_id: str):
        return self.cache_store.get_cached_user_data(user_id)

    def _ensure_db(self, user_id: str):
        if self.db is None:
            return None
        if self.db.connect is None or self.db.user_id != str(user_id).strip():
            if not self.db.connect_user_db(user_id):
                return None
        return self.db

    def is_progress_complete(self, progress: dict) -> bool:
        return self.cache_store.is_progress_complete(progress)

    def should_skip_startup_fetch(self) -> bool:
        return self.cache_store.should_skip_startup_fetch()

    def _save_to_cache(
        self,
        user_id,
        balance,
        last_daily_date,
        last_daily_usage,
        last_daily_charge,
        yearly_charge,
        yearly_usage,
        month_charge,
        month_usage,
        valley_usage,
        flat_usage,
        peak_usage,
        tip_usage,
    ):
        data = self.cache_store.load()
        entry = data.get(user_id) if isinstance(data.get(user_id), dict) else {}
        if not entry:
            entry = {"data": {}, "progress": {"stage": "none"}}
            data[user_id] = entry
        entry["data"] = {
            "balance": balance,
            "last_daily_date": last_daily_date,
            "last_daily_usage": last_daily_usage,
            "last_daily_charge": last_daily_charge,
            "yearly_charge": yearly_charge,
            "yearly_usage": yearly_usage,
            "month_charge": month_charge,
            "month_usage": month_usage,
            "valley_usage": valley_usage,
            "flat_usage": flat_usage,
            "peak_usage": peak_usage,
            "tip_usage": tip_usage,
            "timestamp": datetime.now().isoformat()
        }
        self.cache_store.save(data)

    def republish(self):
        cache_file = self._get_cache_file()
        abs_cache_file = os.path.abspath(cache_file)
        if not os.path.exists(cache_file):
            logging.info(f"No cache file found at {abs_cache_file}, skipping republish.")
            return False

        try:
            data = self.cache_store.load()
            logging.info("Loaded cache file %s with %s user entries.", cache_file, len(data))
        except Exception as e:
            logging.error(f"Failed to load cache file {abs_cache_file}: {e}")
            return False

        try:
            for user_id, values in data.items():
                logging.info("Republishing cached data for user %s", mask_user_id(user_id))
                if not isinstance(values, dict):
                    logging.warning("Skip invalid cache entry for user %s: %r", mask_user_id(user_id), values)
                    continue
                user_data = values.get("data", {})
                allowed_keys = {
                    "balance",
                    "last_daily_date",
                    "last_daily_usage",
                    "last_daily_charge",
                    "yearly_charge",
                    "yearly_usage",
                    "month_charge",
                    "month_usage",
                    "valley_usage",
                    "flat_usage",
                    "peak_usage",
                    "tip_usage",
                }
                clean_values = {k: v for k, v in user_data.items() if k in allowed_keys}
                if not clean_values:
                    continue
                self.update_one_userid(user_id, notify_stale=False, log_success=False, **clean_values)
                logging.info("Cached data republished for user %s.", mask_user_id(user_id))
            return True
        except Exception as e:
            logging.error(f"Failed to republish data: {e}")
            return False

    def _check_and_notify_stale_data(self, user_id: str, entry: dict):
        stale_days_threshold = int(os.getenv("STALE_DATA_ALERT_DAYS", 2))
        user_data = entry.get("data", {}) if isinstance(entry, dict) else {}
        progress = entry.get("progress", {}) if isinstance(entry, dict) else {}
        latest_date = user_data.get("last_daily_date")
        if not latest_date:
            return

        try:
            latest_dt = datetime.strptime(latest_date, "%Y-%m-%d").date()
        except Exception:
            logging.warning("Failed to parse last_daily_date for stale data alert: %s", latest_date)
            return

        stale_days = (datetime.now().date() - latest_dt).days
        alert_key = f"{latest_date}:{stale_days}"
        sent_key = progress.get("stale_alert_sent_key")

        if stale_days > stale_days_threshold:
            if sent_key == alert_key:
                return
            if self.notifier.send_stale_data_alert(user_id, latest_date, stale_days):
                self.update_progress(user_id, stale_alert_sent_key=alert_key)
        elif sent_key:
            self.update_progress(user_id, stale_alert_sent_key=None)

    def update_last_daily_usage(self, user_id: str, postfix: str, last_daily_date: str, sensorState: float):
        sensorName = DAILY_USAGE_SENSOR_NAME + postfix

        try:
            dt = datetime.strptime(last_daily_date, "%Y-%m-%d").date()
            today = datetime.now().date()
            diff = (today - dt).days
            if diff == 0:
                last_daily_date_fmt = "今天"
            elif diff == 1:
                last_daily_date_fmt = "昨天"
            elif diff == 2:
                last_daily_date_fmt = "前天"
            else:
                last_daily_date_fmt = dt.strftime("%m/%d")
        except Exception:
            last_daily_date_fmt = last_daily_date

        extra_attributes = {
            "last_reset": datetime.strptime(last_daily_date, "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00+00:00"),
            "last_daily_date_fmt": last_daily_date_fmt,
        }

        self._publish_sensor_state(
            sensorName,
            user_id,
            sensorState,
            unit="kWh",
            icon="mdi:lightning-bolt",
            device_class="energy",
            state_class="",
            extra_attributes=extra_attributes,
        )
        self._log_sensor_update(sensorName, sensorState, "kWh", last_daily_date=last_daily_date)

    def update_last_daily_charge(self, user_id: str, postfix: str, last_daily_date: str, sensorState: float):
        sensorName = DAILY_CHARGE_SENSOR_NAME + postfix
        extra_attributes = {
            "last_reset": datetime.strptime(last_daily_date, "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00+00:00"),
        }
        self._publish_sensor_state(
            sensorName,
            user_id,
            sensorState,
            unit="CNY",
            icon="mdi:cash",
            device_class="monetary",
            state_class="",
            extra_attributes=extra_attributes,
        )
        self._log_sensor_update(sensorName, sensorState, "CNY", last_daily_date=last_daily_date)

    def update_tou_data(
        self,
        user_id: str,
        postfix: str,
        last_daily_date: str,
        valley_usage: float,
        flat_usage: float,
        peak_usage: float,
        tip_usage: float,
    ):
        if last_daily_date is None:
            return

        tou_values = {
            "valley_usage": valley_usage,
            "flat_usage": flat_usage,
            "peak_usage": peak_usage,
            "tip_usage": tip_usage,
        }
        for key, value in tou_values.items():
            if value is None:
                continue
            spec = TOU_DAILY_SENSORS[key]
            self._update_daily_segment_usage(user_id, spec.sensor_name + postfix, spec.icon, last_daily_date, value)

    def _update_daily_segment_usage(self, user_id: str, sensorName: str, icon: str, last_daily_date: str, sensorState: float):
        self._publish_sensor_state(
            sensorName,
            user_id,
            sensorState,
            unit="kWh",
            icon=icon,
            device_class="energy",
            state_class="",
            extra_attributes={
                "last_reset": datetime.strptime(last_daily_date, "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00+00:00"),
            },
        )
        self._log_sensor_update(sensorName, sensorState, "kWh")

    def _get_current_month_daily_summary(self, user_id: str):
        db = self._ensure_db(user_id)
        if db is None:
            return None
        return db.get_current_month_daily_summary()

    def _get_current_year_daily_summary(self, user_id: str):
        db = self._ensure_db(user_id)
        if db is None:
            return None
        return db.get_current_year_daily_summary()

    def _get_latest_daily_month_summary(self, user_id: str):
        db = self._ensure_db(user_id)
        if db is None:
            return None
        return db.get_latest_daily_month_summary()

    def _get_total_monthly_summary(self, user_id: str):
        db = self._ensure_db(user_id)
        if db is None:
            return None
        return db.get_total_monthly_summary()

    def _get_recent_daily_history(self, user_id: str, days: int = DAILY_HISTORY_PUBLISH_DAYS):
        db = self._ensure_db(user_id)
        if db is None:
            return None
        return db.get_recent_daily_history(days=days)

    def _get_recent_monthly_history(self, user_id: str, months: int = MONTHLY_HISTORY_PUBLISH_MONTHS):
        db = self._ensure_db(user_id)
        if db is None:
            return []
        return db.get_recent_monthly_history(months=months)

    def _update_period_segment_usage(self, user_id: str, sensor_name: str, icon: str, period_value: str, sensor_state: float):
        self._publish_sensor_state(
            sensor_name,
            user_id,
            sensor_state,
            unit="kWh",
            icon=icon,
            device_class="energy",
            state_class="total",
            extra_attributes={"period": period_value},
        )
        self._log_sensor_update(sensor_name, sensor_state, "kWh", period=period_value)

    def update_period_tou_data(self, user_id: str, postfix: str):
        current_month_summary = (
            self._get_current_month_daily_summary(user_id)
            or self._get_latest_daily_month_summary(user_id)
        )
        if current_month_summary is not None:
            values = {
                "valley_usage": current_month_summary["valley_usage"],
                "flat_usage": current_month_summary["flat_usage"],
                "peak_usage": current_month_summary["peak_usage"],
                "tip_usage": current_month_summary["tip_usage"],
            }
            for key, value in values.items():
                if value is None:
                    continue
                spec = TOU_PERIOD_SENSORS["month"][key]
                self._update_period_segment_usage(user_id, spec.sensor_name + postfix, spec.icon, current_month_summary["period"], value)

        current_year_summary = self._get_current_year_daily_summary(user_id)
        if current_year_summary is not None:
            values = {
                "valley_usage": current_year_summary["valley_usage"],
                "flat_usage": current_year_summary["flat_usage"],
                "peak_usage": current_year_summary["peak_usage"],
                "tip_usage": current_year_summary["tip_usage"],
            }
            for key, value in values.items():
                if value is None:
                    continue
                spec = TOU_PERIOD_SENSORS["year"][key]
                self._update_period_segment_usage(user_id, spec.sensor_name + postfix, spec.icon, current_year_summary["period"], value)

    def update_balance(self, user_id: str, postfix: str, sensorState: float):
        sensorName = BALANCE_SENSOR_NAME + postfix

        last_reset = datetime.now().strftime("%Y-%m-%d, %H:%M:%S")
        self._publish_sensor_state(
            sensorName,
            user_id,
            sensorState,
            unit="CNY",
            icon="mdi:cash-100",
            device_class="monetary",
            state_class="total",
            extra_attributes={"last_reset": last_reset},
        )
        self._log_sensor_update(sensorName, sensorState, "CNY")

    def update_month_data(self, user_id: str, postfix: str, sensorState: float, usage=False):
        sensorName = (
            MONTH_USAGE_SENSOR_NAME + postfix
            if usage
            else MONTH_CHARGE_SENSOR_NAME + postfix
        )
        current_month_summary = (
            self._get_current_month_daily_summary(user_id)
            or self._get_latest_daily_month_summary(user_id)
        )
        if current_month_summary is not None:
            sensorState = current_month_summary["usage" if usage else "charge"]
            period = current_month_summary["period"]
        else:
            period = datetime.now().strftime("%Y-%m")
        self._publish_sensor_state(
            sensorName,
            user_id,
            sensorState,
            unit="kWh" if usage else "CNY",
            icon="mdi:lightning-bolt" if usage else "mdi:cash",
            device_class="energy" if usage else "monetary",
            state_class="total",
            extra_attributes={"period": period},
        )
        if current_month_summary is not None:
            self.save_partial_data(
                user_id,
                **({"month_usage": sensorState} if usage else {"month_charge": sensorState}),
            )
        self._log_sensor_update(sensorName, sensorState, "kWh" if usage else "CNY", period=period)

    def update_yearly_data(self, user_id: str, postfix: str, sensorState: float, usage=False):
        sensorName = (
            YEARLY_USAGE_SENSOR_NAME + postfix
            if usage
            else YEARLY_CHARGE_SENSOR_NAME + postfix
        )
        if datetime.now().month == 1:
            last_year = datetime.now().year -1
            last_reset = datetime.now().replace(year=last_year).strftime("%Y")
        else:
            last_reset = datetime.now().strftime("%Y")
        self._publish_sensor_state(
            sensorName,
            user_id,
            sensorState,
            unit="kWh" if usage else "CNY",
            icon="mdi:lightning-bolt" if usage else "mdi:cash",
            device_class="energy" if usage else "monetary",
            state_class="total",
            extra_attributes={"last_reset": last_reset},
        )
        self._log_sensor_update(sensorName, sensorState, "kWh" if usage else "CNY")

    def update_total_data(self, user_id: str, postfix: str, usage=False):
        summary = self._get_total_monthly_summary(user_id)
        if summary is None:
            return

        sensor_name = (
            TOTAL_USAGE_SENSOR_NAME + postfix
            if usage
            else TOTAL_CHARGE_SENSOR_NAME + postfix
        )
        sensor_state = summary["usage" if usage else "charge"]
        self._publish_sensor_state(
            sensor_name,
            user_id,
            sensor_state,
            unit="kWh" if usage else "CNY",
            icon="mdi:home-lightning-bolt-outline" if usage else "mdi:cash-multiple",
            device_class="energy" if usage else "monetary",
            state_class="total",
        )
        self._log_sensor_update(sensor_name, sensor_state, "kWh" if usage else "CNY")

    def update_daily_history_data(self, user_id: str, postfix: str):
        history = self._get_recent_daily_history(user_id)
        if history is None:
            return

        sensor_name = DAILY_HISTORY_SENSOR_NAME + postfix
        self._publish_sensor_state(
            sensor_name,
            user_id,
            history["state"],
            unit="kWh",
            icon="mdi:chart-timeline-variant",
            device_class="energy",
            state_class="",
            extra_attributes={
                "latest_date": history["latest_date"],
                "series_days": history["series_days"],
                "series": history["series"],
            },
        )
        self._log_sensor_update(
            sensor_name,
            history["state"],
            "kWh",
            latest_date=history["latest_date"],
            series_days=history["series_days"],
        )

    def update_monthly_history_data(self, user_id: str, postfix: str):
        series = self._get_recent_monthly_history(user_id)
        if not series:
            return

        latest = series[-1]
        sensor_name = MONTHLY_HISTORY_SENSOR_NAME + postfix
        self._publish_sensor_state(
            sensor_name,
            user_id,
            latest["usage"],
            unit="kWh",
            icon="mdi:chart-bar",
            device_class="",
            state_class="measurement",
            extra_attributes={
                "latest_month": latest["month"],
                "series_months": len(series),
                "series": series,
            },
        )
        self._log_sensor_update(
            sensor_name,
            latest["usage"],
            "kWh",
            latest_month=latest["month"],
            series_months=len(series),
        )

    def update_fetch_status(
        self,
        user_id: str,
        postfix: str,
        status: str,
        *,
        latest_daily_date: str | None = None,
        last_success_at: str | None = None,
        last_attempt_at: str | None = None,
        stage: str | None = None,
        error_type: str | None = None,
    ):
        sensor_name = FETCH_STATUS_SENSOR_NAME + postfix
        now = datetime.now()
        source_delay_days = None
        if latest_daily_date:
            try:
                source_delay_days = (now.date() - datetime.strptime(latest_daily_date, "%Y-%m-%d").date()).days
            except Exception:
                source_delay_days = None

        last_attempt_at = last_attempt_at or now.isoformat(timespec="seconds")
        attributes = {
            "latest_daily_date": latest_daily_date,
            "source_delay_days": source_delay_days,
            "last_success_at": last_success_at,
            "last_attempt_at": last_attempt_at,
            "stage": stage,
            "error_type": error_type,
        }
        self.save_partial_data(
            user_id,
            fetch_status=status,
            source_delay_days=source_delay_days,
            last_fetch_success_at=last_success_at,
            last_fetch_attempt_at=last_attempt_at,
            last_fetch_error_type=error_type,
        )
        self._publish_sensor_state(
            sensor_name,
            user_id,
            status,
            unit="",
            icon="mdi:sync",
            device_class="",
            state_class="",
            extra_attributes=attributes,
        )
        self._log_sensor_update(
            sensor_name,
            status,
            latest_daily_date=latest_daily_date,
            source_delay_days=source_delay_days,
            stage=stage,
            error_type=error_type,
        )

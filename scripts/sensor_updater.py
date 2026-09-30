import logging
import os
import re
from datetime import datetime
from pathlib import Path

from scripts.support.cache_store import CacheStore
from scripts.support.credentials import mask_user_id
from scripts.support.db import SqliteDB
from scripts.support.fetch_progress import FETCH_STAGES as ALL_FETCH_STAGES
from scripts.support.ha_mqtt_publisher import HaDiscoveryPublisher, SensorStatePublisher
from scripts.support.ha_payloads import HistoryPayloadBuilder
from scripts.support.history_gap_alert import HistoryGapAlertChecker
from scripts.support.mqtt_publisher import MqttPublisher
from scripts.support.notifier import build_notifier
from scripts.support.sensor_catalog import TOU_DAILY_SENSORS, TOU_PERIOD_SENSORS, tou_detail_enabled
from scripts.support.stale_alert import StaleDataAlertChecker
from scripts.support.user_state import UserStateSnapshot
from scripts.support.user_state_cache import UserStateCache
from scripts.const import (
    BALANCE_SENSOR_NAME,
    DAILY_CHARGE_SENSOR_NAME,
    DAILY_HISTORY_SENSOR_NAME,
    DAILY_HISTORY_PUBLISH_DAYS,
    DAILY_USAGE_SENSOR_NAME,
    FETCH_STATUS_SENSOR_NAME,
    MONTH_CHARGE_SENSOR_NAME,
    MONTHLY_HISTORY_SENSOR_NAME,
    MONTHLY_HISTORY_PUBLISH_MONTHS,
    MONTH_USAGE_SENSOR_NAME,
    TOTAL_CHARGE_SENSOR_NAME,
    TOTAL_USAGE_SENSOR_NAME,
    YEARLY_CHARGE_SENSOR_NAME,
    YEARLY_USAGE_SENSOR_NAME,
    SENSOR_FRIENDLY_LABELS,
)


ROOT_DIR = Path(__file__).resolve().parent.parent


class SensorUpdater:
    FETCH_STAGES = ALL_FETCH_STAGES

    def __init__(self):
        self.mqtt_host = os.getenv("MQTT_HOST", "").strip()
        self.mqtt_port = int(os.getenv("MQTT_PORT", 1883))
        self.mqtt_username = os.getenv("MQTT_USERNAME", "").strip()
        self.mqtt_password = os.getenv("MQTT_PASSWORD", "").strip()
        self.mqtt_client_id = os.getenv("MQTT_CLIENT_ID", f"ha-95598-{os.getpid()}")
        self.discovery_prefix = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant").strip("/") or "homeassistant"
        self.state_prefix = os.getenv("MQTT_STATE_PREFIX", "ha_95598").strip("/") or "ha_95598"
        self.publish_tou_detail_sensors = tou_detail_enabled()
        self.mqtt_publisher = MqttPublisher(
            host=self.mqtt_host,
            port=self.mqtt_port,
            username=self.mqtt_username,
            password=self.mqtt_password,
            client_id=self.mqtt_client_id,
            qos=int(os.getenv("MQTT_QOS", 1)),
            retain=os.getenv("MQTT_RETAIN", "true").lower() == "true",
            publish_timeout_seconds=float(os.getenv("MQTT_PUBLISH_TIMEOUT_SECONDS", "10")),
        )
        self.notifier = build_notifier()
        self.cache_store = CacheStore(ROOT_DIR / "data" / "ha_95598_cache.json")
        self.user_state_cache = UserStateCache(self.cache_store)
        self.db = SqliteDB()
        self.stale_alert_checker = StaleDataAlertChecker(self.notifier, self.update_progress)
        self.history_gap_alert_checker = HistoryGapAlertChecker(self.notifier, self.update_progress, self.db)
        self.discovery_publisher = HaDiscoveryPublisher(
            discovery_prefix=self.discovery_prefix,
            state_prefix=self.state_prefix,
            mqtt_publish=lambda topic, payload, retain=None: self._publish_mqtt(topic, payload, retain=retain),
            friendly_label=self._sensor_friendly_label,
            device_payload=self._device_payload,
        )
        self.sensor_state_publisher = SensorStatePublisher(
            discovery=self.discovery_publisher,
            mqtt_publish=lambda topic, payload, retain=None: self._publish_mqtt(topic, payload, retain=retain),
        )

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
        if self._public_sensor_name(sensor_name) == FETCH_STATUS_SENSOR_NAME:
            safe_attributes = {
                key: value
                for key, value in attributes.items()
                if key in {"latest_daily_date", "source_delay_days", "stage", "error_type"} and value is not None
            }
            details = ", ".join(f"{key}={value}" for key, value in safe_attributes.items())
            logging.info(
                "Homeassistant sensor %s state updated: %s%s",
                self._public_sensor_name(sensor_name),
                state,
                f" ({details})" if details else "",
            )
            return
        logging.info("Homeassistant sensor %s state updated.", self._public_sensor_name(sensor_name))

    def _mqtt_enabled(self) -> bool:
        return self.mqtt_publisher.enabled()

    def _publish_mqtt(self, topic: str, payload, retain: bool = None):
        return self.mqtt_publisher.publish(topic, payload, retain=retain)

    def close(self):
        self.mqtt_publisher.close()

    def _sensor_object_id(self, sensor_name: str) -> str:
        return self.discovery_publisher.sensor_object_id(sensor_name)

    def _state_topic(self, sensor_name: str) -> str:
        return self.discovery_publisher.state_topic(sensor_name)

    def _discovery_topic(self, sensor_name: str) -> str:
        return self.discovery_publisher.discovery_topic(sensor_name)

    def _publish_discovery(self, sensor_name: str, user_id: str, device_class: str, unit: str, icon: str, state_class: str):
        self.discovery_publisher.publish(sensor_name, user_id, device_class, unit, icon, state_class)

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
        self.sensor_state_publisher.publish(
            sensor_name,
            user_id,
            state,
            unit=unit,
            icon=icon,
            device_class=device_class,
            state_class=state_class,
            extra_attributes=extra_attributes,
        )


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
        publish_fetch_status: bool = True,
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
            entry = self.cache_store.load().get(user_id, {})
            self._check_and_notify_stale_data(user_id, entry)
            self._check_and_notify_history_gaps(user_id, entry)
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
        if publish_fetch_status:
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
        self.user_state_cache.save_snapshot(
            user_id,
            UserStateSnapshot(
                balance=balance,
                last_daily_date=last_daily_date,
                last_daily_usage=last_daily_usage,
                last_daily_charge=last_daily_charge,
                yearly_charge=yearly_charge,
                yearly_usage=yearly_usage,
                month_charge=month_charge,
                month_usage=month_usage,
                valley_usage=valley_usage,
                flat_usage=flat_usage,
                peak_usage=peak_usage,
                tip_usage=tip_usage,
            ),
        )

    def republish(self):
        try:
            republished = False
            cache_entries = self.cache_store.load()
            for user_id, snapshot in self.user_state_cache.iter_snapshots():
                clean_values = snapshot.to_update_kwargs()
                self.update_one_userid(
                    user_id,
                    notify_stale=False,
                    log_success=False,
                    publish_fetch_status=False,
                    **clean_values,
                )
                entry = cache_entries.get(user_id, {})
                user_data = entry.get("data", {}) if isinstance(entry, dict) else {}
                progress = entry.get("progress", {}) if isinstance(entry, dict) else {}
                cached_status = user_data.get("fetch_status")
                if cached_status:
                    self.update_fetch_status(
                        user_id,
                        f"_{user_id[-4:]}",
                        cached_status,
                        latest_daily_date=user_data.get("last_daily_date"),
                        last_success_at=user_data.get("last_fetch_success_at"),
                        last_attempt_at=user_data.get("last_fetch_attempt_at"),
                        stage=progress.get("stage"),
                        error_type=user_data.get("last_fetch_error_type"),
                        persist=False,
                    )
                logging.info("Cached data republished for user %s.", mask_user_id(user_id))
                republished = True
            return republished
        except Exception as e:
            logging.error("Failed to republish data (%s).", type(e).__name__)
            return False

    def _check_and_notify_stale_data(self, user_id: str, entry: dict):
        self.stale_alert_checker.check(user_id, entry)

    def _check_and_notify_history_gaps(self, user_id: str, entry: dict):
        self.history_gap_alert_checker.check(user_id, entry)

    def check_cached_stale_data(self, ignored_user_ids: list[str] | None = None) -> None:
        ignored = set(ignored_user_ids or [])
        for user_id, entry in self.cache_store.load().items():
            if user_id not in ignored and isinstance(entry, dict):
                self._check_and_notify_stale_data(user_id, entry)

    def mark_cached_fetches_failed(
        self,
        error_type: str,
        ignored_user_ids: list[str] | None = None,
    ) -> int:
        ignored = set(ignored_user_ids or [])
        marked = 0
        now = datetime.now().isoformat(timespec="seconds")
        for user_id, entry in self.cache_store.load().items():
            if user_id in ignored or not isinstance(entry, dict):
                continue
            user_data = entry.get("data", {})
            progress = entry.get("progress", {})
            try:
                self.update_fetch_status(
                    user_id,
                    f"_{user_id[-4:]}",
                    "failed",
                    latest_daily_date=user_data.get("last_daily_date"),
                    last_success_at=user_data.get("last_fetch_success_at"),
                    last_attempt_at=now,
                    stage=progress.get("stage"),
                    error_type=error_type,
                )
                marked += 1
            except Exception as exc:
                logging.error("Failed to publish cached fetch status (%s).", type(exc).__name__)
            self._check_and_notify_stale_data(user_id, entry)
        return marked

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
        payload = HistoryPayloadBuilder.daily_history(self._get_recent_daily_history(user_id))
        if payload is None:
            return

        sensor_name = DAILY_HISTORY_SENSOR_NAME + postfix
        self._publish_sensor_state(
            sensor_name,
            user_id,
            payload["state"],
            unit="kWh",
            icon="mdi:chart-timeline-variant",
            device_class="energy",
            state_class="",
            extra_attributes=payload["attributes"],
        )
        self._log_sensor_update(
            sensor_name,
            payload["state"],
            "kWh",
            **payload["log"],
        )

    def update_monthly_history_data(self, user_id: str, postfix: str):
        payload = HistoryPayloadBuilder.monthly_history(self._get_recent_monthly_history(user_id))
        if payload is None:
            return

        sensor_name = MONTHLY_HISTORY_SENSOR_NAME + postfix
        self._publish_sensor_state(
            sensor_name,
            user_id,
            payload["state"],
            unit="kWh",
            icon="mdi:chart-bar",
            device_class="",
            state_class="measurement",
            extra_attributes=payload["attributes"],
        )
        self._log_sensor_update(
            sensor_name,
            payload["state"],
            "kWh",
            **payload["log"],
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
        persist: bool = True,
    ):
        sensor_name = FETCH_STATUS_SENSOR_NAME + postfix
        now = datetime.now()
        source_delay_days = None
        if latest_daily_date:
            try:
                source_delay_days = (now.date() - datetime.strptime(latest_daily_date, "%Y-%m-%d").date()).days
            except Exception:
                source_delay_days = None

        if persist and last_attempt_at is None:
            last_attempt_at = now.isoformat(timespec="seconds")
        attributes = {
            "latest_daily_date": latest_daily_date,
            "source_delay_days": source_delay_days,
            "last_success_at": last_success_at,
            "last_attempt_at": last_attempt_at,
            "stage": stage,
            "error_type": error_type,
        }
        if persist:
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

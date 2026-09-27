#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=/data/options.json

json_get() {
  python3 - "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

key = sys.argv[1]
default = sys.argv[2]
path = Path("/data/options.json")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {}
value = data.get(key, default)
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PY
}

json_dump() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

key = sys.argv[1]
path = Path("/data/options.json")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {}
print(json.dumps(data.get(key, []), ensure_ascii=False))
PY
}

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "Add-on options not found at ${CONFIG_PATH}" >&2
  exit 1
fi

export ACCOUNT="$(json_get account "")"
export PASSWORD="$(json_get password "")"
export IGNORE_USER_ID="$(json_get ignore_user_id "")"
export MQTT_HOST="$(json_get mqtt_host core-mosquitto)"
export MQTT_PORT="$(json_get mqtt_port 1883)"
export MQTT_USERNAME="$(json_get mqtt_username "")"
export MQTT_PASSWORD="$(json_get mqtt_password "")"
export MQTT_PUBLISH_TIMEOUT_SECONDS="$(json_get mqtt_publish_timeout_seconds 10)"
export JOB_START_TIME="$(json_get job_start_time 07:00)"
export JOB_TIMES="$(json_get job_times 2)"
export RETRY_TIMES_LIMIT="$(json_get retry_times_limit 3)"
export RETRY_WAIT_TIME_OFFSET_UNIT="$(json_get retry_wait_time_offset_unit 5)"
export REPUBLISH_INTERVAL_MINUTES="$(json_get republish_interval_minutes 0)"
export FETCH_ATTEMPT_TIMEOUT_MINUTES="$(json_get fetch_attempt_timeout_minutes 30)"
export DAILY_USAGE_WINDOW_DAYS="$(json_get daily_usage_window_days 7)"
export PUBLISH_TOU_DETAIL_SENSORS="$(json_get publish_tou_detail_sensors false)"
export TOU_PRICE_CONFIG="$(json_get tou_price_config config/tou_price_config.json)"
export NOTIFIER="$(json_get notifier none)"
export TG_BOT_TOKEN="$(json_get tg_bot_token "")"
export TG_CHAT_ID="$(json_get tg_chat_id "")"
export TG_API_BASE_URL="$(json_get tg_api_base_url https://api.telegram.org)"
export STALE_DATA_ALERT_DAYS="$(json_get stale_data_alert_days 2)"
export HISTORY_GAP_ALERT_DAYS="$(json_get history_gap_alert_days 30)"
export CAPTCHA_POINT_CLICK_MAX_REFRESHES="$(json_get captcha_point_click_max_refreshes 4)"
export LOGIN_FALLBACK="$(json_get login_fallback qrcode)"
export QR_CODE_LOGIN_REFRESH_LIMIT="$(json_get qr_code_login_refresh_limit 1)"
export TRACE_RETENTION_DAYS="$(json_get trace_retention_days 7)"

LOGIN_CREDENTIALS_JSON="$(json_dump login_credentials)"
if [[ "${LOGIN_CREDENTIALS_JSON}" != "[]" ]]; then
  export LOGIN_CREDENTIALS="${LOGIN_CREDENTIALS_JSON}"
fi

exec xvfb-run -a --server-args="-screen 0 1920x1080x24" python3 -m scripts.main

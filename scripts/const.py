"""Project constants used across the scraper and MQTT publisher."""

LOGIN_URL = "https://95598.cn/osgweb/login"
HOME_URL = "https://95598.cn/osgweb/index"
ELECTRIC_USAGE_URL = "https://95598.cn/osgweb/electricityCharge"
BALANCE_URL = "https://95598.cn/osgweb/userAcc"
ELECTRIC_BILL_SUMMARY_URL = "https://95598.cn/osgweb/electricitySummary"

BALANCE_SENSOR_NAME = "sensor.electricity_charge_balance"
DAILY_USAGE_SENSOR_NAME = "sensor.last_electricity_usage"
DAILY_CHARGE_SENSOR_NAME = "sensor.last_electricity_charge"
TOTAL_USAGE_SENSOR_NAME = "sensor.total_electricity_usage"
TOTAL_CHARGE_SENSOR_NAME = "sensor.total_electricity_charge"
DAILY_HISTORY_SENSOR_NAME = "sensor.daily_electricity_history"
MONTHLY_HISTORY_SENSOR_NAME = "sensor.monthly_electricity_history"
DAILY_HISTORY_PUBLISH_DAYS = 180
MONTHLY_HISTORY_PUBLISH_MONTHS = 12
YEARLY_USAGE_SENSOR_NAME = "sensor.yearly_electricity_usage"
YEARLY_CHARGE_SENSOR_NAME = "sensor.yearly_electricity_charge"
MONTH_USAGE_SENSOR_NAME = "sensor.month_electricity_usage"
MONTH_CHARGE_SENSOR_NAME = "sensor.month_electricity_charge"
VALLEY_USAGE_SENSOR_NAME = "sensor.last_valley_electricity_usage"
FLAT_USAGE_SENSOR_NAME = "sensor.last_flat_electricity_usage"
PEAK_USAGE_SENSOR_NAME = "sensor.last_peak_electricity_usage"
TIP_USAGE_SENSOR_NAME = "sensor.last_tip_electricity_usage"
MONTH_VALLEY_USAGE_SENSOR_NAME = "sensor.month_valley_electricity_usage"
MONTH_FLAT_USAGE_SENSOR_NAME = "sensor.month_flat_electricity_usage"
MONTH_PEAK_USAGE_SENSOR_NAME = "sensor.month_peak_electricity_usage"
MONTH_TIP_USAGE_SENSOR_NAME = "sensor.month_tip_electricity_usage"
YEARLY_VALLEY_USAGE_SENSOR_NAME = "sensor.yearly_valley_electricity_usage"
YEARLY_FLAT_USAGE_SENSOR_NAME = "sensor.yearly_flat_electricity_usage"
YEARLY_PEAK_USAGE_SENSOR_NAME = "sensor.yearly_peak_electricity_usage"
YEARLY_TIP_USAGE_SENSOR_NAME = "sensor.yearly_tip_electricity_usage"
FETCH_STATUS_SENSOR_NAME = "sensor.ha_95598_fetch_status"

BALANCE_UNIT = "CNY"
USAGE_UNIT = "kWh"

SENSOR_FRIENDLY_LABELS = {
    BALANCE_SENSOR_NAME: "电费余额",
    DAILY_USAGE_SENSOR_NAME: "最新日电量",
    DAILY_CHARGE_SENSOR_NAME: "最新日电费",
    TOTAL_USAGE_SENSOR_NAME: "总用电量",
    TOTAL_CHARGE_SENSOR_NAME: "总电费",
    DAILY_HISTORY_SENSOR_NAME: "日用电历史",
    MONTHLY_HISTORY_SENSOR_NAME: "月用电历史",
    MONTH_USAGE_SENSOR_NAME: "本月电量",
    MONTH_CHARGE_SENSOR_NAME: "本月电费",
    YEARLY_USAGE_SENSOR_NAME: "本年电量",
    YEARLY_CHARGE_SENSOR_NAME: "本年电费",
    VALLEY_USAGE_SENSOR_NAME: "最新日电量-谷",
    FLAT_USAGE_SENSOR_NAME: "最新日电量-平",
    PEAK_USAGE_SENSOR_NAME: "最新日电量-峰",
    TIP_USAGE_SENSOR_NAME: "最新日电量-尖",
    MONTH_VALLEY_USAGE_SENSOR_NAME: "本月电量-谷",
    MONTH_FLAT_USAGE_SENSOR_NAME: "本月电量-平",
    MONTH_PEAK_USAGE_SENSOR_NAME: "本月电量-峰",
    MONTH_TIP_USAGE_SENSOR_NAME: "本月电量-尖",
    YEARLY_VALLEY_USAGE_SENSOR_NAME: "本年电量-谷",
    YEARLY_FLAT_USAGE_SENSOR_NAME: "本年电量-平",
    YEARLY_PEAK_USAGE_SENSOR_NAME: "本年电量-峰",
    YEARLY_TIP_USAGE_SENSOR_NAME: "本年电量-尖",
    FETCH_STATUS_SENSOR_NAME: "同步状态",
}

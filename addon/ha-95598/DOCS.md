# 95598 for Home Assistant Add-on

## 配置项

### 95598 登录

- `account` / `password`：你的 `95598` 登录账号和密码。
- `login_credentials`：可选。多个能看到同一批户号的登录凭据，密码登录失败或验证码无法通过时会轮换。
- `ignore_user_id`：可选。忽略指定户号，多个户号用英文逗号分隔。

### MQTT

- `mqtt_host`：MQTT Broker 地址。官方 Mosquitto Add-on 通常是 `core-mosquitto`。
- `mqtt_port`：MQTT 端口，默认 `1883`。
- `mqtt_username` / `mqtt_password`：MQTT 认证信息，没有认证可留空。
- `mqtt_publish_timeout_seconds`：单条 MQTT 发布最长等待秒数，默认 `10`。

### 同步

- `job_start_time`：每天第一轮同步开始时间。
- `job_times`：每天同步次数。
- `daily_usage_window_days`：每次同步最近 `7` 或 `30` 天日用电数据。
- `publish_tou_detail_sensors`：是否额外发布谷、平、峰、尖分时细项实体。
- `tou_price_config`：电价配置文件路径。默认 `config/tou_price_config.json`。

### 登录兜底和通知

- `login_fallback`：密码登录失败或验证码无法自动通过时是否使用二维码兜底。
- `captcha_point_click_max_refreshes`：点选验证码低置信或失败后的最大刷新次数。
- `notifier`：可选 `telegram`，用于推送登录二维码、数据停更和历史缺口告警。
- `stale_data_alert_days`：最新日数据落后多少天后告警。
- `history_gap_alert_days`：检查最近多少天内的日历史缺口。

## 重要说明

本项目仅用于同步你本人有权访问的 `95598` 数据。运行时会处理账号、户号、电费电量、页面截图和验证码样本，请妥善保护 add-on 数据目录。

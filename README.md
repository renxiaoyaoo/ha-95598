# 95598 for Home Assistant

把国家电网 `95598` 的电量、电费、余额和历史用电数据同步到 Home Assistant。

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![GHCR](https://img.shields.io/badge/image-ghcr.io%2Frenxiaoyaoo%2Fha--95598-2496ED.svg)](https://github.com/renxiaoyaoo/ha-95598/pkgs/container/ha-95598)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-MQTT%20Discovery-41BDF5.svg)](#home-assistant)
[![Python](https://img.shields.io/badge/python-3.12-3776AB.svg)](Dockerfile)
[![Docker Compose](https://img.shields.io/badge/deploy-Docker%20Compose-2496ED.svg)](docker-compose.image.yml)
[![Platforms](https://img.shields.io/badge/platform-amd64%20%7C%20arm64-555.svg)](.github/workflows/docker-publish.yml)
[![Data](https://img.shields.io/badge/storage-SQLite-003B57.svg)](#数据和文件)

<p align="center">
  <a href="#效果预览">
    <img height="40" alt="Field data since 2025-09-01" src="https://img.shields.io/badge/field%20data-since%202025--09--01-2ea44f?style=for-the-badge&logo=homeassistant&logoColor=white" />
  </a>
</p>

本项目会定时登录 [`95598`](https://95598.cn/)，获取余额、日/月/年用电量、电费和日用电历史，通过 MQTT Discovery 发布到 Home Assistant，并把结构化历史数据保存到本地 SQLite。

项目基于 [ARC-MX/sgcc_electricity_new](https://github.com/ARC-MX/sgcc_electricity_new) 整理和重构，在此向原作者表达谢意和致敬。

## 使用声明

本项目仅用于同步你本人有权访问的国家电网 `95598` 账户数据到本地 Home Assistant。请勿用于批量采集、代抓、共享账号、绕过访问控制或任何违反服务条款、法律法规的场景。

运行本项目会处理账号、户号、用电地址、电费电量等个人信息。请妥善保护 `.env`、`data/`、日志、截图和验证码样本，不要把这些文件提交到公开仓库或分享给他人。

## 效果预览

<table>
  <tr>
    <td width="50%">
      <a href="examples/energy-dashboard/daily-chart.png">
        <img src="examples/energy-dashboard/daily-chart.png" alt="每日电费与用电量" width="100%" />
      </a>
    </td>
    <td width="50%">
      <a href="examples/energy-dashboard/entities.png">
        <img src="examples/energy-dashboard/entities.png" alt="实体展示" width="100%" />
      </a>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <a href="examples/energy-dashboard/energy-panel.png">
        <img src="examples/energy-dashboard/energy-panel.png" alt="能源面板" width="100%" />
      </a>
    </td>
  </tr>
</table>

详细配置和示例在 [examples/README.md](examples/README.md)。

## 功能

- 自动同步国家电网 `95598` 账户数据。
- 通过 MQTT Discovery 自动创建设备和实体。
- 保存日/月/年历史数据到 SQLite。
- 提供日用电历史图表数据；日常同步会补最近 `7` 或 `30` 天，数据库已有历史会继续保留，MQTT 日历史实体默认发布最近 `180` 天。
- 支持按指定日期范围补充日用电量和分时数据。
- 支持无人值守登录、二维码登录兜底，可选 Telegram 推送登录二维码和数据停更告警。
- 支持可选谷、平、峰、尖分时细项实体。
- 使用 `Docker + Xvfb + Chromium + Selenium` 运行，尽量贴近真实浏览器环境。

## 适用条件

运行前需要准备：

- 国家电网 `95598` 账号：账号可登录，并且已经绑定户号、能查询电量电费。
- 系统环境：主要验证环境是 Linux + Docker；macOS / Windows / NAS 等环境只要能运行 Docker，理论上也可以使用，但不是主要验证路径。
- 运行方式：推荐 Docker / Docker Compose；预构建镜像发布 `linux/amd64` 和 `linux/arm64`。
- 系统资源：建议至少 `1 GB` 可用内存；使用预构建镜像建议预留 `3 GB+` 磁盘空间，本地构建建议预留 `5 GB+`。
- Home Assistant：需要启用 MQTT 集成。
- MQTT Broker：例如 Mosquitto；如果暂时不接 Home Assistant，可以把 `MQTT_HOST` 留空，只写入本地 SQLite。

## 快速开始

### Docker Compose

1. 准备配置文件。

```bash
cp example.env .env
```

2. 编辑 `.env`，至少填写：

```env
ACCOUNT="你的95598账号"
PASSWORD="你的95598密码"
MQTT_HOST="你的MQTT地址"
```

如果同一批户号绑定了多个 `95598` 登录名，可以使用登录凭据池。程序会在密码登录失败或验证码无法通过时按顺序轮换，全部失败后再进入二维码兜底：

```env
LOGIN_CREDENTIALS='[{"account":"账号1","password":"密码1","label":"main"},{"account":"账号2","password":"密码2","label":"backup"}]'
```

只建议把“登录后能看到同一批户号”的账号放进同一个实例。不同户号集合应拆成多个实例运行，避免数据混在一起。

如果暂时不接 Home Assistant，可以留空：

```env
MQTT_HOST=""
```

3. 启动服务。

使用已发布镜像：

```bash
docker compose -f docker-compose.image.yml up -d ha-95598
docker compose -f docker-compose.image.yml logs -f ha-95598
```

本地构建：

```bash
docker compose up -d --build ha-95598
docker compose logs -f ha-95598
```

### Home Assistant Add-on

Home Assistant OS / Supervised 用户可以使用 add-on 方式安装，详细说明见 [addon/ha-95598/README.md](addon/ha-95598/README.md)。

## 配置

主要配置都在 [example.env](example.env)，复制成 `.env` 后按注释修改。

你可以配置这些内容：

- `95598` 登录账号、密码、登录凭据池，以及需要忽略的户号。
- Home Assistant / MQTT 发布地址、端口和认证信息。
- 每天同步次数、开始时间、失败重试次数和页面等待时间。
- 每次同步最近 `7` 天或 `30` 天日用电数据。
- 是否额外发布谷、平、峰、尖分时细项实体。
- 页面截图、错误快照和验证码调试图片保留天数。
- 是否启用无人值守登录、二维码兜底，以及二维码过期后是否自动刷新重发。
- 是否启用 Telegram 通知，当前用于推送登录二维码和数据停更告警。

> [!IMPORTANT]
> 日电费是按 [tou_price_config.json](config/tou_price_config.json) 估算的。
> 默认配置是湖南居民阶梯电价示例，不一定适合你的地区。
> 使用前请按本地电价调整；也可以通过 `TOU_PRICE_CONFIG` 指定自己的配置文件。

## Home Assistant

程序通过 MQTT Discovery 自动创建设备和实体，不需要手动写 `configuration.yaml`。

默认实体：

| 显示名 | 实体 ID |
| --- | --- |
| 电费余额 | `sensor.electricity_charge_balance_xxxx` |
| 最新日电量 | `sensor.last_electricity_usage_xxxx` |
| 最新日电费 | `sensor.last_electricity_charge_xxxx` |
| 总用电量 | `sensor.total_electricity_usage_xxxx` |
| 总电费 | `sensor.total_electricity_charge_xxxx` |
| 日用电历史 | `sensor.daily_electricity_history_xxxx` |
| 月用电历史 | `sensor.monthly_electricity_history_xxxx` |
| 本月电量 | `sensor.month_electricity_usage_xxxx` |
| 本月电费 | `sensor.month_electricity_charge_xxxx` |
| 本年电量 | `sensor.yearly_electricity_usage_xxxx` |
| 本年电费 | `sensor.yearly_electricity_charge_xxxx` |

其中 `xxxx` 是户号后四位。Home Assistant 可能会在实体 ID 冲突时自动追加后缀，请以实际生成的实体 ID 为准。
设备名显示为 `95598-xxxx`。如果你之前已经创建过旧实体，HA 里的 `entity_id` 可能不会自动改名，需要删除旧实体后重新发现。
`sensor.daily_electricity_history_xxxx` 的属性里会发布最近 `180` 天的本地日历史序列，序列包含日期、电量和电费。
`sensor.monthly_electricity_history_xxxx` 的属性里会发布最近 `12` 个月的本地月历史序列，序列包含电量、电费和分时电量。

这两个历史实体主要用于仪表盘图表，属性较大，建议从 Home Assistant recorder 排除，避免 HA 数据库长期膨胀：

```yaml
recorder:
  exclude:
    entities:
      - sensor.daily_electricity_history_xxxx
      - sensor.monthly_electricity_history_xxxx
```

分时细项默认不发布。需要谷、平、峰、尖实体时，设置：

```env
PUBLISH_TOU_DETAIL_SENSORS=true
```

开启后会额外发布：

| 数据 | 实体 ID |
| --- | --- |
| 最新日谷/平/峰/尖电量 | `sensor.last_valley_electricity_usage_xxxx` / `sensor.last_flat_electricity_usage_xxxx` / `sensor.last_peak_electricity_usage_xxxx` / `sensor.last_tip_electricity_usage_xxxx` |
| 本月谷/平/峰/尖电量 | `sensor.month_valley_electricity_usage_xxxx` / `sensor.month_flat_electricity_usage_xxxx` / `sensor.month_peak_electricity_usage_xxxx` / `sensor.month_tip_electricity_usage_xxxx` |
| 本年谷/平/峰/尖电量 | `sensor.yearly_valley_electricity_usage_xxxx` / `sensor.yearly_flat_electricity_usage_xxxx` / `sensor.yearly_peak_electricity_usage_xxxx` / `sensor.yearly_tip_electricity_usage_xxxx` |

详细的 Home Assistant 能源面板配置、日用电图表 YAML 和效果图都放在 [examples/README.md](examples/README.md)。

### 能源面板日期修正

Home Assistant 能源面板读取的是 recorder long-term statistics，不是实体属性里的日历史。普通 MQTT 发布只能更新“当前总量”：如果程序停更几天后一次补到多天数据，HA 可能会把这几天的差额全部记到补抓当天。

需要能源面板也按真实日期显示时，可以开启 recorder 回填。开启后，每次抓取成功都会根据本地 SQLite 的 `daily_usage` 重建总电量和总电费的每日累计点，并写入 HA recorder statistics。

1. 在 compose 里挂载 Home Assistant 配置目录。

```yaml
volumes:
  - ./data:/app/data
  - ./config:/app/config:ro
  - /你的/home-assistant/config:/ha-config
```

2. 在 `.env` 中启用。

```env
HA_ENERGY_BACKFILL_ENABLED=true
HA_RECORDER_DB_PATH=/ha-config/home-assistant_v2.db
```

首次开启建议同时设置：

```env
HA_ENERGY_BACKFILL_BACKUP=true
```

确认能源面板显示正常后，可以把备份关闭，避免每天产生数据库备份文件。更多可选项见 [example.env](example.env) 中的“Home Assistant 能源面板日期修正”。

## 数据和文件

运行数据位于 `data/`：

| 文件 | 说明 |
| --- | --- |
| `homeassistant.db` | SQLite 历史数据 |
| `ha_95598_cache.json` | 当前状态和同步进度 |
| `ha_95598_session.json` | 登录会话 |
| `pages/` | 页面追踪和错误快照 |
| `login_qr_code.png` | 二维码登录临时文件 |

查看数据库：

```bash
docker compose run --rm ha-95598 python3 -m scripts.show_db
```

本地开发环境也可以运行：

```bash
.venv/bin/python -m scripts.show_db
```

按日期范围补充日用电数据：

```bash
docker compose run --rm ha-95598 python3 -m scripts.fetch_daily_range --start 2026-01-01 --end 2026-01-31
```

这个命令会复用同一套登录流程，抓取指定日期范围内的日用电量和谷、平、峰、尖分时数据，计算日电费后写入 SQLite，并刷新 Home Assistant 的日历史和汇总实体。它和日常定时同步是并列入口，不会改写当天同步进度。

## 更新

使用已发布镜像：

```bash
docker compose -f docker-compose.image.yml pull
docker compose -f docker-compose.image.yml up -d ha-95598
```

本地构建：

```bash
git pull
docker compose up -d --build ha-95598
```

## 开发和测试

开发模式会把整个仓库挂载进容器，改 Python 代码后重启容器即可。

```bash
docker compose -f docker-compose.dev.yml up -d --build ha-95598
docker compose -f docker-compose.dev.yml logs -f ha-95598
```

本地运行测试建议使用 Python `3.12`，和 Docker 镜像保持一致：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

不建议用 Python `3.13` 安装完整开发依赖；部分固定依赖版本可能没有兼容 wheel。

代码检查：

```bash
python3 scripts/tools/syntax_check.py
```

提交前隐私检查：

```bash
python3 scripts/tools/privacy_check.py --staged
```

单元测试：

```bash
.venv/bin/python -m pytest -q
```

测试只收集 `tests/`，运行态 `data/` 目录不会被 pytest 扫描。

校验当前启用的本地电价配置：

```bash
python3 scripts/tools/check_local_tariff.py
```

这个命令只输出配置文件名、版本名、月份覆盖和阶梯阈值摘要，不输出 `.env` 内容。私人电价建议放在被 `.gitignore` 忽略的 `config/tou_price_config.local.json`，并通过 `TOU_PRICE_CONFIG` 指向它。

离线回放点选验证码样本：

```bash
python3 -m captcha_solver.tools.replay_point_click --summary-only
```

程序在线遇到点选验证码时，会在 `data/pages/` 保存 `tencent_point_click_answer_*.png`、`tencent_point_click_bg_*.png` 和 `tencent_point_click_report_*.json`。后续调算法时优先用这些样本离线回放，避免频繁线上登录触发风控。
`data/captcha_samples/` 下的验证码学习样本和回放报告会自动清理，默认保留最近 `14` 天；需要调整时见 [example.env](example.env) 中的验证码保留配置。

## 常见问题

### 没有 MQTT Broker 能不能用

可以。

把 `MQTT_HOST` 留空，程序会同步数据并写入 SQLite，但不会在 Home Assistant 中创建设备和实体。

### 二维码在哪里

如果触发二维码登录，图片会保存到：

```text
data/login_qr_code.png
```

启用 Telegram 通知后，也可以推送二维码提醒。

### Telegram 会推送什么

当前 Telegram 通知只做两件事：

- 登录需要扫码时，推送登录二维码。
- 最新日电量日期落后超过 `STALE_DATA_ALERT_DAYS` 时，推送数据停更告警。

它不会推送余额不足、每日账单摘要或每次同步成功通知。

如果当前网络无法直连 `api.telegram.org`，可以在 `.env` 里配置 `TG_API_BASE_URL` 为你的 Telegram API 反代地址，例如：

```env
TG_API_BASE_URL="https://tg-api.example.com"
```

### 点选验证码能不能稳定通过

不能保证。

点选验证码是 best-effort 方案，当前会尽量按图形轮廓和相似度去匹配；但题型、背景和风控策略会变化，所以成功率不是固定值。低置信时程序会主动刷新验证码，必要时会回退到二维码登录。

### 为什么镜像比较大

当前镜像包含完整 Chromium、chromedriver、Xvfb、中文字体和验证码识别依赖。这样做的目标是让 Docker 内浏览器更接近真实桌面环境，减少登录阶段被风控误判的概率。

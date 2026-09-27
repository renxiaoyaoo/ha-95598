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

详细仪表盘配置和图表 YAML 在 [examples/README.md](examples/README.md)。

## 项目地图

- [架构和数据流](docs/ARCHITECTURE.md)
- [运行机制](docs/RUNTIME.md)
- [数据模型](docs/DATA_MODEL.md)
- [隐私说明](docs/PRIVACY.md)
- [排障指南](docs/TROUBLESHOOTING.md)

## 功能

- 自动同步国家电网 `95598` 账户数据。
- 通过 MQTT Discovery 自动创建 Home Assistant 设备和实体。
- 保存日/月/年历史数据到 SQLite。
- 默认发布最近 `180` 天日历史和最近 `12` 个月月历史。
- 支持按日期范围补日用电量和分时数据。
- 支持无人值守登录、二维码兜底、可选 Telegram 通知。
- 支持可选谷、平、峰、尖分时细项实体。
- 使用 `Docker + Xvfb + Chromium + Selenium` 运行。

## 适用条件

- 一个可登录的国家电网 `95598` 账号，且已绑定需要同步的户号。
- Linux + Docker 环境；其他能运行 Docker 的系统理论可用。
- Home Assistant MQTT 集成和一个可访问的 MQTT Broker。
- 至少 `1 GB` 可用内存；预构建镜像建议预留 `3 GB+` 磁盘空间。

## 最快部署

普通 Docker 部署只需要三步。

1. 复制最小配置。

```bash
cp .env.example .env
```

2. 编辑 `.env`，至少填写 95598 账号和密码。需要发布到 Home Assistant 时再填写 MQTT。

```env
ACCOUNT="你的95598账号"
PASSWORD="你的95598密码"
MQTT_HOST="你的MQTT地址"
```

暂时不接 Home Assistant 时可以留空：

```env
MQTT_HOST=""
```

3. 启动服务并跑一次安全诊断。

使用已发布镜像：

```bash
docker compose -f docker-compose.image.yml up -d ha-95598
python3 scripts/tools/config_doctor.py --all
```

本地构建：

```bash
docker compose up -d --build ha-95598
python3 scripts/tools/config_doctor.py --all
```

Home Assistant OS / Supervised 用户也可以使用 add-on，说明见 [addon/ha-95598/README.md](addon/ha-95598/README.md)。

查看日志：

```bash
docker compose logs -f ha-95598
```

## 配置

最小配置在 [.env.example](.env.example)。完整配置示例在 [example.env](example.env)。

### 必填

| 配置 | 说明 |
| --- | --- |
| `ACCOUNT` / `PASSWORD` | 95598 登录账号和密码 |
| `LOGIN_CREDENTIALS` | 可选；账号池。配置后可不填 `ACCOUNT` / `PASSWORD` |

### 常用可选

| 配置 | 说明 |
| --- | --- |
| `IGNORE_USER_ID` | 可选忽略指定户号 |
| `MQTT_HOST` / `MQTT_PORT` | MQTT Broker；留空则不发布 HA 实体 |
| `MQTT_PUBLISH_TIMEOUT_SECONDS` | 单条 MQTT 发布最长等待秒数，默认 `10` |
| `JOB_START_TIME` / `JOB_TIMES` | 每天同步时间和次数 |
| `FETCH_ATTEMPT_TIMEOUT_MINUTES` | 单次抓取超时分钟数，默认 `30` |
| `DAILY_USAGE_WINDOW_DAYS` | 每次同步最近 `7` 或 `30` 天 |
| `HISTORY_GAP_ALERT_DAYS` | 检查最近多少天的日历史缺口，默认 `30` |
| `PUBLISH_TOU_DETAIL_SENSORS` | 是否发布分时细项实体 |
| `TOU_PRICE_CONFIG` | 私人电价配置路径 |
| `NOTIFIER` | 通知器，当前支持 `none` / `telegram` |

### 高级可选

| 配置 | 说明 |
| --- | --- |
| `HA_ENERGY_BACKFILL_ENABLED` | 是否启用 HA 能源面板 recorder 回填 |
| `HA_RECORDER_DB_PATH` | Home Assistant recorder 数据库路径 |
| `HA_ENERGY_BACKFILL_BACKUP_KEEP` | recorder 自动备份保留份数，默认 `2` |
| `CAPTCHA_POINT_CLICK_MAX_REFRESHES` | 点选验证码低置信刷新次数 |

> [!IMPORTANT]
> 日电费会按电价配置估算。仓库默认电价只是示例，不一定适合你的地区。私人电价建议放在被 `.gitignore` 忽略的 `config/tou_price_config.local.json`，并通过 `TOU_PRICE_CONFIG` 指向它。

## Home Assistant

程序通过 MQTT Discovery 自动创建设备和实体，不需要手动写 `configuration.yaml`。

默认实体包括：

- 电费余额
- 最新日电量、最新日电费
- 总用电量、总电费
- 日用电历史、月用电历史
- 本月电量、本月电费
- 本年电量、本年电费

实体 ID 通常以户号后四位结尾，例如 `sensor.daily_electricity_history_xxxx`。Home Assistant 可能会在冲突时追加额外后缀，请以实际生成结果为准。

历史实体属性较大，建议从 Home Assistant recorder 排除，避免 HA 数据库长期膨胀。详细实体说明、Energy 面板配置和图表 YAML 见 [examples/README.md](examples/README.md)。

## 数据和文件

运行数据位于 `data/`：

| 文件 | 说明 |
| --- | --- |
| `homeassistant.db` | SQLite 历史数据 |
| `ha_95598_cache.json` | 当前状态和同步进度 |
| `ha_95598_session.json` | 登录会话 |
| `pages/` | 页面追踪和错误快照 |
| `captcha_samples/` | 验证码学习样本 |
| `login_qr_code.png` | 二维码登录临时文件 |

这些文件可能包含隐私数据，不要提交或分享。更多说明见 [docs/PRIVACY.md](docs/PRIVACY.md)。

## 常用命令

查看日志：

```bash
docker compose logs -f ha-95598
```

查看本地数据摘要：

```bash
docker compose run --rm ha-95598 python3 -m scripts.show_db
```

按日期范围补日数据：

```bash
docker compose run --rm ha-95598 python3 -m scripts.fetch_daily_range --start 2026-01-01 --end 2026-01-31
```

一键安全诊断：

```bash
python3 scripts/tools/config_doctor.py --all
```

提交前检查：

```bash
python3 scripts/tools/privacy_check.py
python3 scripts/tools/privacy_check.py --staged
python3 scripts/tools/syntax_check.py
.venv/bin/python -m pytest -q
```

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

## 开发

开发模式会把整个仓库挂载进容器，改 Python 代码后重启容器即可。

```bash
docker compose -f docker-compose.dev.yml up -d --build ha-95598
docker compose -f docker-compose.dev.yml logs -f ha-95598
```

本地运行测试建议使用 Python `3.12`：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

## 常见问题

常见排障见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

简要原则：

- 没有 MQTT Broker 也能运行，只是不发布 HA 实体。
- 二维码登录图片只保存在本地 `data/login_qr_code.png`。
- Telegram 只用于登录二维码、数据停更和历史缺口告警。
- 95598 网站可能延迟更新日数据或账单，这不一定是抓取失败。
- Selenium 网页自动化依赖 95598 当前页面结构，官网改版后可能需要维护选择器。

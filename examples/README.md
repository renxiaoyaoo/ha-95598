# Examples

这里放的是可直接照着用的示例配置和截图。

## energy-dashboard

这一组适合直接照着搭 Home Assistant 仪表盘。

### 里面有什么

- [`chart.yaml`](energy-dashboard/chart.yaml)：近 `180` 天每日电费的 `apexcharts-card` 配置。
- [`daily-chart.png`](energy-dashboard/daily-chart.png)：图表效果图。
- [`energy-panel.png`](energy-dashboard/energy-panel.png)：Home Assistant 能源面板配置参考。
- [`entities.png`](energy-dashboard/entities.png)：实体名称和展示效果参考。

### 怎么用

1. 打开 `energy-dashboard/chart.yaml`。
2. 把 `sensor.95598_xxxx_daily_electricity_history_xxxx` 换成你自己的日用电历史实体 ID。
3. 把 YAML 直接粘到 Home Assistant 仪表盘里。
4. 按截图微调样式。

### 能源面板配置

Home Assistant 里这样配：

1. 打开 `设置` -> `仪表盘` -> `能源`。
2. 在“电网输入的能源”里选 `sensor.total_electricity_usage_xxxx`。
3. 成本跟踪选“使用可跟踪总成本的实体”。
4. 成本实体选 `sensor.total_electricity_charge_xxxx`。
5. 功率测量类型先选“无供电传感器”。

说明：

- `sensor.total_electricity_usage_xxxx` 是累计电量，适合能源面板。
- `sensor.last_electricity_usage_xxxx` 是最新单日用电量，不适合作为累计输入。

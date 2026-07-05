# 月度水/燃气手工录入

这个 package 适合水表、燃气表只能人工抄表的场景：

- 在 Home Assistant 里录入累计表读数。
- `utility_meter` 自动按月统计用量。
- 按录入的单价自动计算本月费用。

安装方式：

1. 确认 Home Assistant 已启用 packages：

```yaml
homeassistant:
  packages: !include_dir_named packages
```

2. 把 `monthly-utilities.yaml` 放到 Home Assistant 配置目录的 `packages/` 下。
3. 重启 Home Assistant。
4. 在 HA UI 里填写：
   - `input_number.water_meter_reading`
   - `input_number.water_unit_price`
   - `input_number.gas_meter_reading`
   - `input_number.gas_unit_price`

注意：录入的是累计表读数，不是本月用量。月度用量由 Home Assistant 根据读数差额计算。

核心实体 ID：

- `sensor.water_meter_reading_total`
- `sensor.monthly_water_usage`
- `sensor.monthly_water_charge`
- `sensor.gas_meter_reading_total`
- `sensor.monthly_gas_usage`
- `sensor.monthly_gas_charge`

# Data Model

The local database is SQLite. It stores history for each 95598 user ID and is the source for long history MQTT payloads.

## Tables

### `daily_usage`

One row per user and date.

| Field | Meaning |
| --- | --- |
| `date` | Day in `YYYY-MM-DD` |
| `total_usage` | Daily kWh |
| `total_charge` | Daily charge, official if available or locally calculated |
| `valley_usage` / `flat_usage` / `peak_usage` / `tip_usage` | Time-of-use segments |

### `monthly_usage`

One row per user and month.

| Field | Meaning |
| --- | --- |
| `month` | Month in `YYYY-MM` |
| `total_usage` | Monthly kWh |
| `total_charge` | Monthly charge |
| `source` | `official` for 95598 monthly bill, `calculated` for daily fallback |
| TOU fields | Monthly valley/flat/peak/tip usage when known |

Official monthly bills take priority. Daily aggregation does not overwrite an official bill.

### `yearly_usage`

One row per user and year. It is refreshed from monthly rows when monthly data changes.

## Home Assistant Payloads

MQTT state topics publish compact JSON objects:

```json
{"state": 12.34}
```

History sensors include attributes:

```json
{
  "state": 12.34,
  "series": [
    {"date": "2026-01-01", "usage": 10.0, "charge": 5.2}
  ]
}
```

`daily_electricity_history` publishes recent daily rows. `monthly_electricity_history` publishes recent monthly rows. These attributes can be large, so excluding them from Home Assistant recorder is recommended.

## Billing Rule

Monthly billing uses this order:

1. Use official 95598 monthly bill when available.
2. Otherwise calculate monthly totals from daily rows.
3. Refresh yearly totals from monthly rows.

Daily charge is calculated with the configured TOU tariff when 95598 has not provided a final daily charge yet.

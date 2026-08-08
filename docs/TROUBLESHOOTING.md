# Troubleshooting

Start with the safe doctor command:

```bash
python3 scripts/tools/config_doctor.py
```

For Docker Compose validation without printing expanded private config:

```bash
python3 scripts/tools/config_doctor.py --compose
```

## Login Fails

Check:

- The 95598 account can log in manually.
- `ACCOUNT` / `PASSWORD` or `LOGIN_CREDENTIALS` are correct.
- The account can see the expected bound user IDs.
- `FETCH_ON_STARTUP` is not causing repeated login attempts after every restart.

If password login triggers risk control, QR fallback can be used:

```env
LOGIN_FALLBACK=qrcode
```

## Captcha Fails

Point-click captcha is intentionally conservative. It may refresh low-confidence images instead of clicking.

Useful offline replay command:

```bash
python3 -m captcha_solver.tools.replay_point_click --summary-only --newest-first --limit 12
```

Captcha samples are stored under `data/captcha_samples/` and must stay private.

## Website Layout Changed

95598 is a website automation target, so page changes can break selectors or Vue-state parsing.

Use the frontend probe when login works but balance, usage, or monthly bills stop parsing:

```bash
docker compose exec ha-95598 python3 -m scripts.tools.probe_frontend_state
```

If you already know the target user ID and want to skip user-list parsing:

```bash
docker compose exec ha-95598 python3 -m scripts.tools.probe_frontend_state --skip-user-list --user-id USER_ID_PLACEHOLDER
```

The probe writes summaries under `data/pages/`:

- `probe_balance_*`
- `probe_usage_*`
- `probe_bill_summary_*`
- `probe_bill_detail_*`

These files are local diagnostics and can include private page data. Do not commit or share them.

## No New Daily Data

95598 can delay daily usage, TOU, or charge data. A delayed daily charge is not always a fetch failure.

Check the fetch status sensor attributes:

- `latest_daily_date`
- `source_delay_days`
- `stage`
- `error_type`

## Home Assistant Does Not Update

Check:

- `MQTT_HOST` points to a reachable broker.
- Home Assistant MQTT integration is enabled.
- MQTT discovery prefix matches `MQTT_DISCOVERY_PREFIX`.
- The entity ID suffix uses the last four digits of the user ID, but HA can append extra suffixes on conflicts.

History sensors publish large attributes. Excluding them from recorder is recommended.

## Energy Panel Dates Look Wrong

MQTT updates current totals. If several delayed days arrive at once, Home Assistant Energy can assign the difference to the catch-up day.

Enable recorder backfill when you need daily alignment:

```env
HA_ENERGY_BACKFILL_ENABLED=true
HA_RECORDER_DB_PATH=/ha-config/home-assistant_v2.db
```

Use `HA_ENERGY_BACKFILL_BACKUP=true` the first time.

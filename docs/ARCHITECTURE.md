# Architecture

This project is a small long-running service. It logs in to 95598 with a real browser, fetches electricity data, stores local history, and publishes Home Assistant sensors through MQTT.

## Data Flow

```text
95598 website
  -> Selenium browser
  -> fetch workflow
  -> SQLite + cache
  -> Home Assistant MQTT sensors
  -> optional HA recorder backfill
```

## Main Modules

| Area | Files | Responsibility |
| --- | --- | --- |
| Runtime entry | `scripts/main.py` | Load config, start scheduler, run startup/republish tasks |
| Browser/login | `scripts/support/browser_factory.py`, `login_manager.py`, `session_manager.py`, `scripts/pages/login_selectors.py` | Chromium, password login, QR fallback, session reuse |
| Navigation | `scripts/support/ha95598_navigator.py`, `scripts/pages/` | Open 95598 pages and switch bound user IDs |
| Fetching | `scripts/fetchers/` | Balance, usage history, monthly bill details, date-range backfill |
| Workflow | `scripts/support/fetch_workflow.py` | Orchestrate one user refresh and progress stages |
| Persistence | `scripts/support/db.py`, `data_persister.py`, `monthly_billing.py` | SQLite writes, official bill priority, calculated fallback |
| Home Assistant | `scripts/sensor_updater.py`, `ha_mqtt_publisher.py`, `mqtt_publisher.py`, `ha_payloads.py` | MQTT connection, HA Discovery, sensor state publishing, history attributes |
| Runtime cache | `scripts/support/cache_store.py`, `user_state.py`, `user_state_cache.py` | Fetch progress and typed user-state cache snapshots |
| Maintenance | `scripts/tools/` | Privacy checks, config checks, local diagnostics |

## Stability Rules

- Login, captcha solving, and session reuse are intentionally changed slowly.
- Monthly bills use official 95598 bill data first; calculated daily totals are only a fallback.
- Daily history is trend data. HA Energy panel correction uses recorder backfill when enabled.
- Runtime files under `data/` are private and must not be committed.

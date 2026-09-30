# Runtime

## Startup

On startup the service:

1. Loads environment variables.
2. Initializes logging, SQLite, cache, notifier, and scheduler.
3. Republishes cached Home Assistant state when available.
4. Waits for the scheduled run unless `FETCH_ON_STARTUP=true`.

`FETCH_ON_STARTUP=false` is recommended for unattended installs because container restarts should not cause extra login attempts.

## Scheduled Fetch

Each run handles every visible 95598 user ID unless it is listed in `IGNORE_USER_ID`.

For each user, progress is saved in cache with these stages:

```text
none -> balance -> yearly -> monthly -> daily -> tou -> persist -> billing -> complete
```

If a run is interrupted and restarted on the same day, completed stages can be skipped and cached data can be reused.

Each fetch attempt is limited by `FETCH_ATTEMPT_TIMEOUT_MINUTES` (default `30`). A timed-out attempt follows the normal retry path. Docker Compose also checks a scheduler heartbeat and marks the container unhealthy if the main loop remains blocked for too long.

## Local State

Runtime state is stored in `data/`:

| Path | Purpose |
| --- | --- |
| `homeassistant.db` | Local SQLite history |
| `ha_95598_cache.json` | Latest published state and progress |
| `ha_95598_session.json` | Login session |
| `chrome-profile/` | Optional persistent Chromium profile |
| `pages/` | Error snapshots and debug traces |
| `captcha_samples/` | Local captcha learning samples |

Chromium keeps cookies and device state in its profile, while disposable cache files are capped by `BROWSER_PROFILE_CACHE_MAX_MB` (default `128`). Normal page screenshots are not stored unless `PAGE_TRACE_MODE=all`; the default `errors` mode records failure context only.

These files can contain private data. They are ignored by git and should not be shared.

## Failure Recovery

- MQTT publishes stop waiting after `MQTT_PUBLISH_TIMEOUT_SECONDS` and do not delete local history.
- A scheduled run that exhausts all retries publishes a failed fetch status from cached user state.
- Login/session failures are retried by the configured login flow.
- Captcha failures can refresh and retry before falling back.
- If 95598 delays daily charge or TOU data, the next successful run can fill missing local rows.
- HA recorder backfill can correct Energy panel dates after delayed data is restored.

## Diagnostics

Run safe onboarding checks:

```bash
python3 scripts/tools/config_doctor.py --all
```

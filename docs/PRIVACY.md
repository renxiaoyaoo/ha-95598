# Privacy

This project handles private electricity account data. Treat the repository as public and runtime files as private.

## Do Not Commit

- `.env`
- `data/`
- SQLite databases
- browser sessions and profiles
- QR code images
- screenshots and HTML traces
- captcha samples and replay reports
- local tariff override files such as `config/tou_price_config.local.json`

## Safe Examples

Use placeholders in docs and tests:

```env
ACCOUNT="account@example.com"
PASSWORD="password1"
MQTT_HOST="host.docker.internal"
```

Use masked user IDs in logs and examples:

```text
***1234
```

## Required Checks

Before committing:

```bash
python3 scripts/tools/privacy_check.py
python3 scripts/tools/privacy_check.py --staged
python3 scripts/tools/syntax_check.py
```

`config_doctor.py` is also safe to run because it prints summaries instead of private values:

```bash
python3 scripts/tools/config_doctor.py --all
```

## Logging

Logs should not print full account IDs, phone numbers, passwords, tokens, session cookies, QR image contents, database contents, or `.env` values.

Runtime diagnostics under `data/pages/` can still contain private screenshots and page state. Full page HTML error traces are disabled by default; only enable `DEBUG_ERROR_TRACE_DETAIL=true` for short local debugging sessions.

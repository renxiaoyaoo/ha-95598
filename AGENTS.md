# Repository Instructions

## Privacy Gate

- Run `python3 scripts/tools/privacy_check.py --staged` before every commit.
- Do not commit `.env`, `data/`, databases, screenshots, session files, QR codes, local price overrides, or real Home Assistant / 95598 / Telegram credentials.
- Examples, tests, and docs must use placeholders only.
- If a possible secret is found, report only the file path, line number, and risk type. Do not print the value.

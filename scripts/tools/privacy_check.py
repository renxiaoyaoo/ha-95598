from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
TG_TOKEN_RE = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PASSWORD_VALUE_RE = re.compile(r"(?i)(password|passwd|pwd)[\"']?\s*[:=]\s*[\"']([^\"'\s#]{8,})[\"']")

SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "invalid.local"}
SAFE_VALUES = {
    "password",
    "password1",
    "password2",
    "your-password",
    "your_password",
    "yourpassword",
    "secret",
    "xxxxxxxx",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".db", ".sqlite", ".pyc", ".zip", ".tar", ".gz",
}


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)


def tracked_files() -> list[Path]:
    return [ROOT / line for line in run_git(["ls-files"]).splitlines() if line.strip()]


def staged_files() -> list[Path]:
    output = run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    return [ROOT / line for line in output.splitlines() if line.strip()]


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    try:
        path.read_text(encoding="utf-8")
        return True
    except (UnicodeDecodeError, FileNotFoundError):
        return False


def safe_email(value: str) -> bool:
    domain = value.rsplit("@", 1)[-1].lower()
    local = value.split("@", 1)[0].lower()
    return domain in SAFE_EMAIL_DOMAINS or local in {"account", "user", "your-account", "your_account"}


def safe_secret_value(value: str) -> bool:
    lower = value.lower()
    return lower in SAFE_VALUES or "password" in lower or lower.startswith("your") or lower.startswith("xxx") or lower.startswith("你的") or lower.startswith("密码")


def scan_line(line: str) -> list[str]:
    findings: list[str] = []
    if PHONE_RE.search(line):
        findings.append("mainland_phone")
    if TG_TOKEN_RE.search(line):
        findings.append("telegram_bot_token")
    if PRIVATE_KEY_RE.search(line):
        findings.append("private_key")
    for match in EMAIL_RE.finditer(line):
        if not safe_email(match.group(0)):
            findings.append("email")
    for match in PASSWORD_VALUE_RE.finditer(line):
        if not safe_secret_value(match.group(2)):
            findings.append("password_value")
    return findings


def scan_file(path: Path) -> list[tuple[str, int]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    findings: list[tuple[str, int]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind in scan_line(line):
            findings.append((kind, line_no))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tracked project files for likely private credentials before commit.")
    parser.add_argument("--staged", action="store_true", help="Scan only staged files.")
    args = parser.parse_args()

    failed = False
    files = staged_files() if args.staged else tracked_files()
    for path in files:
        if not is_text_file(path):
            continue
        for kind, line_no in scan_file(path):
            failed = True
            print(f"{path.relative_to(ROOT)}:{line_no}: possible {kind}")

    if failed:
        print("privacy check failed: remove secrets or add a narrowly justified allowlist entry")
        return 1
    print("privacy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

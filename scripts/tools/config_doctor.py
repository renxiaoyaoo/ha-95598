from __future__ import annotations

import argparse
import contextlib
import io
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tools import check_local_tariff, privacy_check, syntax_check


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str = ""


def _run_privacy_check(staged: bool) -> DoctorCheck:
    files = privacy_check.staged_files() if staged else privacy_check.tracked_files()
    failed = False
    for path in files:
        if not privacy_check.is_text_file(path):
            continue
        if privacy_check.scan_file(path):
            failed = True
    label = "privacy staged" if staged else "privacy tracked"
    return DoctorCheck(label, not failed)


def _run_syntax_check() -> DoctorCheck:
    with contextlib.redirect_stdout(io.StringIO()):
        ok = syntax_check.main() == 0
    return DoctorCheck("python syntax", ok)


def _run_tariff_check() -> DoctorCheck:
    config_path = check_local_tariff.resolve_config_path()
    result = check_local_tariff.check_tariff_config(config_path)
    return DoctorCheck("tariff config", result.ok, config_path.name)


def _read_env_keys(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        values[key] = value.strip().strip("\"'")
    return values


def _run_env_check(root: Path = ROOT) -> DoctorCheck:
    env_path = root / ".env"
    if not env_path.exists():
        return DoctorCheck("runtime env", False, ".env missing")

    values = _read_env_keys(env_path)
    has_credential_pool = bool(values.get("LOGIN_CREDENTIALS"))
    missing = []
    if not has_credential_pool:
        for key in ("ACCOUNT", "PASSWORD"):
            if not values.get(key):
                missing.append(key)

    if missing:
        return DoctorCheck("runtime env", False, "missing " + ",".join(missing))

    if not values.get("MQTT_HOST"):
        return DoctorCheck("runtime env", True, "mqtt disabled")
    return DoctorCheck("runtime env", True)


def _run_compose_check() -> DoctorCheck:
    try:
        subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return DoctorCheck("docker compose", True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        return DoctorCheck("docker compose", False, type(exc).__name__)


def _print_result(check: DoctorCheck) -> None:
    status = "ok" if check.ok else "failed"
    suffix = f" ({check.detail})" if check.detail else ""
    print(f"{status}: {check.name}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run safe local project checks without printing private config values.")
    parser.add_argument("--staged", action="store_true", help="Also check staged files for privacy risks.")
    parser.add_argument("--compose", action="store_true", help="Also validate docker compose with config --quiet.")
    parser.add_argument("--env", action="store_true", help="Also check .env presence and required keys without printing values.")
    parser.add_argument("--all", "--doctor-all", action="store_true", help="Run the standard onboarding checks.")
    args = parser.parse_args()

    checks = [
        _run_privacy_check(staged=False),
        _run_syntax_check(),
        _run_tariff_check(),
    ]
    if args.all or args.env:
        checks.append(_run_env_check())
    if args.staged:
        checks.append(_run_privacy_check(staged=True))
    if args.all or args.compose:
        checks.append(_run_compose_check())

    for check in checks:
        _print_result(check)

    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

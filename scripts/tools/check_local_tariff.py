from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = "config/tou_price_config.json"


@dataclass
class CheckResult:
    ok: bool
    messages: list[str]


def _read_dotenv_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip().strip('"').strip("'")
        return value or None
    return None


def resolve_config_path(config_path: str | None = None) -> Path:
    value = config_path or os.getenv("TOU_PRICE_CONFIG") or _read_dotenv_value(ROOT / ".env", "TOU_PRICE_CONFIG") or DEFAULT_CONFIG
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def git_ignore_state(path: Path) -> str:
    if not (ROOT / ".git").exists():
        return "unknown"
    try:
        subprocess.run(
            ["git", "check-ignore", "--quiet", str(path.relative_to(ROOT))],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return "true"
    except Exception:
        return "false"


def _validate_rule(rule: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    name = rule.get("name") or "<unnamed>"
    months = rule.get("months")
    if not isinstance(months, list) or not months:
        errors.append(f"{name}: months must be a non-empty list")
    else:
        invalid_months = [month for month in months if not isinstance(month, int) or month < 1 or month > 12]
        if invalid_months:
            errors.append(f"{name}: months contain invalid values")

    tiers = rule.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        errors.append(f"{name}: tiers must be a non-empty list")
        return errors

    previous_limit: float | None = None
    for index, tier in enumerate(tiers, start=1):
        if not isinstance(tier, dict):
            errors.append(f"{name}: tier #{index} must be an object")
            continue
        limit = tier.get("up_to")
        if limit is not None:
            try:
                limit_value = float(limit)
            except (TypeError, ValueError):
                errors.append(f"{name}: tier #{index} up_to must be numeric or null")
                continue
            if previous_limit is not None and limit_value <= previous_limit:
                errors.append(f"{name}: tier limits must be strictly increasing")
            previous_limit = limit_value
        elif index != len(tiers):
            errors.append(f"{name}: only the last tier can use null up_to")

        rates = tier.get("rates")
        if not isinstance(rates, dict):
            errors.append(f"{name}: tier #{index} rates must be an object")
            continue
        for rate_name in ("valley", "flat", "peak", "tip"):
            try:
                float(rates[rate_name])
            except (KeyError, TypeError, ValueError):
                errors.append(f"{name}: tier #{index} missing numeric {rate_name} rate")
    return errors


def check_tariff_config(config_path: Path) -> CheckResult:
    messages: list[str] = []
    if not config_path.exists():
        return CheckResult(False, [f"config file not found: {config_path.name}"])

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return CheckResult(False, [f"config JSON parse failed: {type(exc).__name__}"])

    versions = data.get("versions")
    if not isinstance(versions, list) or not versions:
        return CheckResult(False, ["versions must be a non-empty list"])

    first = versions[0]
    if not isinstance(first, dict):
        return CheckResult(False, ["first version must be an object"])

    version_name = first.get("version") or "<unnamed>"
    messages.append(f"config_file={config_path.name}")
    messages.append(f"git_ignored={git_ignore_state(config_path)}")
    messages.append(f"first_version={version_name}")
    messages.append(f"validfrom={first.get('validfrom')}")

    rules = first.get("season_rules")
    if not isinstance(rules, list) or not rules:
        return CheckResult(False, messages + ["season_rules must be a non-empty list"])

    errors: list[str] = []
    covered_months: list[int] = []
    for rule in rules:
        if not isinstance(rule, dict):
            errors.append("season rule must be an object")
            continue
        errors.extend(_validate_rule(rule))
        covered_months.extend(month for month in rule.get("months", []) if isinstance(month, int))
        thresholds = [tier.get("up_to") for tier in rule.get("tiers", []) if isinstance(tier, dict)]
        messages.append(f"rule={rule.get('name')} months={rule.get('months')} thresholds={thresholds}")

    duplicate_months = sorted({month for month in covered_months if covered_months.count(month) > 1})
    missing_months = [month for month in range(1, 13) if month not in covered_months]
    if duplicate_months:
        errors.append("months are duplicated across rules")
    if missing_months:
        errors.append("months are not fully covered")

    return CheckResult(not errors, messages + errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the active TOU tariff config without printing private env values.")
    parser.add_argument("--config", help="Override TOU price config path.")
    args = parser.parse_args()

    result = check_tariff_config(resolve_config_path(args.config))
    for message in result.messages:
        print(message)
    print("local tariff check passed" if result.ok else "local tariff check failed")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

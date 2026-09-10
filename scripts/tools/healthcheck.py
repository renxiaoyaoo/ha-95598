from __future__ import annotations

import os
import time
from pathlib import Path


HEARTBEAT_PATH = Path("/tmp/ha95598_scheduler_heartbeat")


def heartbeat_is_fresh(path: Path, *, max_age_seconds: int, now: float | None = None) -> bool:
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        return False
    current_time = time.time() if now is None else now
    return 0 <= current_time - modified_at <= max_age_seconds


def main() -> int:
    try:
        max_age_seconds = max(int(os.getenv("SCHEDULER_HEARTBEAT_MAX_AGE_SECONDS", "2700")), 1)
    except ValueError:
        return 1
    return 0 if heartbeat_is_fresh(HEARTBEAT_PATH, max_age_seconds=max_age_seconds) else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ["scripts", "captcha_solver", "tests"]


def main() -> int:
    failed = False
    for scan_dir in SCAN_DIRS:
        for path in sorted((ROOT / scan_dir).rglob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
            except SyntaxError as exc:
                failed = True
                print(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
    if failed:
        return 1
    print("syntax check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

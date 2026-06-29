import argparse
import json
import re
from pathlib import Path

from PIL import Image

from captcha_solver.image import PointClickImageSolver


def replay_pair(answer_path: Path, bg_path: Path, output_dir: Path | None = None) -> dict:
    solver = PointClickImageSolver()
    answer_image = Image.open(answer_path).convert("RGB")
    bg_image = Image.open(bg_path).convert("RGB")
    solutions = solver.ranked_solutions_from_images(answer_image, bg_image, limit=3)
    report = solver.get_last_diagnostics()
    report["answer_path"] = str(answer_path)
    report["background_path"] = str(bg_path)
    report["solution_count"] = len(solutions)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{answer_path.stem}.report.json"
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(output_path)
    return report


def discover_pairs(trace_dir: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    seen: set[tuple[Path, Path]] = set()

    def add_pair(answer_path: Path, bg_path: Path) -> None:
        key = (answer_path.resolve(), bg_path.resolve())
        if bg_path.exists() and key not in seen:
            seen.add(key)
            pairs.append((answer_path, bg_path))

    # Legacy trace files saved directly under data/pages/.
    legacy_pattern = re.compile(r"^tencent_point_click_answer_(.+)\.png$")
    for answer_path in sorted(trace_dir.rglob("tencent_point_click_answer_*.png")):
        match = legacy_pattern.match(answer_path.name)
        if not match:
            continue
        suffix = match.group(1)
        add_pair(answer_path, answer_path.with_name(f"tencent_point_click_bg_{suffix}.png"))

    # Learning samples saved under data/captcha_samples/{success,failed_click,rejected}/.
    for answer_path in sorted(trace_dir.rglob("*_answer.png")):
        bg_path = answer_path.with_name(answer_path.name.removesuffix("_answer.png") + "_bg.png")
        add_pair(answer_path, bg_path)

    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay saved point-click captcha samples without opening a browser."
    )
    parser.add_argument("--answer", type=Path, help="Path to tencent_point_click_answer_*.png")
    parser.add_argument("--background", "--bg", dest="background", type=Path, help="Path to tencent_point_click_bg_*.png")
    parser.add_argument("--trace-dir", type=Path, default=Path("data/captcha_samples"), help="Directory to scan for saved samples")
    parser.add_argument("--output-dir", type=Path, default=Path("data/captcha_samples/replay_reports"), help="Directory for JSON reports")
    parser.add_argument("--summary-only", action="store_true", help="Print one compact line per sample")
    args = parser.parse_args()

    if args.answer or args.background:
        if not args.answer or not args.background:
            parser.error("--answer and --background must be used together")
        pairs = [(args.answer, args.background)]
    else:
        pairs = discover_pairs(args.trace_dir)

    if not pairs:
        print(f"No point-click samples found in {args.trace_dir}")
        return 1

    for answer_path, bg_path in pairs:
        report = replay_pair(answer_path, bg_path, args.output_dir)
        if args.summary_only:
            print(
                f"{answer_path.name}: accepted={report.get('accepted')} "
                f"targets={report.get('target_count')} candidates={report.get('candidate_count')} "
                f"solutions={report.get('solution_count')} reason={report.get('rejection_reason')}"
            )
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
import re
from pathlib import Path

from PIL import Image

from captcha_solver.image import PointClickImageSolver


def replay_pair(
    answer_path: Path,
    bg_path: Path,
    output_dir: Path | None = None,
    *,
    min_average_score: float | None = None,
    min_point_score: float | None = None,
    min_score_gap: float | None = None,
) -> dict:
    solver = PointClickImageSolver()
    answer_image = Image.open(answer_path).convert("RGB")
    bg_image = Image.open(bg_path).convert("RGB")
    kwargs = {
        key: value
        for key, value in {
            "min_average_score": min_average_score,
            "min_point_score": min_point_score,
            "min_score_gap": min_score_gap,
        }.items()
        if value is not None
    }
    solutions = solver.ranked_solutions_from_images(answer_image, bg_image, limit=3, **kwargs)
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


def discover_pairs(trace_dir: Path, newest_first: bool = False, limit: int | None = None) -> list[tuple[Path, Path]]:
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

    pairs.sort(key=lambda pair: pair[0].stat().st_mtime, reverse=newest_first)
    return pairs[:limit] if limit else pairs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay saved point-click captcha samples without opening a browser."
    )
    parser.add_argument("--answer", type=Path, help="Path to tencent_point_click_answer_*.png")
    parser.add_argument("--background", "--bg", dest="background", type=Path, help="Path to tencent_point_click_bg_*.png")
    parser.add_argument("--trace-dir", type=Path, default=Path("data/captcha_samples"), help="Directory to scan for saved samples")
    parser.add_argument("--output-dir", type=Path, default=Path("data/captcha_samples/replay_reports"), help="Directory for JSON reports")
    parser.add_argument("--summary-only", action="store_true", help="Print one compact line per sample")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of discovered samples to replay")
    parser.add_argument("--newest-first", action="store_true", help="Replay newest discovered samples first")
    parser.add_argument("--min-average-score", type=float, help="Override solver minimum average score")
    parser.add_argument("--min-point-score", type=float, help="Override solver minimum per-point score")
    parser.add_argument("--min-score-gap", type=float, help="Override solver minimum global score gap")
    args = parser.parse_args()

    if args.answer or args.background:
        if not args.answer or not args.background:
            parser.error("--answer and --background must be used together")
        pairs = [(args.answer, args.background)]
    else:
        pairs = discover_pairs(args.trace_dir, newest_first=args.newest_first, limit=args.limit or None)

    if not pairs:
        print(f"No point-click samples found in {args.trace_dir}")
        return 1

    for answer_path, bg_path in pairs:
        report = replay_pair(
            answer_path,
            bg_path,
            args.output_dir,
            min_average_score=args.min_average_score,
            min_point_score=args.min_point_score,
            min_score_gap=args.min_score_gap,
        )
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

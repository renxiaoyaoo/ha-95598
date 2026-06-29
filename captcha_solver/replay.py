import json
import logging
import os
from datetime import date
from pathlib import Path

from captcha_solver.learning import CaptchaLearningStore
from captcha_solver.tools.replay_point_click import discover_pairs, replay_pair


def auto_replay_once(data_dir: Path) -> None:
    """Run local captcha replay maintenance when explicitly enabled.

    This is intentionally opt-in because most users do not need background
    replay work. It never opens a browser or makes network requests.
    """

    if os.getenv("CAPTCHA_AUTO_REPLAY", "false").lower() != "true":
        return

    sample_dir = data_dir / "captcha_samples"
    state_path = sample_dir / "auto_replay_state.json"
    today = date.today().isoformat()
    if _already_ran_today(state_path, today):
        return

    trace_dir = sample_dir
    output_dir = sample_dir / "replay_reports"
    pairs = discover_pairs(trace_dir)
    pairs.sort(key=lambda pair: pair[0].stat().st_mtime)
    sample_limit = int(os.getenv("CAPTCHA_AUTO_REPLAY_SAMPLE_LIMIT", "80"))
    if sample_limit > 0 and len(pairs) > sample_limit:
        pairs = pairs[-sample_limit:]
    summary = {
        "date": today,
        "trace_dir": str(trace_dir),
        "sample_count": len(pairs),
        "sample_limit": sample_limit,
        "accepted_count": 0,
        "rejected_count": 0,
        "rejection_reasons": {},
        "reports": [],
    }

    for answer_path, bg_path in pairs:
        try:
            report = replay_pair(answer_path, bg_path, output_dir)
            if report.get("accepted"):
                summary["accepted_count"] += 1
            else:
                summary["rejected_count"] += 1
                reason = report.get("rejection_reason") or "unknown"
                summary["rejection_reasons"][reason] = summary["rejection_reasons"].get(reason, 0) + 1
            summary["reports"].append(
                {
                    "answer_path": report.get("answer_path"),
                    "background_path": report.get("background_path"),
                    "accepted": report.get("accepted"),
                    "solution_count": report.get("solution_count"),
                    "rejection_reason": report.get("rejection_reason"),
                    "report_path": report.get("report_path"),
                }
            )
        except Exception as exc:
            logging.info("Captcha auto replay failed for %s: %s", answer_path, exc)

    sample_dir.mkdir(parents=True, exist_ok=True)
    summary_path = sample_dir / "replay_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    learning_store = CaptchaLearningStore(sample_dir)
    learning_state = learning_store._load_state()
    learning_state["last_auto_replay"] = summary
    learning_state["thresholds"] = learning_store._thresholds_from_state(learning_state)
    learning_store.state_path.write_text(json.dumps(learning_state, ensure_ascii=False, indent=2), encoding="utf-8")
    state_path.write_text(json.dumps({"last_run_date": today}, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info(
        "Captcha auto replay completed: samples=%s accepted=%s rejected=%s",
        summary["sample_count"],
        summary["accepted_count"],
        summary["rejected_count"],
    )


def _already_ran_today(state_path: Path, today: str) -> bool:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return state.get("last_run_date") == today
    except Exception:
        return False

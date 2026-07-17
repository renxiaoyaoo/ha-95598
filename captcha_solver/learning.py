import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path


class CaptchaLearningStore:
    """Persist weak-supervision samples and derive conservative thresholds.

    The store intentionally does not require manual labels. Online outcomes are
    used as weak labels:
    - success: the chosen points completed the captcha/login flow.
    - failure: the chosen points did not complete the captcha/login flow.
    - rejected: the solver refused to click because confidence was too low.
    """

    DEFAULT_THRESHOLDS = {
        "min_average_score": 0.38,
        "min_point_score": 0.18,
        "min_score_gap": 0.001,
    }
    MIN_FAILURE_SAMPLES_FOR_TIGHTENING = 5
    SUCCESS_MARGIN = 0.04

    def __init__(self, sample_dir: Path):
        self.sample_dir = sample_dir
        self.state_path = sample_dir / "learning_state.json"

    def thresholds(self) -> dict:
        state = self._load_state()
        return self._thresholds_from_state(state)

    def _thresholds_from_state(self, state: dict) -> dict:
        thresholds = dict(self.DEFAULT_THRESHOLDS)
        success_scores = [
            item.get("average_score")
            for item in state.get("successes", [])
            if isinstance(item.get("average_score"), (int, float))
        ]
        success_point_scores = [
            item.get("min_point_score")
            for item in state.get("successes", [])
            if isinstance(item.get("min_point_score"), (int, float))
        ]
        failure_scores = [
            item.get("average_score")
            for item in state.get("failed_clicks", [])
            if isinstance(item.get("average_score"), (int, float))
        ]
        failure_point_scores = [
            item.get("min_point_score")
            for item in state.get("failed_clicks", [])
            if isinstance(item.get("min_point_score"), (int, float))
        ]

        if os.getenv("CAPTCHA_LEARNING_TIGHTEN_ON_FAILURE", "false").lower() == "true":
            if len(failure_scores) >= self.MIN_FAILURE_SAMPLES_FOR_TIGHTENING:
                thresholds["min_average_score"] = min(max(thresholds["min_average_score"], max(failure_scores) + 0.02), 0.55)
            if len(failure_point_scores) >= self.MIN_FAILURE_SAMPLES_FOR_TIGHTENING:
                thresholds["min_point_score"] = min(max(thresholds["min_point_score"], max(failure_point_scores) + 0.02), 0.45)

        if success_scores:
            success_cap = max(0.32, min(success_scores) - 0.08)
            thresholds["min_average_score"] = min(thresholds["min_average_score"], success_cap)
        if success_point_scores:
            point_cap = max(0.12, min(success_point_scores) - 0.08)
            thresholds["min_point_score"] = min(thresholds["min_point_score"], point_cap)

        env_map = {
            "min_average_score": "CAPTCHA_MIN_AVERAGE_SCORE",
            "min_point_score": "CAPTCHA_MIN_POINT_SCORE",
            "min_score_gap": "CAPTCHA_MIN_SCORE_GAP",
        }
        for key, env_name in env_map.items():
            raw = os.getenv(env_name)
            if raw not in (None, ""):
                try:
                    thresholds[key] = float(raw)
                except ValueError:
                    logging.warning("Ignore invalid %s=%s", env_name, raw)
        return thresholds

    def record(self, outcome: str, answer_image, bg_image, diagnostics: dict, suffix: str) -> None:
        try:
            self.sample_dir.mkdir(parents=True, exist_ok=True)
            self.prune_artifacts()
            outcome_dir = self.sample_dir / outcome
            outcome_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            prefix = f"{timestamp}_{suffix}"
            answer_path = outcome_dir / f"{prefix}_answer.png"
            bg_path = outcome_dir / f"{prefix}_bg.png"
            report_path = outcome_dir / f"{prefix}_report.json"
            answer_image.save(answer_path)
            bg_image.save(bg_path)
            report = dict(diagnostics or {})
            report["outcome"] = outcome
            report["saved_at"] = datetime.now().isoformat()
            report["answer_path"] = str(answer_path)
            report["background_path"] = str(bg_path)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self._update_state(outcome, report)
            logging.info("Saved captcha learning sample to %s", report_path)
        except Exception as exc:
            logging.info("Failed to save captcha learning sample: %s", exc)

    def prune_artifacts(self) -> None:
        """Keep local captcha samples useful without letting data/ grow forever."""
        for outcome in ("success", "failed_click", "rejected"):
            self._prune_files(
                self.sample_dir / outcome,
                retention_days=_env_int("CAPTCHA_SAMPLE_RETENTION_DAYS", 14),
                max_files=_env_int("CAPTCHA_SAMPLE_MAX_FILES_PER_OUTCOME", 1500),
            )
        self._prune_files(
            self.sample_dir / "replay_reports",
            retention_days=_env_int("CAPTCHA_REPLAY_REPORT_RETENTION_DAYS", 14),
            max_files=_env_int("CAPTCHA_REPLAY_REPORT_MAX_FILES", 500),
        )

    @staticmethod
    def _prune_files(directory: Path, *, retention_days: int, max_files: int) -> None:
        if not directory.exists():
            return
        files = [path for path in directory.rglob("*") if path.is_file()]
        if not files:
            return

        to_delete: set[Path] = set()
        if retention_days > 0:
            cutoff = datetime.now() - timedelta(days=retention_days)
            for path in files:
                try:
                    if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                        to_delete.add(path)
                except Exception:
                    continue

        if max_files > 0:
            remaining = [path for path in files if path not in to_delete]
            remaining.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            to_delete.update(remaining[max_files:])

        for path in to_delete:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                continue

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {"successes": [], "failed_clicks": [], "rejections": []}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"successes": [], "failed_clicks": [], "rejections": []}

    def _update_state(self, outcome: str, report: dict) -> None:
        state = self._load_state()
        state.setdefault("successes", [])
        state.setdefault("failed_clicks", [])
        state.setdefault("rejections", [])

        accepted_solution = (report.get("solutions") or [{}])[0]
        summary = {
            "saved_at": report.get("saved_at"),
            "average_score": accepted_solution.get("average_score"),
            "min_point_score": accepted_solution.get("min_point_score"),
            "target_count": report.get("target_count"),
            "candidate_count": report.get("candidate_count"),
            "rejection_reason": report.get("rejection_reason"),
        }
        if outcome == "success":
            state["successes"].append(summary)
        elif outcome == "failed_click":
            state["failed_clicks"].append(summary)
        else:
            state["rejections"].append(summary)

        for key in ("successes", "failed_clicks", "rejections"):
            state[key] = state[key][-200:]
        state["thresholds"] = self._thresholds_from_state(state)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

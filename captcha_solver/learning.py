import json
import logging
from datetime import datetime
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
        "min_average_score": 0.42,
        "min_point_score": 0.20,
        "min_score_gap": 0.005,
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

        if len(failure_scores) >= self.MIN_FAILURE_SAMPLES_FOR_TIGHTENING:
            thresholds["min_average_score"] = min(max(thresholds["min_average_score"], max(failure_scores) + 0.02), 0.72)
        if len(failure_point_scores) >= self.MIN_FAILURE_SAMPLES_FOR_TIGHTENING:
            thresholds["min_point_score"] = min(max(thresholds["min_point_score"], max(failure_point_scores) + 0.02), 0.55)

        if success_scores:
            success_cap = max(self.DEFAULT_THRESHOLDS["min_average_score"], min(success_scores) - self.SUCCESS_MARGIN)
            thresholds["min_average_score"] = min(thresholds["min_average_score"], success_cap)
        if success_point_scores:
            point_cap = max(self.DEFAULT_THRESHOLDS["min_point_score"], min(success_point_scores) - self.SUCCESS_MARGIN)
            thresholds["min_point_score"] = min(thresholds["min_point_score"], point_cap)
        return thresholds

    def record(self, outcome: str, answer_image, bg_image, diagnostics: dict, suffix: str) -> None:
        try:
            self.sample_dir.mkdir(parents=True, exist_ok=True)
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

from __future__ import annotations

FETCH_STAGES = ("none", "balance", "yearly", "monthly", "daily", "tou", "persist", "billing", "complete")
FETCH_STAGE_ORDER = {stage: index for index, stage in enumerate(FETCH_STAGES)}


def has_completed_stage(progress: dict | None, stage: str) -> bool:
    current_stage = (progress or {}).get("stage", "none")
    return FETCH_STAGE_ORDER.get(current_stage, 0) >= FETCH_STAGE_ORDER.get(stage, 0)


def is_progress_complete(progress: dict | None) -> bool:
    return isinstance(progress, dict) and progress.get("stage") == "complete"

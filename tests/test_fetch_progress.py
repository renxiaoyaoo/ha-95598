from scripts.support.fetch_progress import FETCH_STAGES, has_completed_stage, is_progress_complete


def test_fetch_stages_keep_expected_order():
    assert FETCH_STAGES == ("none", "balance", "yearly", "monthly", "daily", "tou", "persist", "billing", "complete")


def test_has_completed_stage_uses_stage_order():
    assert has_completed_stage({"stage": "daily"}, "monthly") is True
    assert has_completed_stage({"stage": "monthly"}, "daily") is False
    assert has_completed_stage({}, "balance") is False


def test_is_progress_complete_requires_complete_stage():
    assert is_progress_complete({"stage": "complete"}) is True
    assert is_progress_complete({"stage": "billing"}) is False
    assert is_progress_complete(None) is False

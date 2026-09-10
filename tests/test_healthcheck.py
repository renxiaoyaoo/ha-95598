from scripts.tools.healthcheck import heartbeat_is_fresh


def test_heartbeat_is_fresh_with_recent_file(tmp_path) -> None:
    path = tmp_path / "heartbeat"
    path.touch()
    modified_at = path.stat().st_mtime

    assert heartbeat_is_fresh(path, max_age_seconds=60, now=modified_at + 30)
    assert not heartbeat_is_fresh(path, max_age_seconds=60, now=modified_at + 61)


def test_missing_heartbeat_is_unhealthy(tmp_path) -> None:
    assert not heartbeat_is_fresh(tmp_path / "missing", max_age_seconds=60)

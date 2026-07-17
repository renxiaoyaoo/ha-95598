import os
import time

from captcha_solver.learning import CaptchaLearningStore


def test_captcha_artifact_pruning_keeps_newest_files(tmp_path, monkeypatch) -> None:
    sample_dir = tmp_path / "captcha_samples"
    failed_dir = sample_dir / "failed_click"
    failed_dir.mkdir(parents=True)
    old_file = failed_dir / "old_report.json"
    mid_file = failed_dir / "mid_report.json"
    new_file = failed_dir / "new_report.json"
    for path in (old_file, mid_file, new_file):
        path.write_text("{}", encoding="utf-8")

    now = time.time()
    os.utime(old_file, (now - 30 * 86400, now - 30 * 86400))
    os.utime(mid_file, (now - 60, now - 60))
    os.utime(new_file, (now, now))

    monkeypatch.setenv("CAPTCHA_SAMPLE_RETENTION_DAYS", "14")
    monkeypatch.setenv("CAPTCHA_SAMPLE_MAX_FILES_PER_OUTCOME", "1")

    CaptchaLearningStore(sample_dir).prune_artifacts()

    assert not old_file.exists()
    assert not mid_file.exists()
    assert new_file.exists()


def test_captcha_replay_report_pruning_uses_separate_limit(tmp_path, monkeypatch) -> None:
    sample_dir = tmp_path / "captcha_samples"
    report_dir = sample_dir / "replay_reports"
    report_dir.mkdir(parents=True)
    reports = [report_dir / f"report_{index}.json" for index in range(3)]
    for index, path in enumerate(reports):
        path.write_text("{}", encoding="utf-8")
        ts = time.time() + index
        os.utime(path, (ts, ts))

    monkeypatch.setenv("CAPTCHA_REPLAY_REPORT_RETENTION_DAYS", "0")
    monkeypatch.setenv("CAPTCHA_REPLAY_REPORT_MAX_FILES", "2")

    CaptchaLearningStore(sample_dir).prune_artifacts()

    assert not reports[0].exists()
    assert reports[1].exists()
    assert reports[2].exists()

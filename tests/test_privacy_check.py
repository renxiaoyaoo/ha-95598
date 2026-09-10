from pathlib import Path

from scripts.tools import privacy_check


def test_scan_path_rejects_private_binary_artifacts() -> None:
    assert privacy_check.scan_path(privacy_check.ROOT / "data" / "login_qr_code.png")
    assert privacy_check.scan_path(privacy_check.ROOT / "private.sqlite3")
    assert privacy_check.scan_path(privacy_check.ROOT / "docs" / "unreviewed.png")


def test_scan_path_allows_reviewed_public_examples() -> None:
    path = privacy_check.ROOT / "examples" / "energy-dashboard" / "daily-chart.png"

    assert privacy_check.scan_path(path) == []


def test_scan_path_handles_paths_outside_repository() -> None:
    assert privacy_check.scan_path(Path("/tmp/private.db")) == [("database_file", 0)]


def test_text_detection_still_scans_source_files(tmp_path) -> None:
    source = tmp_path / "example.py"
    source.write_text("value = 1\n", encoding="utf-8")

    assert privacy_check.is_text_file(source) is True


def test_scan_line_rejects_quoted_and_unquoted_password_values() -> None:
    key = "PASS" + "WORD"
    unsafe_value = "credential_" + "value_123"

    assert "password_value" in privacy_check.scan_line(f'{key}="{unsafe_value}"')
    assert "password_value" in privacy_check.scan_line(f"{key}={unsafe_value}")

from scripts.support.error_watcher import ErrorWatcher


class FakeDriver:
    current_url = "https://example.invalid/page"
    title = "Example"
    page_source = "<html>private</html>"

    def __init__(self):
        self.scripts = []

    def execute_script(self, script):
        self.scripts.append(script)
        return {}

    def get_log(self, log_type):
        return []

    def get_cookies(self):
        return []


def test_error_watcher_debug_state_does_not_collect_input_values():
    driver = FakeDriver()

    ErrorWatcher._collect_debug_state(driver)

    script = driver.scripts[0]
    assert "has_value: Boolean(el.value)" in script
    assert "value: el.value" not in script


def test_error_watcher_skips_html_artifact_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("DEBUG_ERROR_TRACE_DETAIL", raising=False)
    watcher = ErrorWatcher(root_dir=tmp_path, screenshot_dir=tmp_path)
    driver = FakeDriver()

    watcher._save_debug_artifacts(driver, tmp_path / "error_test", RuntimeError("boom"))

    assert not (tmp_path / "error_test.html.txt").exists()
    assert (tmp_path / "error_test.meta.txt").exists()


def test_error_watcher_writes_html_artifact_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBUG_ERROR_TRACE_DETAIL", "true")
    watcher = ErrorWatcher(root_dir=tmp_path, screenshot_dir=tmp_path)
    driver = FakeDriver()

    watcher._save_debug_artifacts(driver, tmp_path / "error_test", RuntimeError("boom"))

    assert (tmp_path / "error_test.html.txt").exists()

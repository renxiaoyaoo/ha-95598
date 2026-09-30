from scripts.support.page_tracer import PageTracer


def test_page_trace_defaults_to_errors_only(monkeypatch):
    monkeypatch.delenv("PAGE_TRACE_MODE", raising=False)

    assert PageTracer._should_capture("after_open_login_url") is False
    assert PageTracer._should_capture("mobile_password_login_form_failed") is True


def test_page_trace_mode_can_enable_all_or_disable_all(monkeypatch):
    monkeypatch.setenv("PAGE_TRACE_MODE", "all")
    assert PageTracer._should_capture("after_open_login_url") is True

    monkeypatch.setenv("PAGE_TRACE_MODE", "off")
    assert PageTracer._should_capture("mobile_password_login_form_failed") is False

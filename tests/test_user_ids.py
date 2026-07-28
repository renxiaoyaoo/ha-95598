from scripts.support.user_ids import resolve_user_ids


def test_resolve_user_ids_prefers_local_state():
    calls = 0

    def page_loader():
        nonlocal calls
        calls += 1
        return ["page-user"]

    assert resolve_user_ids(["cached-user"], page_loader) == ["cached-user"]
    assert calls == 0


def test_resolve_user_ids_uses_page_loader_when_local_state_is_empty():
    calls = 0

    def page_loader():
        nonlocal calls
        calls += 1
        return ["page-user"]

    assert resolve_user_ids([], page_loader) == ["page-user"]
    assert resolve_user_ids(None, page_loader) == ["page-user"]
    assert calls == 2

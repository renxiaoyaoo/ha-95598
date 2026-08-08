from scripts.pages import usage_selectors


def test_usage_year_option_formats_target_year():
    assert usage_selectors.year_option(2026) == "//span[text() = '2026']"


def test_usage_selectors_keep_expected_page_anchors():
    assert "tab-first" in usage_selectors.MONTHLY_TAB
    assert "tab-second" in usage_selectors.DAILY_TAB
    assert "pane-second" in usage_selectors.DAILY_TABLE_ROWS


def test_expanded_cell_for_date_targets_matching_daily_row():
    selector = usage_selectors.expanded_cell_for_date("2026-08-01")

    assert "2026-08-01" in selector
    assert "following-sibling::tr[1]" in selector

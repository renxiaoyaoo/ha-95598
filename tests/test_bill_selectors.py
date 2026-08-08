from scripts.pages import bill_selectors


def test_bill_year_option_formats_target_year():
    assert bill_selectors.bill_year_option(2026).endswith("span[normalize-space()='2026年']")


def test_bill_selectors_keep_expected_page_anchors():
    assert "billContent_bill" in bill_selectors.BILL_CARD
    assert "billInfo_cycle" in bill_selectors.BILL_DETAIL_CYCLE

from scripts.pages import login_selectors, navigator_selectors


def test_login_selectors_keep_expected_page_anchors():
    assert "login_box" in login_selectors.DESKTOP_PASSWORD_TAB
    assert "密码登录" in login_selectors.MOBILE_PASSWORD_TAB
    assert "sweepCodePic" in login_selectors.QR_IMAGE


def test_navigator_selectors_keep_expected_page_anchors():
    assert "切换用户" in navigator_selectors.SWITCH_USER_TEXT
    assert "用电户号" in navigator_selectors.USER_ID_LABEL
    assert "houseNum" in navigator_selectors.USER_SELECTOR_TRIGGER

"""Selectors for authenticated 95598 navigation pages."""

SWITCH_USER_TEXT = "//span[contains(normalize-space(.), '切换用户')]"
USER_ID_LABEL = "//*[contains(normalize-space(.), '用电户号')]"
MY_PAGE_ENTRY = "//ul[@id='column_top']//span[contains(normalize-space(.), '我的')]"
SESSION_EXPIRED_CONFIRM = (
    "//div[contains(@class,'el-message-box__wrapper')]//button[contains(@class,'el-button--primary')]"
)
USER_CONFIRM_BUTTON_CLASS = "button_confirm"
USER_CONFIRM_BUTTON = "//*[@id='app']/div/div[2]/div/div/div/div[2]/div[2]/div/button"
USER_SELECTOR_SUFFIX_CLASS = "el-input__suffix"
USER_SELECTOR_TRIGGER = (
    "//span[contains(normalize-space(.), '切换用户')]"
    " | //div[contains(@class,'houseNum')]//div[contains(@class,'el-select')]//span[contains(@class,'el-input__suffix')]"
    " | //div[contains(@class,'houseNum')]//span[contains(normalize-space(.), '切换用户')]"
)
USER_OPTIONS = (
    "//ul[contains(@class,'el-dropdown-menu')]//li"
    " | //div[contains(@class,'el-select-dropdown')]//li"
)

"""Selectors for the 95598 monthly bill pages."""

BILL_CARD = "//div[contains(@class,'billContent_bill')]"
BILL_YEAR_OPTIONS = "//div[contains(@class,'billList_timeSelection')]//div[contains(@class,'content_year')]/span"
BILL_ACTIVE_YEAR = "//div[contains(@class,'billList_timeSelection')]//div[contains(@class,'content_sleectYear')]/span"
BILL_EXPAND_BUTTON = "//div[contains(@class,'content_button')]//*[contains(text(),'查看更多')]"
BILL_MONTH_LABEL = "//div[contains(@class,'bill_time')]/span[1]"
BILL_LIST_ROW = "//div[contains(@class,'billList_content')]"
BILL_ROW_DETAIL_ARROW = ".//img[contains(@class,'back_right')]"
BILL_DETAIL_CYCLE = "//div[contains(@class,'billInfo_cycle')]"
BILL_TOTAL_USAGE = (
    "//span[contains(text(),'正向有功(总)')]/ancestor::div[contains(@class,'item_item')][1]/"
    "span[contains(@class,'thisReadPq')]"
)
BILL_TOU_ITEMS = "//div[contains(@class,'wrap_pvQtyJm')]//div[contains(@class,'right_top')]//div[contains(@class,'top_item')]"
BILL_TOU_LABEL = ".//span[contains(@class,'name')]"
BILL_TOU_VALUE = ".//div[contains(@class,'item_right')]/span"
BILL_CHARGE_ITEMS = (
    "//div[contains(@class,'wrap_electricChargeJm')]//div[contains(@class,'prcGroup_amtGroup')]//"
    "div[contains(@class,'amt_item')]"
)


def bill_year_option(target_year: int) -> str:
    return (
        "//div[contains(@class,'billList_timeSelection')]//div[contains(@class,'content_year')]/"
        f"span[normalize-space()='{int(target_year)}年']"
    )

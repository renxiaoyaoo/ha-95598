"""Selectors for the 95598 electricity usage page."""

MONTHLY_TAB = "//div[@class='el-tabs__nav is-top']/div[@id='tab-first']"
DAILY_TAB = "//div[@class='el-tabs__nav is-top']/div[@id='tab-second']"
YEAR_INPUT = '//*[@id="pane-first"]/div[1]/div/div[1]/div/div/input'
YEARLY_TOTAL = "//*[@id='pane-first']//ul[contains(@class,'total')]"
YEARLY_USAGE = "//*[@id='pane-first']//ul[contains(@class,'total')]/li[1]/span"
YEARLY_CHARGE = "//*[@id='pane-first']//ul[contains(@class,'total')]/li[2]/span"
DAILY_FIRST_USAGE = (
    "//div[@class='el-tab-pane dayd']//div[@class='el-table__body-wrapper is-scrolling-none']/"
    "table/tbody/tr[1]/td[2]/div"
)
DAILY_FIRST_DATE = (
    "//div[@class='el-tab-pane dayd']//div[@class='el-table__body-wrapper is-scrolling-none']/"
    "table/tbody/tr[1]/td[1]/div"
)
DAILY_FIRST_EXPAND_ICON = (
    "//div[@class='el-tab-pane dayd']//div[contains(@class,'el-table__body-wrapper')]//"
    "table/tbody/tr[1]//div[contains(@class,'el-table__expand-icon')]"
)
DAILY_FIRST_EXPANDED_CELL = (
    "//div[@class='el-tab-pane dayd']//table/tbody/tr[1]/following-sibling::tr[1]//"
    "td[contains(@class,'el-table__expanded-cell')]"
)
DAILY_TABLE_ROWS = (
    "//*[@id='pane-second']//div[contains(@class,'el-table__body-wrapper')]//"
    "table/tbody/tr[./td[1]/div and ./td[2]/div]"
)
DAILY_RETENTION_7 = "//*[@id='pane-second']/div[1]/div/label[1]/span[1]"
DAILY_RETENTION_30 = "//*[@id='pane-second']/div[1]/div/label[2]/span[1]"
DAILY_TABLE_BODY_ROWS = "//*[@id='pane-second']/div[2]/div[2]/div[1]/div[3]/table/tbody/tr"
MONTH_TABLE_BODY = "//*[@id='pane-first']//div[contains(@class,'el-table__body-wrapper')]//table/tbody"
ROW_DATE_CELL = "./td[1]/div"
ROW_USAGE_CELL = "./td[2]/div"
ROW_EXPAND_ICON = ".//div[contains(@class,'el-table__expand-icon')]"
ROW_CELLS = "./td"
TOU_VALUE_SELECTORS = {
    "valley_usage": ".//p[.//text()[contains(.,'谷用电')]]//span[contains(@class,'num')]",
    "flat_usage": ".//p[.//text()[contains(.,'平用电')]]//span[contains(@class,'num')]",
    "peak_usage": ".//p[.//text()[contains(.,'峰用电')]]//span[contains(@class,'num')]",
    "tip_usage": ".//p[.//text()[contains(.,'尖用电')]]//span[contains(@class,'num')]",
}


def year_option(target_year: int) -> str:
    return f"//span[text() = '{int(target_year)}']"


def expanded_cell_for_date(row_date: str) -> str:
    return (
        "//*[@id='pane-second']//div[contains(@class,'el-table__body-wrapper')]//"
        f"table/tbody/tr[./td[1]/div and normalize-space(./td[1]/div)='{row_date}']/"
        "following-sibling::tr[1]//td[contains(@class,'el-table__expanded-cell')]"
    )

"""Selectors for 95598 login pages."""

DESKTOP_LOGIN_READY_CLASS = "user"
MOBILE_LOGIN_ROOT = ".wap-login"
LOADING_MASK_CLASS = "el-loading-mask"
DESKTOP_USER_TRIGGER_CLASS = "user"
DESKTOP_PASSWORD_TAB = '//*[@id="login_box"]/div[1]/div[1]/div[2]/span'
DESKTOP_AGREEMENT_CHECKBOX = '//*[@id="login_box"]/div[2]/div[1]/form/div[1]/div[3]/div/span[2]'
DESKTOP_PHONE_CODE_TAB = '//*[@id="login_box"]/div[1]/div[1]/div[3]/span'
DESKTOP_PHONE_CODE_BUTTON = '//*[@id="login_box"]/div[2]/div[2]/form/div[1]/div[2]/div[2]/div/a'
DESKTOP_PHONE_LOGIN_BUTTON = '//*[@id="login_box"]/div[2]/div[2]/form/div[2]/div/button/span'
DESKTOP_INPUT_CLASS = "el-input__inner"
DESKTOP_LOGIN_BUTTON_CLASS = "el-button.el-button--primary"
MOBILE_PASSWORD_TAB = (
    "//div[contains(@class,'wap-login')]"
    "//div[contains(@class,'normal-title') and contains(normalize-space(.),'密码登录')]"
)
MOBILE_PASSWORD_FORM = ".wap-pass-login"
MOBILE_LOGIN_BUTTON = ".login-Btn"
LOGIN_ERROR_MESSAGES = (
    "//div[@class='errmsg-tip']//span",
    "//*[contains(@class,'errmsg-tip')]",
    "//*[contains(@class,'el-message')]",
    "//*[contains(@class,'error') or contains(@class,'err')]",
)
QR_IMAGE = "//div[@class='sweepCodePic']//img"
QR_ERROR = "//div[@class='sweepCodePic']//div[@class='erwBg']//p"
QR_TAB_CLASS = "qr_code"

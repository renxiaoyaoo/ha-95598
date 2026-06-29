from scripts.const import ELECTRIC_USAGE_URL
from scripts.support.credentials import mask_user_id


class UsagePage:
    """Operations for the 95598 electricity usage page."""

    def __init__(self, navigator, log_page_state, step_sleep):
        self.navigator = navigator
        self._log_page_state = log_page_state
        self._step_sleep = step_sleep

    def open_for_user(self, driver, user_id: str, userid_index: int, label_prefix: str = "after_open_usage_url") -> None:
        masked_user_id = mask_user_id(user_id)
        driver.get(ELECTRIC_USAGE_URL)
        self._log_page_state(driver, f"{label_prefix}_{masked_user_id}")
        self._step_sleep(driver, f"{label_prefix}_{masked_user_id}")
        self.navigator.ensure_target_userid(driver, userid_index, expected_user_id=user_id)
        self._step_sleep(driver, f"after_choose_usage_user_for_{masked_user_id}")

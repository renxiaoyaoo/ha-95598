"""Pluggable notification backends used by the scraper service."""

import io
import logging
from scripts.support.credentials import mask_user_id
import os
from dataclasses import dataclass
from typing import Protocol

import requests


class Notifier(Protocol):
    def send_qr_code(self, qrcode: bytes) -> bool: ...

    def send_stale_data_alert(self, user_id: str, latest_date: str, stale_days: int) -> bool: ...


@dataclass
class NoopNotifier:
    def send_qr_code(self, qrcode: bytes) -> bool:
        return False

    def send_stale_data_alert(self, user_id: str, latest_date: str, stale_days: int) -> bool:
        return False


@dataclass
class TelegramNotifier:
    bot_token: str
    chat_id: str
    api_base_url: str = "https://api.telegram.org"

    @property
    def api_base(self) -> str:
        return f"{self.api_base_url.rstrip('/')}/bot{self.bot_token}"

    def _send_message(self, text: str) -> bool:
        try:
            resp = requests.post(
                f"{self.api_base}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=10,
            )
            if resp.status_code == 200:
                return True
            logging.error("Telegram message push failed: %s", resp.text)
        except Exception as exc:
            logging.exception("Telegram message push exception: %s", exc)
        return False

    def send_qr_code(self, qrcode: bytes) -> bool:
        try:
            resp = requests.post(
                f"{self.api_base}/sendPhoto",
                files={"photo": ("qrcode.png", io.BytesIO(qrcode), "image/png")},
                data={"chat_id": self.chat_id, "caption": "新的国网登录二维码"},
                timeout=10,
            )
            if resp.status_code == 200:
                logging.info("QRCode sent to Telegram")
                return True
            logging.error("Telegram QRCode push failed: %s", resp.text)
        except Exception as exc:
            logging.exception("Telegram QRCode push exception: %s", exc)
        return False

    def send_stale_data_alert(self, user_id: str, latest_date: str, stale_days: int) -> bool:
        message = (
            f"国网数据停更告警\n"
            f"用户号：{mask_user_id(user_id)}\n"
            f"最新日电量日期：{latest_date}\n"
            f"距离今天已落后：{stale_days}天\n"
            f"请检查登录、验证码或网站状态。"
        )
        if self._send_message(message):
            logging.info(
                "Telegram stale data notice has been sent for user %s, latest_date=%s, stale_days=%s.",
                mask_user_id(user_id),
                latest_date,
                stale_days,
            )
            return True
        return False


def build_notifier() -> Notifier:
    notifier_type = (os.getenv("NOTIFIER") or "none").strip().lower()
    if notifier_type == "telegram":
        token = (os.getenv("TG_BOT_TOKEN") or "").strip()
        chat_id = (os.getenv("TG_CHAT_ID") or "").strip()
        if token and chat_id:
            api_base_url = (os.getenv("TG_API_BASE_URL") or "https://api.telegram.org").strip()
            if not api_base_url.startswith(("http://", "https://")):
                api_base_url = f"https://{api_base_url}"
            return TelegramNotifier(bot_token=token, chat_id=chat_id, api_base_url=api_base_url)
        logging.warning("NOTIFIER=telegram but TG_BOT_TOKEN or TG_CHAT_ID is missing, notifications disabled.")
    return NoopNotifier()

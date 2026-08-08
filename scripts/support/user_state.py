from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class UserStateSnapshot:
    balance: Any = None
    last_daily_date: Any = None
    last_daily_usage: Any = None
    last_daily_charge: Any = None
    yearly_charge: Any = None
    yearly_usage: Any = None
    month_charge: Any = None
    month_usage: Any = None
    valley_usage: Any = None
    flat_usage: Any = None
    peak_usage: Any = None
    tip_usage: Any = None
    timestamp: str | None = None

    UPDATE_KEYS = (
        "balance",
        "last_daily_date",
        "last_daily_usage",
        "last_daily_charge",
        "yearly_charge",
        "yearly_usage",
        "month_charge",
        "month_usage",
        "valley_usage",
        "flat_usage",
        "peak_usage",
        "tip_usage",
    )

    @classmethod
    def from_cache_data(cls, data: dict[str, Any]) -> "UserStateSnapshot":
        if not isinstance(data, dict):
            data = {}
        return cls(**{key: data.get(key) for key in (*cls.UPDATE_KEYS, "timestamp")})

    def to_cache_data(self) -> dict[str, Any]:
        data = {key: getattr(self, key) for key in self.UPDATE_KEYS}
        data["timestamp"] = self.timestamp or datetime.now().isoformat()
        return data

    def to_update_kwargs(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self.UPDATE_KEYS}

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DailyUsageRow:
    date: str
    total_usage: float
    valley_usage: float = 0.0
    flat_usage: float = 0.0
    peak_usage: float = 0.0
    tip_usage: float = 0.0
    total_charge: float | None = None

    def to_dict(self, *, include_charge: bool = False) -> dict[str, Any]:
        data = {
            "date": self.date,
            "total_usage": self.total_usage,
            "valley_usage": self.valley_usage,
            "flat_usage": self.flat_usage,
            "peak_usage": self.peak_usage,
            "tip_usage": self.tip_usage,
        }
        if include_charge:
            data["total_charge"] = self.total_charge
        return data


@dataclass
class MonthlyUsageRow:
    month: str
    total_usage: Any
    total_charge: Any
    valley_usage: Any = 0.0
    flat_usage: Any = 0.0
    peak_usage: Any = 0.0
    tip_usage: Any = 0.0
    source: str | None = None

    def to_dict(self, *, include_source: bool = False) -> dict[str, Any]:
        data = {
            "month": self.month,
            "total_usage": self.total_usage,
            "total_charge": self.total_charge,
            "valley_usage": self.valley_usage,
            "flat_usage": self.flat_usage,
            "peak_usage": self.peak_usage,
            "tip_usage": self.tip_usage,
        }
        if include_source and self.source is not None:
            data["source"] = self.source
        return data


@dataclass
class MonthlyBillRow(MonthlyUsageRow):
    def to_official_dict(self) -> dict[str, Any]:
        return self.to_dict()

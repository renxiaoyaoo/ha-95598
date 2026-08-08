from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class FetchResult:
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

    def as_tuple(self) -> tuple[Any, ...]:
        return (
            self.balance,
            self.last_daily_date,
            self.last_daily_usage,
            self.last_daily_charge,
            self.yearly_charge,
            self.yearly_usage,
            self.month_charge,
            self.month_usage,
            self.valley_usage,
            self.flat_usage,
            self.peak_usage,
            self.tip_usage,
        )

    def __iter__(self) -> Iterator[Any]:
        return iter(self.as_tuple())

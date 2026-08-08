from dataclasses import dataclass
from typing import Any


@dataclass
class HaSensorPayload:
    state: Any
    attributes: dict[str, Any]
    log: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "attributes": self.attributes,
            "log": self.log,
        }


class HistoryPayloadBuilder:
    @staticmethod
    def daily_history(history: dict[str, Any] | None) -> dict[str, Any] | None:
        if history is None:
            return None
        return HaSensorPayload(
            state=history["state"],
            attributes={
                "latest_date": history["latest_date"],
                "series_days": history["series_days"],
                "series": history["series"],
            },
            log={
                "latest_date": history["latest_date"],
                "series_days": history["series_days"],
            },
        ).to_dict()

    @staticmethod
    def monthly_history(series: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not series:
            return None
        latest = series[-1]
        return HaSensorPayload(
            state=latest["usage"],
            attributes={
                "latest_month": latest["month"],
                "series_months": len(series),
                "series": series,
            },
            log={
                "latest_month": latest["month"],
                "series_months": len(series),
            },
        ).to_dict()

from __future__ import annotations

from typing import Any


def build_probe_report(label: str, normalized: dict[str, Any]) -> dict[str, Any]:
    required_fields = {
        "balance": ("balance",),
        "usage": ("yearly_usage", "months", "daily"),
        "bill_summary": ("bills",),
        "bill_detail": ("month", "usage", "charge"),
    }.get(label, ())
    missing_fields = [
        field
        for field in required_fields
        if normalized.get(field) in (None, "", [])
    ]
    report = {
        "label": label,
        "ok": not missing_fields,
        "missing_fields": missing_fields,
        "has_raw": bool(normalized.get("raw")),
    }
    if label == "usage":
        report["months_count"] = len(normalized.get("months") or [])
        report["daily_count"] = len(normalized.get("daily") or [])
    elif label == "bill_summary":
        report["bills_count"] = len(normalized.get("bills") or [])
    elif label == "bill_detail":
        report["charge_segments_count"] = len(normalized.get("charge_segments") or [])
    return report

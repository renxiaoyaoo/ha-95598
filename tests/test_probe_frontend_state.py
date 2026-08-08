from scripts.support.probe_report import build_probe_report


def test_probe_report_marks_usage_ok_with_counts():
    report = build_probe_report(
        "usage",
        {
            "yearly_usage": 100.0,
            "months": [{"month": "2026-08"}],
            "daily": [{"date": "2026-08-01"}],
            "raw": {"private": "not copied"},
        },
    )

    assert report == {
        "label": "usage",
        "ok": True,
        "missing_fields": [],
        "has_raw": True,
        "months_count": 1,
        "daily_count": 1,
    }


def test_probe_report_lists_missing_fields_without_raw_values():
    report = build_probe_report(
        "bill_detail",
        {
            "month": "2026-08",
            "usage": None,
            "charge": None,
            "charge_segments": [],
        },
    )

    assert report == {
        "label": "bill_detail",
        "ok": False,
        "missing_fields": ["usage", "charge"],
        "has_raw": False,
        "charge_segments_count": 0,
    }

import json

from scripts.tools.check_local_tariff import check_tariff_config


def test_check_tariff_config_accepts_complete_month_rules(tmp_path) -> None:
    config_path = tmp_path / "tou_price_config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "versions": [
                    {
                        "version": "local",
                        "validfrom": "2026-07-01",
                        "validuntil": "2099-12-31",
                        "season_rules": [
                            {
                                "name": "summer",
                                "months": [7, 8, 9],
                                "tiers": [
                                    {"up_to": 260, "rates": {"valley": 0.5, "flat": 0.5, "peak": 0.5, "tip": 0.5}},
                                    {"up_to": None, "rates": {"valley": 0.6, "flat": 0.6, "peak": 0.6, "tip": 0.6}},
                                ],
                            },
                            {
                                "name": "regular",
                                "months": [1, 2, 3, 4, 5, 6, 10, 11, 12],
                                "tiers": [
                                    {"up_to": 180, "rates": {"valley": 0.5, "flat": 0.5, "peak": 0.5, "tip": 0.5}},
                                    {"up_to": None, "rates": {"valley": 0.6, "flat": 0.6, "peak": 0.6, "tip": 0.6}},
                                ],
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = check_tariff_config(config_path)

    assert result.ok is True


def test_check_tariff_config_rejects_missing_months(tmp_path) -> None:
    config_path = tmp_path / "tou_price_config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "versions": [
                    {
                        "version": "local",
                        "validfrom": "2026-07-01",
                        "validuntil": "2099-12-31",
                        "season_rules": [
                            {
                                "name": "summer",
                                "months": [7, 8, 9],
                                "tiers": [
                                    {"up_to": None, "rates": {"valley": 0.5, "flat": 0.5, "peak": 0.5, "tip": 0.5}},
                                ],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = check_tariff_config(config_path)

    assert result.ok is False
    assert "months are not fully covered" in result.messages

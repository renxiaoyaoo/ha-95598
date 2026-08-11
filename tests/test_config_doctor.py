from scripts.tools import config_doctor


def test_doctor_prints_summary_without_raw_findings(capsys):
    config_doctor._print_result(config_doctor.DoctorCheck("privacy tracked", False))

    output = capsys.readouterr().out

    assert output == "failed: privacy tracked\n"


def test_env_check_accepts_minimal_account_config(tmp_path):
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                'ACCOUNT="account@example.com"',
                'PASSWORD="password1"',
                'MQTT_HOST=""',
            ]
        ),
        encoding="utf-8",
    )

    result = config_doctor._run_env_check(tmp_path)

    assert result.ok is True
    assert result.detail == "mqtt disabled"


def test_env_check_accepts_login_credentials_pool(tmp_path):
    (tmp_path / ".env").write_text(
        'LOGIN_CREDENTIALS=\'[{"account":"account@example.com","password":"password1"}]\'\n',
        encoding="utf-8",
    )

    result = config_doctor._run_env_check(tmp_path)

    assert result.ok is True


def test_env_check_reports_missing_keys_without_values(tmp_path):
    (tmp_path / ".env").write_text('ACCOUNT="account@example.com"\n', encoding="utf-8")

    result = config_doctor._run_env_check(tmp_path)

    assert result.ok is False
    assert result.detail == "missing PASSWORD"

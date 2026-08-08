from scripts.tools import config_doctor


def test_doctor_prints_summary_without_raw_findings(capsys):
    config_doctor._print_result(config_doctor.DoctorCheck("privacy tracked", False))

    output = capsys.readouterr().out

    assert output == "failed: privacy tracked\n"

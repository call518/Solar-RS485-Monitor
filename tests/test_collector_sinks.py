import pytest

from solar_rs485_monitor.collector import parse_collector_sinks


def test_parse_collector_sinks_accepts_documented_google_sheet_name() -> None:
    assert parse_collector_sinks("google_sheet, thingspeak") == {
        "google_sheet",
        "thingspeak",
    }


def test_parse_collector_sinks_accepts_google_sheet_aliases() -> None:
    assert parse_collector_sinks("google-sheet,google_sheets,googlesheet") == {
        "google_sheet"
    }


def test_parse_collector_sinks_skips_unknown_sink(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parse_collector_sinks("google_sheet,unknown") == {"google_sheet"}

    captured = capsys.readouterr()
    assert '"level": "warning"' in captured.out
    assert '"field": "COLLECTOR_SINKS"' in captured.out
    assert '"invalid_values": [\n    "unknown"\n  ]' in captured.out


def test_parse_collector_sinks_warns_unknown_sink_with_all(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parse_collector_sinks("all,unknown") == {"all"}

    captured = capsys.readouterr()
    assert '"field": "COLLECTOR_SINKS"' in captured.out
    assert '"unknown"' in captured.out

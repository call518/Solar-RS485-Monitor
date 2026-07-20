import pytest

from solar_rs485_monitor.alerts.dispatcher import parse_alert_channels


def test_parse_alert_channels_accepts_aliases() -> None:
    assert parse_alert_channels("telegram,tg") == {"telegram"}


def test_parse_alert_channels_skips_unknown_channel(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parse_alert_channels("telegram,email") == {"telegram"}

    captured = capsys.readouterr()
    assert '"level": "warning"' in captured.err
    assert '"field": "ALERT_CHANNELS"' in captured.err
    assert '"email"' in captured.err


def test_parse_alert_channels_warns_unknown_channel_with_all(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parse_alert_channels("all,email") == {"all"}

    captured = capsys.readouterr()
    assert '"field": "ALERT_CHANNELS"' in captured.err
    assert '"email"' in captured.err

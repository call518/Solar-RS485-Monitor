import json
import sys
from contextlib import nullcontext
from datetime import date, datetime, timezone
from io import StringIO
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from solar_rs485_monitor import solar_weather


def weather_response() -> dict[str, Any]:
    """Provide daily source units and a real zero distinct from a missing day."""
    return {
        "daily_units": {"shortwave_radiation_sum": "MJ/m²", "sunshine_duration": "s"},
        "daily": {
            "time": ["2026-10-01", "2026-10-03"],
            "shortwave_radiation_sum": [18, 0],
            "sunshine_duration": [18000, None],
        },
    }


def test_unit_conversion_and_missing_days() -> None:
    rows = solar_weather.normalize_daily_weather(
        weather_response(), date(2026, 10, 1), date(2026, 10, 3)
    )
    assert rows == [
        {"date": "2026-10-01", "radiation_kwh_m2": 5, "sunshine_hours": 5},
        {"date": "2026-10-02", "radiation_kwh_m2": None, "sunshine_hours": None},
        {"date": "2026-10-03", "radiation_kwh_m2": 0, "sunshine_hours": None},
    ]


@pytest.mark.parametrize(
    "invalid", ["units", "length", "negative", "infinite", "duration", "duplicate"]
)
def test_invalid_provider_data_is_rejected(invalid: str) -> None:
    payload = weather_response()
    if invalid == "units":
        payload["daily_units"]["shortwave_radiation_sum"] = "W/m²"
    elif invalid == "length":
        payload["daily"]["sunshine_duration"] = []
    elif invalid == "duplicate":
        payload["daily"]["time"] = ["2026-10-01", "2026-10-01"]
    elif invalid == "duration":
        payload["daily"]["sunshine_duration"][0] = 90000
    else:
        payload["daily"]["shortwave_radiation_sum"][0] = (
            -1 if invalid == "negative" else float("inf")
        )
    with pytest.raises(solar_weather.WeatherError):
        solar_weather.normalize_daily_weather(
            payload, date(2026, 10, 1), date(2026, 10, 3)
        )


def test_range_excludes_today_in_installation_timezone() -> None:
    seoul = ZoneInfo("Asia/Seoul")
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 8, 15, 1, tzinfo=timezone.utc)
    assert solar_weather.get_weather_dates(start, end, seoul, date(2026, 10, 9)) == (
        date(2026, 10, 1),
        date(2026, 10, 8),
    )
    assert solar_weather.get_weather_dates(end, end, seoul, date(2026, 10, 9)) is None
    assert solar_weather.get_weather_dates(start, start, seoul, date(2026, 10, 9)) == (
        date(2026, 10, 1),
        date(2026, 10, 1),
    )


@pytest.mark.parametrize(
    "latitude, longitude",
    [("91", "127"), ("35", "181"), ("nan", "127"), ("35", ""), ("text", "127")],
)
def test_invalid_coordinates(
    latitude: str, longitude: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOLAR_LATITUDE", latitude)
    monkeypatch.setenv("SOLAR_LONGITUDE", longitude)
    with pytest.raises(solar_weather.WeatherError):
        solar_weather.get_solar_coordinates()


def test_optional_and_valid_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOLAR_LATITUDE", raising=False)
    monkeypatch.delenv("SOLAR_LONGITUDE", raising=False)
    assert solar_weather.get_solar_coordinates() is None
    monkeypatch.setenv("SOLAR_LATITUDE", "35.0474797566362")
    monkeypatch.setenv("SOLAR_LONGITUDE", "127.789455645983")
    assert solar_weather.get_solar_coordinates() == (35.0474797566362, 127.789455645983)


def test_query_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    solar_weather.read_daily_solar_weather.clear()
    calls = []

    def handle_request(url: str, timeout: int) -> Any:
        calls.append(url)
        query = parse_qs(urlparse(url).query)
        assert query["daily"] == ["shortwave_radiation_sum,sunshine_duration"]
        assert query["timezone"] == ["Asia/Seoul"]
        assert query["end_date"] == ["2026-10-03"]
        assert timeout == 10
        return nullcontext(StringIO(json.dumps(weather_response())))

    monkeypatch.setattr(solar_weather, "urlopen", handle_request)
    args = (
        35.0474797566362,
        127.789455645983,
        date(2026, 10, 1),
        date(2026, 10, 3),
        "Asia/Seoul",
    )
    first = solar_weather.read_daily_solar_weather(*args)
    assert solar_weather.read_daily_solar_weather(*args) == first
    assert len(calls) == 1
    solar_weather.read_daily_solar_weather.clear()


@pytest.mark.parametrize(
    "error",
    [
        HTTPError("https://example.com", 429, "private", {}, None),
        URLError("private"),
        TimeoutError("private"),
    ],
)
def test_provider_errors_are_safe(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    solar_weather.read_daily_solar_weather.clear()

    def handle_request(*args: Any, **kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(solar_weather, "urlopen", handle_request)
    with pytest.raises(solar_weather.WeatherError) as caught:
        solar_weather.read_daily_solar_weather(
            35, 127, date(2026, 10, 1), date(2026, 10, 3), "Asia/Seoul"
        )
    assert "private" not in str(caught.value)


def test_dashboard_chart_axes_and_missing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from solar_rs485_monitor import dashboard

    class DashboardStub:
        def __init__(self) -> None:
            self.captions: list[str] = []

        def markdown(self, value: str) -> None:
            pass

        def caption(self, value: str) -> None:
            self.captions.append(value)

        def warning(self, value: str) -> None:
            self.captions.append(value)

    rows = solar_weather.normalize_daily_weather(
        weather_response(), date(2026, 10, 1), date(2026, 10, 3)
    )
    monkeypatch.setattr(dashboard, "get_solar_coordinates", lambda: (35, 127))
    monkeypatch.setattr(dashboard, "read_daily_solar_weather", lambda *args: rows)
    captured: dict[str, Any] = {}

    def handle_chart(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules, "streamlit_echarts", SimpleNamespace(st_echarts=handle_chart)
    )
    st = DashboardStub()
    dashboard.render_solar_weather_chart(
        st,
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 3, tzinfo=timezone.utc),
        dashboard.UI_TEXT["en"],
        ZoneInfo("Asia/Seoul"),
    )
    options = captured["options"]
    assert options["yAxis"][0]["position"] == "left"
    assert options["yAxis"][1]["position"] == "right"
    assert options["series"][0]["data"] == [5, None, 0]
    assert options["series"][1]["yAxisIndex"] == 1
    assert options["series"][1]["connectNulls"] is False
    assert any("Open-Meteo" in caption for caption in st.captions)

    def handle_failure(*args: Any) -> Any:
        raise solar_weather.WeatherError("Open-Meteo HTTP 429.")

    monkeypatch.setattr(dashboard, "read_daily_solar_weather", handle_failure)
    captured.clear()
    dashboard.render_solar_weather_chart(
        st,
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 3, tzinfo=timezone.utc),
        dashboard.UI_TEXT["en"],
        ZoneInfo("Asia/Seoul"),
    )
    assert not captured
    assert "Weather data request failed: Open-Meteo HTTP 429." in st.captions

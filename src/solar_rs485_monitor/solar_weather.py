"""Open-Meteo daily solar weather for a fixed installation location."""

import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from streamlit import cache_data


class WeatherError(RuntimeError):
    """A weather configuration or response error safe to display to users."""


def get_solar_coordinates() -> tuple[float, float] | None:
    """Read optional installation coordinates without guessing a location."""
    latitude = os.getenv("SOLAR_LATITUDE", "").strip()
    longitude = os.getenv("SOLAR_LONGITUDE", "").strip()
    if not latitude and not longitude:
        return None
    try:
        coordinates = (float(latitude), float(longitude))
    except ValueError:
        raise WeatherError("Set valid SOLAR_LATITUDE and SOLAR_LONGITUDE.") from None
    if not (-90 <= coordinates[0] <= 90 and -180 <= coordinates[1] <= 180):
        raise WeatherError("SOLAR_LATITUDE or SOLAR_LONGITUDE is out of range.")
    return coordinates


def get_weather_dates(
    since: datetime, until: datetime, display_timezone: ZoneInfo, today: date
) -> tuple[date, date] | None:
    """Use the displayed date range, excluding today's unfinished local day."""
    start = since.astimezone(display_timezone).date()
    end = min(until.astimezone(display_timezone).date(), today - timedelta(days=1))
    return (start, end) if start <= end else None


def normalize_daily_weather(
    response: dict[str, Any], start: date, end: date
) -> list[dict[str, Any]]:
    """Convert daily MJ/m² and seconds, retaining missing days as nulls."""
    try:
        units = response["daily_units"]
        if (
            units["shortwave_radiation_sum"] != "MJ/m²"
            or units["sunshine_duration"] != "s"
        ):
            raise ValueError("Unexpected units")
        daily = response["daily"]
        days = daily["time"]
        radiation = daily["shortwave_radiation_sum"]
        sunshine = daily["sunshine_duration"]
        if not all(isinstance(values, list) for values in (days, radiation, sunshine)):
            raise ValueError("Invalid daily arrays")
        if len(days) != len(radiation) or len(days) != len(sunshine):
            raise ValueError("Mismatched daily arrays")
        rows = {}
        for day, energy, duration in zip(days, radiation, sunshine):
            parsed = date.fromisoformat(day)
            if parsed in rows:
                raise ValueError("Duplicate date")
            values = (energy, duration)
            if any(
                value is not None
                and (not math.isfinite(float(value)) or float(value) < 0)
                for value in values
            ):
                raise ValueError("Invalid measurement")
            if duration is not None and float(duration) > 86400:
                raise ValueError("Invalid sunshine duration")
            rows[parsed] = {
                "date": parsed.isoformat(),
                "radiation_kwh_m2": round(float(energy) / 3.6, 3)
                if energy is not None
                else None,
                "sunshine_hours": round(float(duration) / 3600, 3)
                if duration is not None
                else None,
            }
    except (KeyError, TypeError, ValueError, OverflowError):
        raise WeatherError("Open-Meteo returned invalid daily weather data.") from None
    return [
        rows.get(
            day,
            {"date": day.isoformat(), "radiation_kwh_m2": None, "sunshine_hours": None},
        )
        for offset in range((end - start).days + 1)
        for day in [start + timedelta(days=offset)]
    ]


@cache_data(ttl=3600, max_entries=32, show_spinner=False)
def read_daily_solar_weather(
    latitude: float, longitude: float, start: date, end: date, timezone_name: str
) -> list[dict[str, Any]]:
    """Read cached historical model estimates, including recent IFS data."""
    query = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "shortwave_radiation_sum,sunshine_duration",
            "timezone": timezone_name,
        }
    )
    try:
        with urlopen(
            f"https://archive-api.open-meteo.com/v1/archive?{query}", timeout=10
        ) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise WeatherError(f"Open-Meteo HTTP {error.code}.") from None
    except (URLError, TimeoutError, OSError):
        raise WeatherError("Open-Meteo connection failed or timed out.") from None
    except ValueError:
        raise WeatherError("Open-Meteo returned an unreadable response.") from None
    if not isinstance(payload, dict):
        raise WeatherError("Open-Meteo returned invalid daily weather data.")
    return normalize_daily_weather(payload, start, end)

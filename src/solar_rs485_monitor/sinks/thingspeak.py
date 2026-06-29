import os
from urllib.parse import urlencode
from urllib.request import urlopen


DEFAULT_FIELD_MAP = {
    "field1": "pv_voltage_v",
    "field2": "pv_current_a",
    "field3": "pv_power_w",
    "field4": "grid_voltage_v",
    "field5": "grid_current_a",
    "field6": "current_output_w",
    "field7": "total_generation_kwh",
    "field8": "fault_code",
}


def get_field_map() -> dict:
    return DEFAULT_FIELD_MAP.copy()


def write_to_thingspeak(
    data: dict,
    api_key: str,
    field_map: dict,
    timeout: float,
) -> int:
    if not api_key:
        raise RuntimeError("THINGSPEAK_API_KEY is not set")

    params = {"api_key": api_key}

    for field_name, metric_name in field_map.items():
        if metric_name not in data:
            raise RuntimeError(
                f"ThingSpeak metric not found: {metric_name}"
            )

        params[field_name] = data[metric_name]

    url = "https://api.thingspeak.com/update?" + urlencode(params)

    with urlopen(url, timeout=timeout) as response:
        response_body = response.read().decode("utf-8").strip()

    try:
        entry_id = int(response_body)
    except ValueError:
        raise RuntimeError(f"Unexpected ThingSpeak response: {response_body}")

    if entry_id == 0:
        raise RuntimeError(
            "ThingSpeak update rejected. "
            "Check THINGSPEAK_API_KEY and wait at least 15 seconds "
            "between channel updates."
        )

    return entry_id

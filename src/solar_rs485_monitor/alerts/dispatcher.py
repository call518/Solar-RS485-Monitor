import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from solar_rs485_monitor.alerts.telegram import (
    get_telegram_config,
    has_telegram_config,
    send_alert as send_telegram_alert,
)


@dataclass(frozen=True)
class AlertHandler:
    name: str
    aliases: tuple[str, ...]
    get_config: Callable[[], dict]
    has_config: Callable[[dict], bool]
    send: Callable[[dict, dict], dict]


_ALERT_HANDLERS: dict[str, AlertHandler] = {
    "telegram": AlertHandler(
        name="telegram",
        aliases=("telegram", "tg"),
        get_config=get_telegram_config,
        has_config=has_telegram_config,
        send=send_telegram_alert,
    ),
}
SUPPORTED_ALERT_CHANNELS = ("all", *tuple(sorted(_ALERT_HANDLERS.keys())))


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def print_alert_channel_warning(invalid_values: list[str]) -> None:
    print(
        json.dumps(
            {
                "@timestamp": now_utc_iso(),
                "level": "warning",
                "event": "config_invalid_value",
                "component": "config",
                "field": "ALERT_CHANNELS",
                "invalid_values": sorted(invalid_values),
                "supported_values": list(SUPPORTED_ALERT_CHANNELS),
                "action": "skipped",
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
        flush=True,
    )


def list_alert_handler_names() -> list[str]:
    return sorted(_ALERT_HANDLERS.keys())


def get_alert_handler(name: str) -> AlertHandler:
    handler = _ALERT_HANDLERS.get(name)

    if handler is None:
        raise RuntimeError(f"Unknown alert channel: {name}")

    return handler


def get_alert_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}

    for canonical_name, handler in _ALERT_HANDLERS.items():
        for alias in handler.aliases:
            aliases[alias] = canonical_name

    return aliases


def parse_alert_channels(value: str) -> set[str]:
    channel_text = value.strip()

    if not channel_text:
        return set()

    aliases = {
        "all": "all",
        **get_alert_aliases(),
    }
    requested = {
        item.strip().lower().replace("-", "_")
        for item in channel_text.split(",")
        if item.strip()
    }

    channels = set()
    invalid = []

    for channel in requested:
        canonical = aliases.get(channel)

        if canonical is None:
            invalid.append(channel)
            continue

        channels.add(canonical)

    if invalid:
        print_alert_channel_warning(invalid)

    if "all" in channels:
        return {"all"}

    return channels

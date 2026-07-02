from dataclasses import dataclass
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

    aliases = get_alert_aliases()
    requested = {
        item.strip().lower().replace("-", "_")
        for item in channel_text.split(",")
        if item.strip()
    }

    if "all" in requested:
        return {"all"}

    channels = set()
    invalid = []

    for channel in requested:
        canonical = aliases.get(channel)

        if canonical is None:
            invalid.append(channel)
            continue

        channels.add(canonical)

    if invalid:
        raise RuntimeError(
            "Invalid ALERT_CHANNELS value(s): "
            + ", ".join(sorted(invalid))
        )

    return channels
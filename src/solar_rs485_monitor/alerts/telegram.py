import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from solar_rs485_monitor.alerts.message import (
    build_fault_event_message,
    build_sink_error_message,
    build_summary_message,
    build_system_error_message,
    build_system_recovered_message,
    format_code,
    parse_int_value,
)


FAULT_EVENT_MASK = 0xFFFE
OPERATION_STOP_MASK = 0x0001

_last_operation_stopped: bool | None = None


def parse_chat_ids(chat_ids_text: str, single_chat_id: str) -> list[str]:
    chat_ids = []

    for item in chat_ids_text.split(","):
        value = item.strip()

        if value:
            chat_ids.append(value)

    if single_chat_id:
        chat_ids.append(single_chat_id)

    # Keep input order but remove duplicates.
    unique_chat_ids = list(dict.fromkeys(chat_ids))
    return unique_chat_ids


def get_telegram_config() -> dict:
    single_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    chat_ids = parse_chat_ids(
        os.getenv("TELEGRAM_CHAT_IDS", ""),
        single_chat_id,
    )

    return {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "chat_id": single_chat_id,
        "chat_ids": chat_ids,
        "message_thread_id": os.getenv("TELEGRAM_MESSAGE_THREAD_ID", "").strip(),
        "timeout": float(os.getenv("TELEGRAM_TIMEOUT", "5.0")),
        "disable_notification": os.getenv(
            "TELEGRAM_DISABLE_NOTIFICATION",
            "false",
        ).strip().lower() in ("1", "true", "yes", "y", "on"),
        "parse_mode": os.getenv("TELEGRAM_PARSE_MODE", "Markdown").strip(),
        "send_summary": os.getenv(
            "TELEGRAM_SEND_SUMMARY",
            "true",
        ).strip().lower() in ("1", "true", "yes", "y", "on"),
        "send_fault_event": os.getenv(
            "TELEGRAM_SEND_FAULT_EVENT",
            "true",
        ).strip().lower() in ("1", "true", "yes", "y", "on"),
        "send_sink_error": os.getenv(
            "TELEGRAM_SEND_SINK_ERROR",
            "true",
        ).strip().lower() in ("1", "true", "yes", "y", "on"),
        "send_system_error": os.getenv(
            "TELEGRAM_SEND_SYSTEM_ERROR",
            "true",
        ).strip().lower() in ("1", "true", "yes", "y", "on"),
        "send_standby_event": os.getenv(
            "TELEGRAM_SEND_STANDBY_EVENT",
            "true",
        ).strip().lower() in ("1", "true", "yes", "y", "on"),
    }


def has_telegram_config(config: dict) -> bool:
    return bool(config.get("bot_token") and config.get("chat_ids"))


def validate_telegram_config(config: dict) -> None:
    if not config.get("bot_token"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    if not config.get("chat_ids"):
        raise RuntimeError("TELEGRAM_CHAT_ID or TELEGRAM_CHAT_IDS is not set")


def send_telegram_message(config: dict, text: str, chat_id: str) -> dict:
    validate_telegram_config(config)

    url = (
        f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_notification": config["disable_notification"],
    }

    if config.get("parse_mode"):
        payload["parse_mode"] = config["parse_mode"]

    if config.get("message_thread_id"):
        payload["message_thread_id"] = int(config["message_thread_id"])

    body = urlencode(payload).encode("utf-8")
    request = Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=config["timeout"]) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Telegram request failed status={e.code} body={error_body}"
        ) from e

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Unexpected Telegram response: {response_body}") from e

    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {response_body}")

    message = result.get("result", {})
    return {
        "chat_id": str(message.get("chat", {}).get("id", chat_id)),
        "message_id": message.get("message_id"),
    }


def send_to_all_chat_ids(config: dict, text: str) -> dict:
    sent = []
    failed = []

    for chat_id in config.get("chat_ids", []):
        try:
            result = send_telegram_message(config, text, chat_id)
            sent.append(result)
        except Exception as e:
            failed.append({
                "chat_id": chat_id,
                "error": str(e),
            })

    return {
        "sent": sent,
        "failed": failed,
    }


def build_operation_state_message(data: dict, fault_code: int, state: str) -> str:
    bit_value = 1 if state == "STANDBY" else 0
    title = "Standby" if state == "STANDBY" else "Normal"

    return "\n".join(
        [
            f"*Solar RS485 {title} Event*",
            f"Time: {format_code(data.get('@timestamp', '-'))}",
            f"Inverter: {format_code(data.get('inverter_name', '-'))} "
            f"(ID {format_code(data.get('inverter_id', '-'))})",
            f"Fault code: {format_code(fault_code)}",
            f"State: {format_code(f'{state} (Bit 0 = {bit_value})')}",
        ]
    )


def write_to_telegram(data: dict, config: dict) -> dict:
    global _last_operation_stopped

    sent_summary = {"sent": [], "failed": []}
    sent_event = {"sent": [], "failed": []}

    fault_code = parse_int_value(data.get("fault_code"), 0)
    is_fault_event = (fault_code & FAULT_EVENT_MASK) != 0
    is_operation_stopped = (fault_code & OPERATION_STOP_MASK) != 0

    standby_transition = False
    normal_transition = False
    if config.get("send_standby_event", False):
        standby_transition = _last_operation_stopped is False and is_operation_stopped
        normal_transition = (
            _last_operation_stopped is True
            and not is_operation_stopped
            and not is_fault_event
        )

    if _last_operation_stopped is None:
        _last_operation_stopped = is_operation_stopped

    should_send = is_fault_event or standby_transition or normal_transition

    if not should_send:
        _last_operation_stopped = is_operation_stopped
        return {
            "summary": None,
            "fault_event": None,
            "skipped": True,
            "chat_ids": config.get("chat_ids", []),
        }

    if is_fault_event and config.get("send_fault_event", True):
        sent_event = send_to_all_chat_ids(config, build_fault_event_message(data))

    if standby_transition and config.get("send_standby_event", False):
        sent_standby = send_to_all_chat_ids(
            config,
            build_operation_state_message(data, fault_code, "STANDBY"),
        )
        sent_event = {
            "sent": sent_event.get("sent", []) + sent_standby.get("sent", []),
            "failed": sent_event.get("failed", []) + sent_standby.get("failed", []),
        }

    if normal_transition and config.get("send_standby_event", False):
        sent_normal = send_to_all_chat_ids(
            config,
            build_operation_state_message(data, fault_code, "NORMAL"),
        )
        sent_event = {
            "sent": sent_event.get("sent", []) + sent_normal.get("sent", []),
            "failed": sent_event.get("failed", []) + sent_normal.get("failed", []),
        }

    if config.get("send_summary", False):
        sent_summary = send_to_all_chat_ids(config, build_summary_message(data))

    _last_operation_stopped = is_operation_stopped

    return {
        "summary": sent_summary,
        "fault_event": sent_event,
        "chat_ids": config.get("chat_ids", []),
        "skipped": False,
    }


def send_alert(data: dict, config: dict) -> dict:
    return write_to_telegram(data=data, config=config)


def send_sink_error_alert(
    data: dict,
    config: dict,
    sink: str,
    error: Exception,
    event: str = "sink_insert_failed",
) -> dict:
    if not config.get("send_sink_error", True):
        return {
            "sent": [],
            "failed": [],
            "skipped": True,
            "chat_ids": config.get("chat_ids", []),
        }

    result = send_to_all_chat_ids(
        config,
        build_sink_error_message(
            data=data,
            sink=sink,
            error=error,
            event=event,
        ),
    )
    return {
        **result,
        "skipped": False,
        "chat_ids": config.get("chat_ids", []),
    }


def send_system_error_alert(
    data: dict,
    config: dict,
    component: str,
    event: str,
    error: Exception,
    failures: int | None = None,
) -> dict:
    if not config.get("send_system_error", True):
        return {
            "sent": [],
            "failed": [],
            "skipped": True,
            "chat_ids": config.get("chat_ids", []),
        }

    result = send_to_all_chat_ids(
        config,
        build_system_error_message(
            data=data,
            component=component,
            event=event,
            error=error,
            failures=failures,
        ),
    )
    return {
        **result,
        "skipped": False,
        "chat_ids": config.get("chat_ids", []),
    }


def send_system_recovered_alert(
    data: dict,
    config: dict,
    component: str,
    event: str,
    failures: int,
) -> dict:
    if not config.get("send_system_error", True):
        return {
            "sent": [],
            "failed": [],
            "skipped": True,
            "chat_ids": config.get("chat_ids", []),
        }

    result = send_to_all_chat_ids(
        config,
        build_system_recovered_message(
            data=data,
            component=component,
            event=event,
            failures=failures,
        ),
    )
    return {
        **result,
        "skipped": False,
        "chat_ids": config.get("chat_ids", []),
    }

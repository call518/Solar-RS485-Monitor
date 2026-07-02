import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
    }


def has_telegram_config(config: dict) -> bool:
    return bool(config.get("bot_token") and config.get("chat_ids"))


def validate_telegram_config(config: dict) -> None:
    if not config.get("bot_token"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    if not config.get("chat_ids"):
        raise RuntimeError("TELEGRAM_CHAT_ID or TELEGRAM_CHAT_IDS is not set")


def build_summary_message(data: dict) -> str:
    fault_code = parse_int_value(data.get("fault_code"), 0)
    fault = parse_int_value(data.get("fault"), 0)
    active_bits = format_active_bits(fault_code)

    return "\n".join(
        [
            "*Solar RS485 Monitor*",
            f"Time: `{data.get('@timestamp', '-')}`",
            f"Inverter: `{data.get('inverter_name', '-')}` (ID `{data.get('inverter_id', '-')}`)",
            f"Fault: `{fault}`",
            f"Fault code: `{fault_code}`",
            f"Active bits: `{active_bits}`",
            "",
            "*DC Input*",
            f"- Voltage: `{data.get('input_dc_voltage_v', '-')}` V",
            f"- Current: `{data.get('input_dc_current_a', '-')}` A",
            f"- Power: `{data.get('input_dc_power_w', '-')}` W",
            "",
            "*AC Output*",
            f"- Voltage: `{data.get('output_ac_voltage_v', '-')}` V",
            f"- Current: `{data.get('output_ac_current_a', '-')}` A",
            f"- Power: `{data.get('output_ac_power_w', '-')}` W",
            f"- Power factor: `{data.get('output_ac_power_factor_pct', '-')}` %",
            f"- Frequency: `{data.get('output_ac_frequency_hz', '-')}` Hz",
            "",
            f"Total: `{data.get('total_generation_kwh', '-')}` kWh",
            f"Raw frame: `{data.get('raw_frame_hex', '-')}`",
        ]
    )


def build_fault_event_message(data: dict) -> str:
    fault_code = parse_int_value(data.get("fault_code"), 0)
    fault = parse_int_value(data.get("fault"), 0)
    active_bits = format_active_bits(fault_code)

    return "\n".join(
        [
            "*Solar RS485 Fault Event*",
            f"Time: `{data.get('@timestamp', '-')}`",
            f"Inverter: `{data.get('inverter_name', '-')}` (ID `{data.get('inverter_id', '-')}`)",
            f"Fault: `{fault}`",
            f"Fault code: `{fault_code}`",
            f"Active bits: `{active_bits}`",
            "",
            "*DC Input*",
            f"- Voltage: `{data.get('input_dc_voltage_v', '-')}` V",
            f"- Current: `{data.get('input_dc_current_a', '-')}` A",
            f"- Power: `{data.get('input_dc_power_w', '-')}` W",
            "",
            "*AC Output*",
            f"- Voltage: `{data.get('output_ac_voltage_v', '-')}` V",
            f"- Current: `{data.get('output_ac_current_a', '-')}` A",
            f"- Power: `{data.get('output_ac_power_w', '-')}` W",
            f"- Power factor: `{data.get('output_ac_power_factor_pct', '-')}` %",
            f"- Frequency: `{data.get('output_ac_frequency_hz', '-')}` Hz",
            "",
            f"Total: `{data.get('total_generation_kwh', '-')}` kWh",
            f"Raw frame: `{data.get('raw_frame_hex', '-')}`",
        ]
    )


def parse_int_value(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def format_active_bits(fault_code: int) -> str:
    if fault_code <= 0:
        return "-"

    bits = [f"Bit {bit}" for bit in range(16) if fault_code & (1 << bit)]
    return ", ".join(bits) if bits else "-"


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


def write_to_telegram(data: dict, config: dict) -> dict:
    sent_summary = {"sent": [], "failed": []}
    sent_event = {"sent": [], "failed": []}

    fault = parse_int_value(data.get("fault"), 0)
    fault_code = parse_int_value(data.get("fault_code"), 0)
    is_fault_event = (fault == 1) or (fault_code != 0)

    if not is_fault_event:
        return {
            "summary": None,
            "fault_event": None,
            "skipped": True,
            "chat_ids": config.get("chat_ids", []),
        }

    if config.get("send_fault_event", True):
        sent_event = send_to_all_chat_ids(config, build_fault_event_message(data))

    if config.get("send_summary", False):
        sent_summary = send_to_all_chat_ids(config, build_summary_message(data))

    return {
        "summary": sent_summary,
        "fault_event": sent_event,
        "chat_ids": config.get("chat_ids", []),
        "skipped": False,
    }

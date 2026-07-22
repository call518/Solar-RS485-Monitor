#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, time as datetime_time, timezone
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import serial
from dotenv import load_dotenv

from solar_rs485_monitor.sinks.google_sheets import (
    get_google_sheet,
    write_to_google_sheet,
)
from solar_rs485_monitor.sinks.mariadb import (
    get_mariadb_config,
    write_to_mariadb,
)
from solar_rs485_monitor.sinks.opensearch import (
    get_opensearch_config,
    write_to_opensearch,
)
from solar_rs485_monitor.sinks.supabase import (
    get_supabase_config,
    write_to_supabase,
)
from solar_rs485_monitor.sinks.sqlite import (
    get_sqlite_config,
    write_to_sqlite,
)
from solar_rs485_monitor.sinks.thingspeak import (
    get_field_map as get_thingspeak_field_map,
    write_to_thingspeak,
)
from solar_rs485_monitor.alerts.dispatcher import (
    get_alert_handler,
    list_alert_handler_names,
    parse_alert_channels,
)
from solar_rs485_monitor.alerts.telegram import (
    send_sink_error_alert,
    send_system_error_alert,
    send_system_recovered_alert,
)
from solar_rs485_monitor.protocols import InverterProtocol, get_protocol
from solar_rs485_monitor.version import get_version

CONFIG_FILENAME = "solar-rs485-monitor.conf"
CONFIG_TEMPLATE_FILENAME = "solar-rs485-monitor.conf.template"
MIN_COLLECT_INTERVAL_SECONDS = 60.0
DEFAULT_ALERT_COOLDOWN_SECONDS = 900.0
DEFAULT_COLLECTOR_FAILURE_ALERT_THRESHOLD = 3
DEFAULT_COLLECTOR_STATE_PATH = (
    "/var/lib/solar-rs485-monitor/collector-state.json"
)
DEFAULT_COLLECTOR_STATE_MAX_AGE_SECONDS = 86400.0
DEFAULT_COLLECTOR_UNKNOWN_STATE_NO_RESPONSE_SUPPRESS_SECONDS = 43200.0
DEFAULT_COLLECTOR_STANDBY_POWER_W_THRESHOLD = 20.0
DEFAULT_COLLECTOR_NORMAL_POWER_W_THRESHOLD = 30.0
DEFAULT_COLLECTOR_LOCAL_TIMEZONE = "Asia/Seoul"
DEFAULT_COLLECTOR_NIGHT_NO_RESPONSE_START = "20:00"
DEFAULT_COLLECTOR_NIGHT_NO_RESPONSE_END = "04:00"
FAULT_EVENT_MASK = 0xFFFE
OPERATION_STOP_MASK = 0x0001
SUPPORTED_COLLECTOR_SINKS = (
    "all",
    "google_sheet",
    "thingspeak",
    "mariadb",
    "supabase",
    "sqlite",
    "opensearch",
)


@dataclass
class AlertRuntimeState:
    cooldown_seconds: float
    last_sent_at_by_key: dict[str, float] = field(default_factory=dict)

    def can_send(self, key: str, now: float | None = None) -> bool:
        current_time = now if now is not None else time.monotonic()
        last_sent_at = self.last_sent_at_by_key.get(key)

        if last_sent_at is not None:
            elapsed = current_time - last_sent_at
            if elapsed < self.cooldown_seconds:
                return False

        self.last_sent_at_by_key[key] = current_time
        return True


def parse_hex(value: str) -> bytes:
    return bytes.fromhex(value.replace(" ", ""))


def env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in ("1", "true", "yes", "y", "on")


def env_float(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def env_int(name: str, default: str) -> int:
    return int(os.getenv(name, default))


def parse_int_value(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_float_value(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_hhmm(value: str) -> datetime_time:
    try:
        parsed = datetime.strptime(value.strip(), "%H:%M")
    except ValueError as e:
        raise RuntimeError(f"Invalid HH:MM time value: {value}") from e

    return datetime_time(hour=parsed.hour, minute=parsed.minute)


def parse_optional_interval(value: str) -> float | None:
    interval_text = value.strip()

    if not interval_text:
        return None

    interval = float(interval_text)

    if interval <= 0:
        raise RuntimeError("COLLECT_INTERVAL must be greater than 0")

    return max(interval, MIN_COLLECT_INTERVAL_SECONDS)


def get_loop_interval(loop_enabled: bool, cli_interval: float | None) -> float | None:
    if cli_interval is not None:
        if cli_interval <= 0:
            raise RuntimeError("--interval must be greater than 0")

        return max(cli_interval, MIN_COLLECT_INTERVAL_SECONDS)

    if not loop_enabled:
        return None

    interval = parse_optional_interval(os.getenv("COLLECT_INTERVAL", ""))

    if interval is None:
        raise RuntimeError("COLLECT_INTERVAL is required when --loop is used")

    return interval


def parse_collector_sinks(value: str) -> set[str]:
    sink_text = value.strip()

    if not sink_text:
        return set()

    aliases = {
        "all": "all",
        "google_sheet": "google_sheet",
        "google-sheet": "google_sheet",
        "google_sheets": "google_sheet",
        "googlesheet": "google_sheet",
        "thingspeak": "thingspeak",
        "mariadb": "mariadb",
        "mysql": "mariadb",
        "supabase": "supabase",
        "postgres": "supabase",
        "postgresql": "supabase",
        "sqlite": "sqlite",
        "opensearch": "opensearch",
        "elasticsearch": "opensearch",
    }
    requested = {
        item.strip().lower().replace("-", "_")
        for item in sink_text.split(",")
        if item.strip()
    }

    sinks = set()
    invalid = []

    for sink in requested:
        canonical = aliases.get(sink)

        if canonical is None:
            invalid.append(sink)
            continue

        sinks.add(canonical)

    if invalid:
        warning_event(
            event="config_invalid_value",
            component="config",
            field="COLLECTOR_SINKS",
            invalid_values=sorted(invalid),
            supported_values=list(SUPPORTED_COLLECTOR_SINKS),
            action="skipped",
        )

    if "all" in sinks:
        return {"all"}

    return sinks


def has_cli_sink_flags(args: argparse.Namespace) -> bool:
    return any(
        [
            args.google_sheet,
            args.thingspeak,
            args.mariadb,
            args.supabase,
            args.sqlite,
            args.opensearch,
            args.all_sinks,
        ]
    )


def has_cli_alert_flags(args: argparse.Namespace) -> bool:
    return any([args.telegram, args.all_alerts])


def apply_sink_selection(args: argparse.Namespace) -> None:
    if has_cli_sink_flags(args):
        return

    sinks = parse_collector_sinks(os.getenv("COLLECTOR_SINKS", ""))

    if "all" in sinks:
        args.all_sinks = True
        return

    args.google_sheet = "google_sheet" in sinks
    args.thingspeak = "thingspeak" in sinks
    args.mariadb = "mariadb" in sinks
    args.supabase = "supabase" in sinks
    args.sqlite = "sqlite" in sinks
    args.opensearch = "opensearch" in sinks


def apply_alert_selection(args: argparse.Namespace) -> None:
    if has_cli_alert_flags(args):
        return

    channels = parse_alert_channels(os.getenv("ALERT_CHANNELS", ""))

    if "all" in channels:
        args.all_alerts = True
        return

    args.requested_alert_channels = channels


def get_requested_alert_channels(args: argparse.Namespace) -> set[str]:
    if args.all_alerts:
        return set(list_alert_handler_names())

    requested = set(getattr(args, "requested_alert_channels", set()))

    # Legacy explicit CLI flag kept for backward compatibility.
    if args.telegram:
        requested.add("telegram")

    return requested


def summarize_alert_result(result: dict) -> dict:
    summary: dict = {
        "alert_skipped": bool(result.get("skipped", False)),
    }

    if "chat_ids" in result:
        summary["alert_targets"] = len(result.get("chat_ids", []))

    summary_result = result.get("summary")
    if isinstance(summary_result, dict):
        summary["summary_sent_count"] = len(summary_result.get("sent", []))
        summary["summary_failed_count"] = len(summary_result.get("failed", []))

    fault_event_result = result.get("fault_event")
    if isinstance(fault_event_result, dict):
        summary["fault_event_sent_count"] = len(fault_event_result.get("sent", []))
        summary["fault_event_failed_count"] = len(fault_event_result.get("failed", []))

    sent_result = result.get("sent")
    failed_result = result.get("failed")
    if isinstance(sent_result, list):
        summary["sent_count"] = len(sent_result)
    if isinstance(failed_result, list):
        summary["failed_count"] = len(failed_result)

    return summary


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_fields() -> dict:
    return {
        "@timestamp": now_utc_iso(),
    }


def parse_utc_datetime(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


def has_fault_event(fault_code: int) -> bool:
    return bool(fault_code & FAULT_EVENT_MASK)


def is_operation_stopped_by_fault_code(fault_code: int) -> bool:
    return bool(fault_code & OPERATION_STOP_MASK)


def derive_operation_state(
    data: dict,
    previous_operation_stopped: bool | None,
    standby_power_w_threshold: float,
    normal_power_w_threshold: float,
) -> dict:
    fault_code = parse_int_value(data.get("fault_code"), 0)
    output_ac_power_w = parse_float_value(data.get("output_ac_power_w"), 0.0)

    if has_fault_event(fault_code):
        return {
            "operation_stopped": is_operation_stopped_by_fault_code(fault_code),
            "operation_state": "fault",
            "operation_state_reason": "fault_code_bit_1_plus",
        }

    if is_operation_stopped_by_fault_code(fault_code):
        return {
            "operation_stopped": True,
            "operation_state": "standby",
            "operation_state_reason": "fault_code_bit_0",
        }

    if output_ac_power_w <= standby_power_w_threshold:
        return {
            "operation_stopped": True,
            "operation_state": "standby",
            "operation_state_reason": "low_output_power",
        }

    if output_ac_power_w >= normal_power_w_threshold:
        return {
            "operation_stopped": False,
            "operation_state": "normal",
            "operation_state_reason": "output_power_recovered",
        }

    if previous_operation_stopped is True:
        return {
            "operation_stopped": True,
            "operation_state": "standby",
            "operation_state_reason": "hysteresis_keep_standby",
        }

    return {
        "operation_stopped": False,
        "operation_state": "normal",
        "operation_state_reason": "hysteresis_keep_normal",
    }


def apply_operation_state(
    data: dict,
    previous_operation_stopped: bool | None,
    standby_power_w_threshold: float,
    normal_power_w_threshold: float,
) -> dict:
    return {
        **data,
        **derive_operation_state(
            data=data,
            previous_operation_stopped=previous_operation_stopped,
            standby_power_w_threshold=standby_power_w_threshold,
            normal_power_w_threshold=normal_power_w_threshold,
        ),
    }


def build_collector_state(data: dict) -> dict:
    fault_code = parse_int_value(data.get("fault_code"), 0)
    operation_stopped = bool(
        data.get(
            "operation_stopped",
            is_operation_stopped_by_fault_code(fault_code),
        )
    )

    return {
        "updated_at": now_utc_iso(),
        "inverter_name": data.get("inverter_name", ""),
        "inverter_id": data.get("inverter_id"),
        "fault_code": fault_code,
        "operation_stopped": operation_stopped,
        "operation_state": data.get("operation_state", ""),
        "operation_state_reason": data.get("operation_state_reason", ""),
        "output_ac_power_w": data.get("output_ac_power_w"),
        "has_fault": has_fault_event(fault_code),
    }


def write_collector_state(state_path: Path, data: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_name(f"{state_path.name}.tmp")
    payload = json.dumps(
        build_collector_state(data),
        ensure_ascii=False,
        indent=2,
    )

    temp_path.write_text(payload + "\n", encoding="utf-8")
    os.replace(temp_path, state_path)


def read_collector_state(
    state_path: Path,
    max_age_seconds: float,
    now: datetime | None = None,
) -> dict | None:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None

    if not isinstance(state, dict):
        return None

    updated_at = state.get("updated_at")
    if not isinstance(updated_at, str):
        return None

    current_time = now or datetime.now(timezone.utc)
    age_seconds = (current_time - parse_utc_datetime(updated_at)).total_seconds()
    if age_seconds < 0 or age_seconds > max_age_seconds:
        return None

    return state


def is_no_response_error(error: Exception) -> bool:
    return str(error).startswith("No response from inverter")


def is_standby_state(state: dict | None) -> bool:
    if state is None:
        return False

    return bool(state.get("operation_stopped")) and not bool(state.get("has_fault"))


def should_suppress_unknown_state_no_response(
    process_started_at: float,
    suppress_seconds: float,
    now: float | None = None,
) -> bool:
    if suppress_seconds <= 0:
        return False

    current_time = now if now is not None else time.monotonic()
    elapsed = current_time - process_started_at
    return 0 <= elapsed < suppress_seconds


def is_time_in_window(
    current_time: datetime_time,
    start_time: datetime_time,
    end_time: datetime_time,
) -> bool:
    if start_time == end_time:
        return True

    if start_time < end_time:
        return start_time <= current_time < end_time

    return current_time >= start_time or current_time < end_time


def should_suppress_night_no_response(
    enabled: bool,
    timezone_name: str,
    start_time_text: str,
    end_time_text: str,
    now: datetime | None = None,
) -> tuple[bool, dict]:
    if not enabled:
        return False, {}

    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as e:
        raise RuntimeError(
            f"Invalid COLLECTOR_LOCAL_TIMEZONE: {timezone_name}"
        ) from e

    start_time = parse_hhmm(start_time_text)
    end_time = parse_hhmm(end_time_text)
    current_datetime = now or datetime.now(timezone.utc)
    local_datetime = current_datetime.astimezone(local_timezone)
    suppressed = is_time_in_window(
        current_time=local_datetime.time(),
        start_time=start_time,
        end_time=end_time,
    )

    return suppressed, {
        "local_timezone": timezone_name,
        "local_time": local_datetime.isoformat(),
        "night_start": start_time_text,
        "night_end": end_time_text,
    }


def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)


def print_section(title: str) -> None:
    print(f"\n== {title} ==", flush=True)


def print_section_json(title: str, data: dict) -> None:
    print_section(title)
    print_json(data)


def log_event(
    section: str,
    level: str,
    event: str,
    component: str,
    **fields,
) -> None:
    print_section_json(section, {
        **timestamp_fields(),
        "level": level,
        "event": event,
        "component": component,
        **fields,
    })


def warning_event(event: str, component: str, **fields) -> None:
    log_event(
        section=f"[Warning] {component}",
        level="warning",
        event=event,
        component=component,
        **fields,
    )


def print_sink_error(inverter_name: str, sink: str, error: Exception) -> None:
    log_event(
        section=f"[Sink] {sink}",
        level="error",
        event="sink_error",
        component="sink",
        inverter_name=inverter_name,
        sink=sink,
        error=str(error),
    )


def print_alert_error(inverter_name: str, alert: str, error: Exception) -> None:
    log_event(
        section=f"[Alert] {alert}",
        level="error",
        event="alert_error",
        component="alert",
        inverter_name=inverter_name,
        alert=alert,
        error=str(error),
    )


def handle_sink_error(
    inverter_name: str,
    alert_configs: dict[str, dict],
    data: dict,
    sink: str,
    error: Exception,
    alert_state: AlertRuntimeState,
    event: str = "sink_write_failed",
    log_error: bool = True,
) -> None:
    if log_error:
        print_sink_error(
            inverter_name=inverter_name,
            sink=sink,
            error=error,
        )

    telegram_config = alert_configs.get("telegram")
    if telegram_config is None:
        return

    cooldown_key = f"{event}:{sink}:{type(error).__name__}:{error}"
    if not alert_state.can_send(cooldown_key):
        log_event(
            section="[Alert] Telegram",
            level="warning",
            event="alert_suppressed",
            component="alert",
            inverter_name=inverter_name,
            alert="telegram",
            suppressed_event=event,
            sink=sink,
            reason="cooldown",
        )
        return

    try:
        alert_result = send_sink_error_alert(
            data=data,
            config=telegram_config,
            sink=sink,
            error=error,
            event=event,
        )
        log_event(
            section="[Alert] Telegram",
            level="warning" if alert_result.get("failed") else "info",
            event="alert_sent",
            component="alert",
            inverter_name=inverter_name,
            alert="telegram",
            alert_event=event,
            sink=sink,
            **summarize_alert_result(alert_result),
        )
    except Exception as e:
        print_alert_error(
            inverter_name=inverter_name,
            alert="telegram",
            error=e,
        )


def send_system_error_notification(
    inverter_name: str,
    alert_configs: dict[str, dict],
    data: dict,
    component: str,
    event: str,
    error: Exception,
    alert_state: AlertRuntimeState,
    failures: int | None = None,
) -> None:
    telegram_config = alert_configs.get("telegram")
    if telegram_config is None:
        return

    cooldown_key = f"{event}:{component}:{type(error).__name__}:{error}"
    if not alert_state.can_send(cooldown_key):
        log_event(
            section="[Alert] Telegram",
            level="warning",
            event="alert_suppressed",
            component="alert",
            inverter_name=inverter_name,
            alert="telegram",
            suppressed_event=event,
            reason="cooldown",
        )
        return

    try:
        alert_result = send_system_error_alert(
            data=data,
            config=telegram_config,
            component=component,
            event=event,
            error=error,
            failures=failures,
        )
        log_event(
            section="[Alert] Telegram",
            level="warning" if alert_result.get("failed") else "info",
            event="alert_sent",
            component="alert",
            inverter_name=inverter_name,
            alert="telegram",
            alert_event=event,
            **summarize_alert_result(alert_result),
        )
    except Exception as e:
        print_alert_error(
            inverter_name=inverter_name,
            alert="telegram",
            error=e,
        )


def send_system_recovered_notification(
    inverter_name: str,
    alert_configs: dict[str, dict],
    data: dict,
    component: str,
    event: str,
    failures: int,
) -> None:
    telegram_config = alert_configs.get("telegram")
    if telegram_config is None:
        return

    try:
        alert_result = send_system_recovered_alert(
            data=data,
            config=telegram_config,
            component=component,
            event=event,
            failures=failures,
        )
        log_event(
            section="[Alert] Telegram",
            level="warning" if alert_result.get("failed") else "info",
            event="alert_sent",
            component="alert",
            inverter_name=inverter_name,
            alert="telegram",
            alert_event=event,
            **summarize_alert_result(alert_result),
        )
    except Exception as e:
        print_alert_error(
            inverter_name=inverter_name,
            alert="telegram",
            error=e,
        )


def get_config_path() -> Path | None:
    system_config = Path("/etc") / CONFIG_FILENAME

    if system_config.is_file():
        return system_config

    current_config = Path.cwd() / CONFIG_FILENAME

    if current_config.is_file():
        return current_config

    return None


def print_config_template() -> None:
    template = files("solar_rs485_monitor").joinpath(CONFIG_TEMPLATE_FILENAME)
    print(template.read_text(encoding="utf-8"), end="")


def read_frame(
    port: str,
    baudrate: int,
    timeout: float,
    request: bytes,
    expected_frame_len: int,
) -> bytes:
    with serial.serial_for_url(
        url=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
    ) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ser.write(request)
        ser.flush()
        frame = ser.read(expected_frame_len)

    if not frame:
        raise RuntimeError("No response from inverter")

    return frame


def is_retryable_frame_error(error: Exception) -> bool:
    message = str(error)
    return message.startswith((
        "CRC mismatch",
        "Incomplete frame",
        "Invalid SOP",
        "No response from inverter",
    ))


def collect_once(
    port: str,
    baudrate: int,
    timeout: float,
    request: bytes,
    inverter_name: str,
    protocol: InverterProtocol,
    expected_inverter_id: int,
    expected_frame_len: int,
    expected_data_len: int,
    crc_order: str,
    verify_crc: bool,
    read_retries: int,
) -> dict:
    for attempt in range(read_retries + 1):
        try:
            frame = read_frame(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                request=request,
                expected_frame_len=expected_frame_len,
            )

            parsed = protocol.parse_frame(
                frame=frame,
                inverter_name=inverter_name,
                expected_inverter_id=expected_inverter_id,
                expected_frame_len=expected_frame_len,
                expected_data_len=expected_data_len,
                crc_order=crc_order,
                verify_crc=verify_crc,
            )
            return {
                **timestamp_fields(),
                **parsed,
            }

        except RuntimeError as e:
            if attempt >= read_retries or not is_retryable_frame_error(e):
                raise

            time.sleep(0.2)

    raise RuntimeError("Failed to collect inverter frame")


def main() -> None:
    config_path = get_config_path()
    if config_path is not None:
        load_dotenv(dotenv_path=config_path, override=True)

    parser = argparse.ArgumentParser(
        description="Solar inverter RS485 collector"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"solar-rs485-monitor {get_version()}",
    )

    parser.add_argument(
        "--print-config-template",
        action="store_true",
        help="Print the default configuration template and exit",
    )

    parser.add_argument(
        "-p",
        "--port",
        default=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"),
        help=(
            "Serial port or pyserial URL "
            "(e.g. /dev/ttyUSB0, socket://HOST:9600). "
            "default: /dev/ttyUSB0"
        ),
    )

    parser.add_argument(
        "-b",
        "--baudrate",
        type=int,
        default=int(os.getenv("SERIAL_BAUDRATE", "9600")),
        help="RS485 baudrate. default: 9600",
    )

    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=float(os.getenv("SERIAL_TIMEOUT", "1.0")),
        help="Serial read timeout seconds. default: 1.0",
    )

    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=None,
        help=(
            "Repeat collection interval seconds. "
            "Implies --loop and overrides COLLECT_INTERVAL. "
            "Minimum effective interval is 60 seconds."
        ),
    )

    parser.add_argument(
        "--loop",
        action="store_true",
        help=(
            "Repeat collection using COLLECT_INTERVAL from the config file. "
            "Minimum effective interval is 60 seconds."
        ),
    )

    parser.add_argument(
        "--google-sheet",
        action="store_true",
        help="Write collected data to Google Sheet",
    )

    parser.add_argument(
        "--thingspeak",
        action="store_true",
        help="Write collected data to ThingSpeak",
    )

    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Send fault alert messages to Telegram",
    )

    parser.add_argument(
        "--mariadb",
        action="store_true",
        help="Write collected data to MariaDB",
    )

    parser.add_argument(
        "--sqlite",
        action="store_true",
        help="Write collected data to SQLite",
    )

    parser.add_argument(
        "--supabase",
        action="store_true",
        help="Write collected data to Supabase PostgreSQL",
    )

    parser.add_argument(
        "--opensearch",
        action="store_true",
        help="Write collected data to OpenSearch or Elasticsearch",
    )

    parser.add_argument(
        "--all-sinks",
        action="store_true",
        help="Write collected data to all configured sinks",
    )

    parser.add_argument(
        "--all-alerts",
        action="store_true",
        help="Send alert messages to all configured alert channels",
    )

    args = parser.parse_args()

    if args.print_config_template:
        print_config_template()
        return

    protocol = get_protocol(
        os.getenv("INVERTER_PROTOCOL", "inoelectric_iepvs_g1_g2")
    )
    inverter_name = os.getenv("INVERTER_NAME", "Unknown Inverter")
    inverter_id = int(os.getenv("INVERTER_ID", "1"))
    request_hex = os.getenv("INVERTER_REQUEST_HEX", protocol.default_request_hex)

    if not request_hex:
        raise RuntimeError("INVERTER_REQUEST_HEX is not set")

    request = parse_hex(request_hex)
    frame_len = int(os.getenv(
        "INVERTER_FRAME_LENGTH",
        str(protocol.default_frame_length),
    ))
    data_len = int(os.getenv(
        "INVERTER_DATA_LENGTH",
        str(protocol.default_data_length),
    ))
    crc_order = os.getenv(
        "INVERTER_CRC_ORDER",
        protocol.default_crc_order,
    ).strip().upper()
    verify_crc = env_bool("INVERTER_VERIFY_CRC", "true")
    read_retries = int(os.getenv("SERIAL_READ_RETRIES", "2"))
    collect_interval = get_loop_interval(args.loop, args.interval)
    process_started_at = time.monotonic()
    alert_state = AlertRuntimeState(
        cooldown_seconds=max(
            0.0,
            env_float(
                "ALERT_COOLDOWN_SECONDS",
                str(DEFAULT_ALERT_COOLDOWN_SECONDS),
            ),
        )
    )
    collector_failure_alert_threshold = max(
        1,
        env_int(
            "COLLECTOR_FAILURE_ALERT_THRESHOLD",
            str(DEFAULT_COLLECTOR_FAILURE_ALERT_THRESHOLD),
        ),
    )
    collector_state_path = Path(os.getenv(
        "COLLECTOR_STATE_PATH",
        DEFAULT_COLLECTOR_STATE_PATH,
    )).expanduser()
    collector_state_max_age_seconds = max(
        0.0,
        env_float(
            "COLLECTOR_STATE_MAX_AGE_SECONDS",
            str(DEFAULT_COLLECTOR_STATE_MAX_AGE_SECONDS),
        ),
    )
    standby_no_response_suppress = env_bool(
        "COLLECTOR_STANDBY_NO_RESPONSE_SUPPRESS",
        "true",
    )
    standby_power_w_threshold = max(
        0.0,
        env_float(
            "COLLECTOR_STANDBY_POWER_W_THRESHOLD",
            str(DEFAULT_COLLECTOR_STANDBY_POWER_W_THRESHOLD),
        ),
    )
    normal_power_w_threshold = max(
        standby_power_w_threshold,
        env_float(
            "COLLECTOR_NORMAL_POWER_W_THRESHOLD",
            str(DEFAULT_COLLECTOR_NORMAL_POWER_W_THRESHOLD),
        ),
    )
    night_no_response_suppress = env_bool(
        "COLLECTOR_NIGHT_NO_RESPONSE_SUPPRESS",
        "true",
    )
    collector_local_timezone = os.getenv(
        "COLLECTOR_LOCAL_TIMEZONE",
        DEFAULT_COLLECTOR_LOCAL_TIMEZONE,
    ).strip()
    night_no_response_start = os.getenv(
        "COLLECTOR_NIGHT_NO_RESPONSE_START",
        DEFAULT_COLLECTOR_NIGHT_NO_RESPONSE_START,
    ).strip()
    night_no_response_end = os.getenv(
        "COLLECTOR_NIGHT_NO_RESPONSE_END",
        DEFAULT_COLLECTOR_NIGHT_NO_RESPONSE_END,
    ).strip()
    unknown_state_no_response_suppress_seconds = max(
        0.0,
        env_float(
            "COLLECTOR_UNKNOWN_STATE_NO_RESPONSE_SUPPRESS_SECONDS",
            str(DEFAULT_COLLECTOR_UNKNOWN_STATE_NO_RESPONSE_SUPPRESS_SECONDS),
        ),
    )

    apply_sink_selection(args)
    apply_alert_selection(args)

    if args.all_sinks:
        args.google_sheet = True
        args.thingspeak = True
        args.mariadb = True
        args.supabase = True
        args.sqlite = True
        args.opensearch = bool(os.getenv("OPENSEARCH_URL", "").strip())

    requested_alert_channels = get_requested_alert_channels(args)
    pending_sink_init_errors: list[tuple[str, Exception]] = []

    google_sheet_enabled = False
    if args.google_sheet:
        try:
            get_google_sheet()
            google_sheet_enabled = True
        except Exception as e:
            error = RuntimeError(f"initialization failed: {e}")
            print_sink_error(
                inverter_name=inverter_name,
                sink="google_sheet",
                error=error,
            )
            pending_sink_init_errors.append(("google_sheet", error))

    mariadb_config = None
    if args.mariadb:
        try:
            mariadb_config = get_mariadb_config()
        except Exception as e:
            error = RuntimeError(f"initialization failed: {e}")
            print_sink_error(
                inverter_name=inverter_name,
                sink="mariadb",
                error=error,
            )
            pending_sink_init_errors.append(("mariadb", error))

    sqlite_config = None
    if args.sqlite:
        try:
            sqlite_config = get_sqlite_config()
        except Exception as e:
            error = RuntimeError(f"initialization failed: {e}")
            print_sink_error(
                inverter_name=inverter_name,
                sink="sqlite",
                error=error,
            )
            pending_sink_init_errors.append(("sqlite", error))

    supabase_config = None
    if args.supabase:
        try:
            supabase_config = get_supabase_config()
        except Exception as e:
            error = RuntimeError(f"initialization failed: {e}")
            print_sink_error(
                inverter_name=inverter_name,
                sink="supabase",
                error=error,
            )
            pending_sink_init_errors.append(("supabase", error))

    opensearch_config = None
    if args.opensearch:
        try:
            opensearch_config = get_opensearch_config()
        except Exception as e:
            error = RuntimeError(f"initialization failed: {e}")
            print_sink_error(
                inverter_name=inverter_name,
                sink="opensearch",
                error=error,
            )
            pending_sink_init_errors.append(("opensearch", error))

    alert_configs: dict[str, dict] = {}
    for channel in sorted(requested_alert_channels):
        handler = get_alert_handler(channel)

        try:
            config = handler.get_config()

            if args.all_alerts and not handler.has_config(config):
                continue

            if not handler.has_config(config):
                raise RuntimeError(f"{channel} configuration is not set")

            alert_configs[channel] = config
        except Exception as e:
            print_alert_error(
                inverter_name=inverter_name,
                alert=channel,
                error=RuntimeError(f"initialization failed: {e}"),
            )

    for sink, error in pending_sink_init_errors:
        handle_sink_error(
            inverter_name=inverter_name,
            alert_configs=alert_configs,
            data={
                **timestamp_fields(),
                "inverter_name": inverter_name,
                "inverter_id": inverter_id,
            },
            sink=sink,
            error=error,
            alert_state=alert_state,
            event="sink_init_failed",
            log_error=False,
        )

    consecutive_collector_failures = 0
    previous_state = read_collector_state(
        collector_state_path,
        collector_state_max_age_seconds,
    )
    previous_operation_stopped = (
        bool(previous_state.get("operation_stopped"))
        if previous_state is not None
        else None
    )

    while True:
        try:
            result = collect_once(
                port=args.port,
                baudrate=args.baudrate,
                timeout=args.timeout,
                request=request,
                inverter_name=inverter_name,
                protocol=protocol,
                expected_inverter_id=inverter_id,
                expected_frame_len=frame_len,
                expected_data_len=data_len,
                crc_order=crc_order,
                verify_crc=verify_crc,
                read_retries=read_retries,
            )
            result = apply_operation_state(
                data=result,
                previous_operation_stopped=previous_operation_stopped,
                standby_power_w_threshold=standby_power_w_threshold,
                normal_power_w_threshold=normal_power_w_threshold,
            )
            previous_operation_stopped = bool(result["operation_stopped"])

            try:
                write_collector_state(collector_state_path, result)
            except Exception as e:
                warning_event(
                    event="collector_state_write_failed",
                    component="collector",
                    state_path=str(collector_state_path),
                    error=str(e),
                    action="continued",
                )

            if consecutive_collector_failures >= collector_failure_alert_threshold:
                send_system_recovered_notification(
                    inverter_name=inverter_name,
                    alert_configs=alert_configs,
                    data=result,
                    component="collector",
                    event="collector_recovered",
                    failures=consecutive_collector_failures,
                )

            consecutive_collector_failures = 0
            print_section_json("inverter", result)

            if google_sheet_enabled:
                try:
                    worksheet = get_google_sheet()
                    write_to_google_sheet(worksheet, result)
                    print_section_json("[Sink] Google Sheet", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "sink": "google_sheet",
                        "status": "written",
                    })
                except Exception as e:
                    handle_sink_error(
                        inverter_name=inverter_name,
                        alert_configs=alert_configs,
                        data=result,
                        sink="google_sheet",
                        error=e,
                        alert_state=alert_state,
                    )

            if args.thingspeak:
                try:
                    thingspeak_entry_id = write_to_thingspeak(
                        data=result,
                        api_key=os.getenv("THINGSPEAK_API_KEY", ""),
                        field_map=get_thingspeak_field_map(),
                        timeout=float(os.getenv("THINGSPEAK_TIMEOUT", "5.0")),
                    )
                    print_section_json("[Sink] ThingSpeak", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "sink": "thingspeak",
                        "thingspeak_entry_id": thingspeak_entry_id,
                    })
                except Exception as e:
                    handle_sink_error(
                        inverter_name=inverter_name,
                        alert_configs=alert_configs,
                        data=result,
                        sink="thingspeak",
                        error=e,
                        alert_state=alert_state,
                    )

            if mariadb_config is not None:
                try:
                    mariadb_insert_id = write_to_mariadb(
                        data=result,
                        config=mariadb_config,
                    )
                    print_section_json("[Sink] MariaDB", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "sink": "mariadb",
                        "mariadb_insert_id": mariadb_insert_id,
                    })
                except Exception as e:
                    handle_sink_error(
                        inverter_name=inverter_name,
                        alert_configs=alert_configs,
                        data=result,
                        sink="mariadb",
                        error=e,
                        alert_state=alert_state,
                    )

            if sqlite_config is not None:
                try:
                    sqlite_insert_id = write_to_sqlite(
                        data=result,
                        config=sqlite_config,
                    )
                    print_section_json("[Sink] SQLite", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "sink": "sqlite",
                        "sqlite_path": sqlite_config["path"],
                        "sqlite_insert_id": sqlite_insert_id,
                    })
                except Exception as e:
                    handle_sink_error(
                        inverter_name=inverter_name,
                        alert_configs=alert_configs,
                        data=result,
                        sink="sqlite",
                        error=e,
                        alert_state=alert_state,
                    )

            if opensearch_config is not None:
                try:
                    opensearch_result = write_to_opensearch(
                        data=result,
                        config=opensearch_config,
                    )
                    print_section_json("[Sink] Opensearch", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "sink": "opensearch",
                        "opensearch_index": opensearch_result["index"],
                        "opensearch_id": opensearch_result["id"],
                        "opensearch_result": opensearch_result["result"],
                    })
                except Exception as e:
                    handle_sink_error(
                        inverter_name=inverter_name,
                        alert_configs=alert_configs,
                        data=result,
                        sink="opensearch",
                        error=e,
                        alert_state=alert_state,
                    )

            if supabase_config is not None:
                try:
                    supabase_insert_id = write_to_supabase(
                        data=result,
                        config=supabase_config,
                    )
                    print_section_json("[Sink] Supabase", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "sink": "supabase",
                        "supabase_table": (
                            f"{supabase_config['schema']}."
                            f"{supabase_config['table']}"
                        ),
                        "supabase_insert_id": supabase_insert_id,
                    })
                except Exception as e:
                    handle_sink_error(
                        inverter_name=inverter_name,
                        alert_configs=alert_configs,
                        data=result,
                        sink="supabase",
                        error=e,
                        alert_state=alert_state,
                    )

            for channel, config in alert_configs.items():
                try:
                    handler = get_alert_handler(channel)
                    alert_result = handler.send(
                        data=result,
                        config=config,
                    )

                    alert_summary = summarize_alert_result(alert_result)
                    failed_count = (
                        alert_summary.get("failed_count", 0)
                        + alert_summary.get("summary_failed_count", 0)
                        + alert_summary.get("fault_event_failed_count", 0)
                    )
                    log_event(
                        section=f"[Alert] {channel.capitalize()}",
                        level="warning" if failed_count else "info",
                        event="alert_result",
                        component="alert",
                        inverter_name=inverter_name,
                        alert=channel,
                        **alert_summary,
                    )
                except Exception as e:
                    print_alert_error(
                        inverter_name=inverter_name,
                        alert=channel,
                        error=e,
                    )

        except Exception as e:
            if standby_no_response_suppress and is_no_response_error(e):
                state = read_collector_state(
                    collector_state_path,
                    collector_state_max_age_seconds,
                )
                if is_standby_state(state):
                    log_event(
                        section="[Collector]",
                        level="info",
                        event="collector_no_response_during_standby",
                        component="collector",
                        inverter_name=inverter_name,
                        state_path=str(collector_state_path),
                        action="system_alert_skipped",
                        error=str(e),
                    )
                    if collect_interval is None:
                        break

                    time.sleep(collect_interval)
                    continue

                if state is None and should_suppress_unknown_state_no_response(
                    process_started_at,
                    unknown_state_no_response_suppress_seconds,
                ):
                    log_event(
                        section="[Collector]",
                        level="info",
                        event="collector_no_response_unknown_state",
                        component="collector",
                        inverter_name=inverter_name,
                        state_path=str(collector_state_path),
                        action="system_alert_skipped",
                        error=str(e),
                    )
                    if collect_interval is None:
                        break

                    time.sleep(collect_interval)
                    continue

                try:
                    suppress_night, night_context = (
                        should_suppress_night_no_response(
                            enabled=night_no_response_suppress,
                            timezone_name=collector_local_timezone,
                            start_time_text=night_no_response_start,
                            end_time_text=night_no_response_end,
                        )
                    )
                except RuntimeError as night_error:
                    warning_event(
                        event="collector_night_suppress_config_invalid",
                        component="collector",
                        error=str(night_error),
                        action="night_suppress_disabled",
                    )
                    suppress_night = False
                    night_context = {}

                if suppress_night:
                    log_event(
                        section="[Collector]",
                        level="info",
                        event="collector_no_response_during_night",
                        component="collector",
                        inverter_name=inverter_name,
                        state_path=str(collector_state_path),
                        action="system_alert_skipped",
                        error=str(e),
                        **night_context,
                    )
                    if collect_interval is None:
                        break

                    time.sleep(collect_interval)
                    continue

            consecutive_collector_failures += 1
            failure_data = {
                **timestamp_fields(),
                "inverter_name": inverter_name,
                "inverter_id": inverter_id,
            }
            log_event(
                section="[Collector]",
                level="error",
                event="collector_failed",
                component="collector",
                inverter_name=inverter_name,
                failures=consecutive_collector_failures,
                error=str(e),
            )
            if consecutive_collector_failures >= collector_failure_alert_threshold:
                send_system_error_notification(
                    inverter_name=inverter_name,
                    alert_configs=alert_configs,
                    data=failure_data,
                    component="collector",
                    event="collector_failed",
                    error=e,
                    alert_state=alert_state,
                    failures=consecutive_collector_failures,
                )

        if collect_interval is None:
            break

        time.sleep(collect_interval)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

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
from solar_rs485_monitor.alerts.telegram import send_sink_error_alert
from solar_rs485_monitor.protocols import InverterProtocol, get_protocol
from solar_rs485_monitor.version import get_version

CONFIG_FILENAME = "solar-rs485-monitor.conf"
CONFIG_TEMPLATE_FILENAME = "solar-rs485-monitor.conf.template"
MIN_COLLECT_INTERVAL_SECONDS = 60.0
SUPPORTED_COLLECTOR_SINKS = (
    "all",
    "google_sheet",
    "thingspeak",
    "mariadb",
    "supabase",
    "sqlite",
    "opensearch",
)


def parse_hex(value: str) -> bytes:
    return bytes.fromhex(value.replace(" ", ""))


def env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in ("1", "true", "yes", "y", "on")


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

    if "all" in requested:
        return {"all"}

    sinks = set()
    invalid = []

    for sink in requested:
        canonical = aliases.get(sink)

        if canonical is None:
            invalid.append(sink)
            continue

        sinks.add(canonical)

    if invalid:
        print(
            "WARNING: Ignoring invalid COLLECTOR_SINKS value(s): "
            + ", ".join(sorted(invalid))
            + ". Supported values: "
            + ", ".join(SUPPORTED_COLLECTOR_SINKS),
            file=sys.stderr,
            flush=True,
        )

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


def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)


def print_section(title: str) -> None:
    print(f"\n== {title} ==", flush=True)


def print_section_json(title: str, data: dict) -> None:
    print_section(title)
    print_json(data)


def print_sink_error(inverter_name: str, sink: str, error: Exception) -> None:
    print_section_json(sink, {
        **timestamp_fields(),
        "inverter_name": inverter_name,
        "sink": sink,
        "error": str(error),
    })


def print_alert_error(inverter_name: str, alert: str, error: Exception) -> None:
    print_section_json(alert, {
        **timestamp_fields(),
        "inverter_name": inverter_name,
        "alert": alert,
        "error": str(error),
    })


def handle_sink_error(
    inverter_name: str,
    alert_configs: dict[str, dict],
    data: dict,
    sink: str,
    error: Exception,
) -> None:
    print_sink_error(
        inverter_name=inverter_name,
        sink=sink,
        error=error,
    )

    telegram_config = alert_configs.get("telegram")
    if telegram_config is None:
        return

    try:
        alert_result = send_sink_error_alert(
            data=data,
            config=telegram_config,
            sink=sink,
            error=error,
        )
        print_section_json("[Alert] Telegram", {
            **timestamp_fields(),
            "inverter_name": inverter_name,
            "alert": "telegram",
            "event": "sink_insert_failed",
            "sink": sink,
            **summarize_alert_result(alert_result),
        })
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

    google_sheet_enabled = False
    if args.google_sheet:
        try:
            get_google_sheet()
            google_sheet_enabled = True
        except Exception as e:
            print_sink_error(
                inverter_name=inverter_name,
                sink="google_sheet",
                error=RuntimeError(f"initialization failed: {e}"),
            )

    mariadb_config = None
    if args.mariadb:
        try:
            mariadb_config = get_mariadb_config()
        except Exception as e:
            print_sink_error(
                inverter_name=inverter_name,
                sink="mariadb",
                error=RuntimeError(f"initialization failed: {e}"),
            )

    sqlite_config = None
    if args.sqlite:
        try:
            sqlite_config = get_sqlite_config()
        except Exception as e:
            print_sink_error(
                inverter_name=inverter_name,
                sink="sqlite",
                error=RuntimeError(f"initialization failed: {e}"),
            )

    supabase_config = None
    if args.supabase:
        try:
            supabase_config = get_supabase_config()
        except Exception as e:
            print_sink_error(
                inverter_name=inverter_name,
                sink="supabase",
                error=RuntimeError(f"initialization failed: {e}"),
            )

    opensearch_config = None
    if args.opensearch:
        try:
            opensearch_config = get_opensearch_config()
        except Exception as e:
            print_sink_error(
                inverter_name=inverter_name,
                sink="opensearch",
                error=RuntimeError(f"initialization failed: {e}"),
            )

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
                    )

            for channel, config in alert_configs.items():
                try:
                    handler = get_alert_handler(channel)
                    alert_result = handler.send(
                        data=result,
                        config=config,
                    )

                    print_section_json(f"[Alert] {channel.capitalize()}", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "alert": channel,
                        **summarize_alert_result(alert_result),
                    })
                except Exception as e:
                    print_alert_error(
                        inverter_name=inverter_name,
                        alert=channel,
                        error=e,
                    )

        except Exception as e:
            print_section_json("[Collector] JSON Raw-Data", {
                **timestamp_fields(),
                "inverter_name": inverter_name,
                "error": str(e),
            })

        if collect_interval is None:
            break

        time.sleep(collect_interval)


if __name__ == "__main__":
    main()

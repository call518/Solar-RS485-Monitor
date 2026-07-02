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
from solar_rs485_monitor.sinks.sqlite import (
    get_sqlite_config,
    write_to_sqlite,
)
from solar_rs485_monitor.sinks.thingspeak import (
    get_field_map as get_thingspeak_field_map,
    write_to_thingspeak,
)
from solar_rs485_monitor.alerts.telegram import (
    get_telegram_config,
    has_telegram_config,
    write_to_telegram,
)
from solar_rs485_monitor.version import get_version

CONFIG_FILENAME = "solar-rs485-monitor.conf"
CONFIG_TEMPLATE_FILENAME = "solar-rs485-monitor.conf.template"
MIN_COLLECT_INTERVAL_SECONDS = 10.0
# Fault status bit mask from remote monitoring table (Bit 1-12).
FAULT_STATUS_MASK = 0x1FFE


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "big")


def u64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 8], "big")


def modbus_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


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
        "google-sheet": "google_sheet",
        "google_sheets": "google_sheet",
        "googlesheet": "google_sheet",
        "thingspeak": "thingspeak",
        "mariadb": "mariadb",
        "mysql": "mariadb",
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
        raise RuntimeError(
            "Invalid COLLECTOR_SINKS value(s): "
            + ", ".join(sorted(invalid))
        )

    return sinks


def parse_alert_channels(value: str) -> set[str]:
    channel_text = value.strip()

    if not channel_text:
        return set()

    aliases = {
        "telegram": "telegram",
        "tg": "telegram",
    }
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


def has_cli_sink_flags(args: argparse.Namespace) -> bool:
    return any(
        [
            args.google_sheet,
            args.thingspeak,
            args.mariadb,
            args.sqlite,
            args.opensearch,
            args.all_sinks,
        ]
    )


def has_cli_alert_flags(args: argparse.Namespace) -> bool:
    return any(
        [
            args.telegram,
            args.all_alerts,
        ]
    )


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
    args.sqlite = "sqlite" in sinks
    args.opensearch = "opensearch" in sinks


def apply_alert_selection(args: argparse.Namespace) -> None:
    if has_cli_alert_flags(args):
        return

    channels = parse_alert_channels(os.getenv("ALERT_CHANNELS", ""))

    if "all" in channels:
        args.all_alerts = True
        return

    args.telegram = "telegram" in channels


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


def get_crc_from_frame(frame: bytes, crc_order: str) -> int:
    crc_bytes = frame[-2:]

    if crc_order == "LH":
        return crc_bytes[0] | (crc_bytes[1] << 8)

    if crc_order == "HL":
        return (crc_bytes[0] << 8) | crc_bytes[1]

    raise RuntimeError(f"Invalid INVERTER_CRC_ORDER: {crc_order}")


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


def parse_frame(
    frame: bytes,
    inverter_name: str,
    expected_inverter_id: int,
    expected_frame_len: int,
    expected_data_len: int,
    crc_order: str,
    verify_crc: bool,
) -> dict:
    if len(frame) < expected_frame_len:
        raise RuntimeError(
            f"Incomplete frame: {len(frame)} bytes "
            f"raw_frame_hex={frame.hex(' ')}"
        )

    if verify_crc:
        received_crc = get_crc_from_frame(frame, crc_order)
        calculated_crc = modbus_crc16(frame[:-2])

        if received_crc != calculated_crc:
            raise RuntimeError(
                "CRC mismatch "
                f"received=0x{received_crc:04x} "
                f"calculated=0x{calculated_crc:04x} "
                f"frame_len={len(frame)} "
                f"raw_frame_hex={frame.hex(' ')}"
            )

    if frame[0] != 0x7E:
        raise RuntimeError(
            f"Invalid SOP: 0x{frame[0]:02x} "
            f"raw_frame_hex={frame.hex(' ')}"
        )

    inverter_id = frame[1]
    command = frame[2]
    data_len = int.from_bytes(frame[3:5], "big")

    if inverter_id != expected_inverter_id:
        raise RuntimeError(f"Unexpected inverter_id: {inverter_id}")

    if command != 0x02:
        raise RuntimeError(f"Unexpected command: 0x{command:02x}")

    if data_len != expected_data_len:
        raise RuntimeError(f"Unexpected data length: {data_len}")

    data = frame[5:5 + data_len]
    fault_code = u16(data, 24)

    return {
        **timestamp_fields(),
        "inverter_name": inverter_name,
        "inverter_id": inverter_id,
        "input_dc_voltage_v": u16(data, 0),
        "input_dc_current_a": u16(data, 2),
        "input_dc_power_w": u16(data, 4),
        "output_ac_voltage_v": u16(data, 6),
        "output_ac_current_a": u16(data, 8),
        "output_ac_power_w": u16(data, 10),
        "output_ac_power_factor_pct": u16(data, 12) / 10.0,
        "output_ac_frequency_hz": u16(data, 14) / 10.0,
        "total_generation_kwh": u64(data, 16) / 1000.0,
        "fault_code": fault_code,
        "fault": 1 if (fault_code & FAULT_STATUS_MASK) != 0 else 0,
        "raw_frame_hex": frame.hex(" "),
    }


def collect_once(
    port: str,
    baudrate: int,
    timeout: float,
    request: bytes,
    inverter_name: str,
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

            return parse_frame(
                frame=frame,
                inverter_name=inverter_name,
                expected_inverter_id=expected_inverter_id,
                expected_frame_len=expected_frame_len,
                expected_data_len=expected_data_len,
                crc_order=crc_order,
                verify_crc=verify_crc,
            )

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
            "Minimum effective interval is 10 seconds."
        ),
    )

    parser.add_argument(
        "--loop",
        action="store_true",
        help=(
            "Repeat collection using COLLECT_INTERVAL from the config file. "
            "Minimum effective interval is 10 seconds."
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

    inverter_name = os.getenv("INVERTER_NAME", "Unknown Inverter")
    inverter_id = int(os.getenv("INVERTER_ID", "1"))
    request_hex = os.getenv("INVERTER_REQUEST_HEX")

    if not request_hex:
        raise RuntimeError("INVERTER_REQUEST_HEX is not set")

    request = parse_hex(request_hex)
    frame_len = int(os.getenv("INVERTER_FRAME_LENGTH", "33"))
    data_len = int(os.getenv("INVERTER_DATA_LENGTH", "26"))
    crc_order = os.getenv("INVERTER_CRC_ORDER", "LH").strip().upper()
    verify_crc = env_bool("INVERTER_VERIFY_CRC", "true")
    read_retries = int(os.getenv("SERIAL_READ_RETRIES", "2"))
    collect_interval = get_loop_interval(args.loop, args.interval)

    apply_sink_selection(args)
    apply_alert_selection(args)

    if args.all_sinks:
        args.google_sheet = True
        args.thingspeak = True
        args.mariadb = True
        args.sqlite = True
        args.opensearch = bool(os.getenv("OPENSEARCH_URL", "").strip())

    if args.all_alerts:
        args.telegram = has_telegram_config(get_telegram_config())

    worksheet = None
    if args.google_sheet:
        try:
            worksheet = get_google_sheet()
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

    telegram_config = None
    if args.telegram:
        try:
            telegram_config = get_telegram_config()
        except Exception as e:
            print_alert_error(
                inverter_name=inverter_name,
                alert="telegram",
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
                expected_inverter_id=inverter_id,
                expected_frame_len=frame_len,
                expected_data_len=data_len,
                crc_order=crc_order,
                verify_crc=verify_crc,
                read_retries=read_retries,
            )

            print_section_json("inverter", result)

            if worksheet is not None:
                try:
                    write_to_google_sheet(worksheet, result)
                    print_section_json("[Sink] Google Sheet", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "sink": "google_sheet",
                        "status": "written",
                    })
                except Exception as e:
                    print_sink_error(
                        inverter_name=inverter_name,
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
                    print_sink_error(
                        inverter_name=inverter_name,
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
                    print_sink_error(
                        inverter_name=inverter_name,
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
                    print_sink_error(
                        inverter_name=inverter_name,
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
                    print_sink_error(
                        inverter_name=inverter_name,
                        sink="opensearch",
                        error=e,
                    )

            if telegram_config is not None:
                try:
                    telegram_result = write_to_telegram(
                        data=result,
                        config=telegram_config,
                    )
                    summary_result = telegram_result.get("summary") or {}
                    fault_event_result = telegram_result.get("fault_event") or {}
                    print_section_json("[Alert] Telegram", {
                        **timestamp_fields(),
                        "inverter_name": inverter_name,
                        "alert": "telegram",
                        "telegram_chat_targets": len(telegram_result.get("chat_ids", [])),
                        "telegram_summary_sent_count": len(summary_result.get("sent", [])),
                        "telegram_summary_failed_count": len(summary_result.get("failed", [])),
                        "telegram_fault_event_sent_count": len(fault_event_result.get("sent", [])),
                        "telegram_fault_event_failed_count": len(fault_event_result.get("failed", [])),
                        "telegram_skipped": bool(telegram_result.get("skipped", False)),
                    })
                except Exception as e:
                    print_alert_error(
                        inverter_name=inverter_name,
                        alert="telegram",
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

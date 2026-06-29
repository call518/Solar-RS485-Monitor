#!/usr/bin/env python3

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

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
from solar_rs485_monitor.sinks.thingspeak import (
    get_field_map as get_thingspeak_field_map,
    write_to_thingspeak,
)


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


def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)


def print_sink_error(inverter_name: str, sink: str, error: Exception) -> None:
    print_json({
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "inverter_name": inverter_name,
        "sink": sink,
        "error": str(error),
    })


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
        raise RuntimeError(f"Incomplete frame: {len(frame)} bytes")

    if verify_crc:
        received_crc = get_crc_from_frame(frame, crc_order)
        calculated_crc = modbus_crc16(frame[:-2])

        if received_crc != calculated_crc:
            raise RuntimeError(
                "CRC mismatch "
                f"received=0x{received_crc:04x} "
                f"calculated=0x{calculated_crc:04x}"
            )

    if frame[0] != 0x7E:
        raise RuntimeError(f"Invalid SOP: 0x{frame[0]:02x}")

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
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "inverter_name": inverter_name,
        "inverter_id": inverter_id,
        "pv_voltage_v": u16(data, 0),
        "pv_current_a": u16(data, 2),
        "pv_power_w": u16(data, 4),
        "grid_voltage_v": u16(data, 6),
        "grid_current_a": u16(data, 8),
        "current_output_w": u16(data, 10),
        "power_factor_pct": u16(data, 12) / 10.0,
        "frequency_hz": u16(data, 14) / 10.0,
        "total_generation_kwh": u64(data, 16) / 1000.0,
        "fault_code": fault_code,
        "fault": fault_code != 0,
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
) -> dict:
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


def main() -> None:
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)

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

    parser = argparse.ArgumentParser(
        description="Solar inverter RS485 collector"
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
        help="Repeat collection interval seconds. If omitted, collect once.",
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
        "--mariadb",
        action="store_true",
        help="Write collected data to MariaDB",
    )

    args = parser.parse_args()

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
            )

            print_json(result)

            if worksheet is not None:
                try:
                    write_to_google_sheet(worksheet, result)
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
                    print_json({
                        "@timestamp": datetime.now(timezone.utc).isoformat(),
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
                    print_json({
                        "@timestamp": datetime.now(timezone.utc).isoformat(),
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

        except Exception as e:
            print_json({
                "@timestamp": datetime.now(timezone.utc).isoformat(),
                "inverter_name": inverter_name,
                "error": str(e),
            })

        if args.interval is None:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()

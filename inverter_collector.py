#!/usr/bin/env python3

import argparse
import json
import time
from datetime import datetime, timezone

import serial


REQUEST = bytes.fromhex("7e 01 01 d1 88")

EXPECTED_INVERTER_ID = 1
EXPECTED_FRAME_LEN = 33
EXPECTED_DATA_LEN = 26


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "big")


def u64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 8], "big")


def read_frame(port: str, baudrate: int, timeout: float) -> bytes:
    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
    ) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        ser.write(REQUEST)
        ser.flush()

        frame = ser.read(EXPECTED_FRAME_LEN)

    if not frame:
        raise RuntimeError("No response from inverter")

    return frame


def parse_frame(frame: bytes) -> dict:
    if len(frame) < EXPECTED_FRAME_LEN:
        raise RuntimeError(f"Incomplete frame: {len(frame)} bytes")

    if frame[0] != 0x7E:
        raise RuntimeError(f"Invalid SOP: 0x{frame[0]:02x}")

    inverter_id = frame[1]
    command = frame[2]
    data_len = int.from_bytes(frame[3:5], "big")

    if inverter_id != EXPECTED_INVERTER_ID:
        raise RuntimeError(f"Unexpected inverter_id: {inverter_id}")

    if command != 0x02:
        raise RuntimeError(f"Unexpected command: 0x{command:02x}")

    if data_len != EXPECTED_DATA_LEN:
        raise RuntimeError(f"Unexpected data length: {data_len}")

    data_start = 5
    data_end = data_start + data_len
    data = frame[data_start:data_end]

    fault_code = u16(data, 24)

    return {
        "@timestamp": datetime.now(timezone.utc).isoformat(),

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


def collect_once(port: str, baudrate: int, timeout: float) -> dict:
    frame = read_frame(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
    )

    return parse_frame(frame)


def print_json(data: dict) -> None:
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Solar inverter RS485 collector"
    )

    parser.add_argument(
        "-p",
        "--port",
        default="/dev/ttyUSB0",
        help="Serial port. default: /dev/ttyUSB0",
    )

    parser.add_argument(
        "-b",
        "--baudrate",
        type=int,
        default=9600,
        help="RS485 baudrate. default: 9600",
    )

    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=1.0,
        help="Serial read timeout seconds. default: 1.0",
    )

    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=None,
        help="Repeat collection interval seconds. If omitted, collect once.",
    )

    args = parser.parse_args()

    while True:
        try:
            result = collect_once(
                port=args.port,
                baudrate=args.baudrate,
                timeout=args.timeout,
            )
            print_json(result)

        except Exception as e:
            print_json(
                {
                    "@timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }
            )

        if args.interval is None:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()

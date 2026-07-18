import argparse
import time

from solar_rs485_monitor.protocols import get_protocol
from solar_rs485_monitor.protocols.inoelectric_iepvs_g1_g2 import crc16


DEFAULT_BAUDRATES = "9600,19200,38400,4800,115200"


def parse_hex(value: str) -> bytes:
    return bytes.fromhex(value.replace(" ", ""))


def parse_baudrates(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def format_request_with_crc(base: bytes, crc_order: str) -> bytes:
    crc = crc16(base)

    if crc_order == "HL":
        return base + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    if crc_order == "LH":
        return base + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    raise RuntimeError(f"Invalid CRC order: {crc_order}")


def build_requests(
    request: bytes,
    slave_id: int | None,
    default_crc_order: str,
    try_crc_orders: bool,
) -> list[tuple[str, bytes]]:
    if len(request) < 3:
        raise RuntimeError("Request frame must contain at least SOP, ID, and command")

    base = bytearray(request[:-2] if len(request) >= 5 else request)
    if slave_id is not None:
        base[1] = slave_id

    if try_crc_orders:
        return [
            ("CRC High/Low", format_request_with_crc(bytes(base), "HL")),
            ("CRC Low/High", format_request_with_crc(bytes(base), "LH")),
        ]

    if slave_id is not None:
        return [
            (
                f"selected request, CRC {default_crc_order}",
                format_request_with_crc(bytes(base), default_crc_order),
            )
        ]

    return [("selected request", request)]


def capture_once(
    port: str,
    baudrate: int,
    timeout: float,
    delay: float,
    read_bytes: int,
    requests: list[tuple[str, bytes]],
) -> None:
    import serial

    print(f"\n=== baudrate={baudrate} ===")

    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
    ) as ser:
        for label, request in requests:
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            print(f"TX ({label}):", request.hex(" "))
            ser.write(request)
            ser.flush()

            time.sleep(delay)
            response = ser.read(read_bytes)

            if response:
                print("RX:", response.hex(" "))
            else:
                print("RX: no response")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture raw RS485 inverter response frames."
    )
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--protocol", default="inoelectric_iepvs_g1_g2")
    parser.add_argument("--slave-id", type=int)
    parser.add_argument("--request-hex")
    parser.add_argument("--baudrates", default=DEFAULT_BAUDRATES)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--read-bytes", type=int, default=128)
    parser.add_argument(
        "--try-crc-orders",
        action="store_true",
        help="Try both CRC High/Low and Low/High request byte orders.",
    )
    args = parser.parse_args()

    protocol = get_protocol(args.protocol)
    request_hex = args.request_hex or protocol.default_request_hex
    requests = build_requests(
        request=parse_hex(request_hex),
        slave_id=args.slave_id,
        default_crc_order=protocol.default_crc_order,
        try_crc_orders=args.try_crc_orders,
    )

    for baudrate in parse_baudrates(args.baudrates):
        try:
            capture_once(
                port=args.port,
                baudrate=baudrate,
                timeout=args.timeout,
                delay=args.delay,
                read_bytes=args.read_bytes,
                requests=requests,
            )
        except Exception as error:
            print(f"error at {baudrate}: {error}")


if __name__ == "__main__":
    main()

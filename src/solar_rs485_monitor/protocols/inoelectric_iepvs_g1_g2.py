from solar_rs485_monitor.protocols.base import InverterProtocol


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "big")


def u64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 8], "big")


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def get_crc_from_frame(frame: bytes, crc_order: str) -> int:
    crc_bytes = frame[-2:]

    if crc_order == "LH":
        return crc_bytes[0] | (crc_bytes[1] << 8)

    if crc_order == "HL":
        return (crc_bytes[0] << 8) | crc_bytes[1]

    raise RuntimeError(f"Invalid INVERTER_CRC_ORDER: {crc_order}")


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
        calculated_crc = crc16(frame[:-2])

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
        "raw_frame_hex": frame.hex(" "),
    }


PROTOCOL = InverterProtocol(
    name="inoelectric_iepvs_g1_g2",
    aliases=(
        "inoelectric",
        "iepvs",
        "iepvs_g1_g2",
        "inoelectric_iepvs",
        "inoelectric_iepvs_3_5_g1_g2",
    ),
    default_request_hex="7e0101d188",
    default_frame_length=33,
    default_data_length=26,
    default_crc_order="LH",
    parse_frame=parse_frame,
)

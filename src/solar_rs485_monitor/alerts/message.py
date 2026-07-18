def parse_int_value(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def has_fault_event(fault_code: int) -> bool:
    # Bit 0 is operation/standby state and is not treated as a fault event.
    return (fault_code & 0xFFFE) != 0


def format_active_bits(fault_code: int) -> str:
    if fault_code <= 0:
        return "-"

    bits = [f"Bit {bit}" for bit in range(16) if fault_code & (1 << bit)]
    return ", ".join(bits) if bits else "-"


def build_summary_message(data: dict) -> str:
    fault_code = parse_int_value(data.get("fault_code"), 0)
    fault = 1 if has_fault_event(fault_code) else 0
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
    fault = 1 if has_fault_event(fault_code) else 0
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


def build_sink_error_message(data: dict, sink: str, error: Exception) -> str:
    return "\n".join(
        [
            f"*Solar RS485 Sink Insert Failed: {sink}*",
            f"Time: `{data.get('@timestamp', '-')}`",
            f"Inverter: `{data.get('inverter_name', '-')}` (ID `{data.get('inverter_id', '-')}`)",
            f"Sink: `{sink}`",
            f"Error: `{str(error)}`",
            "",
            f"Total: `{data.get('total_generation_kwh', '-')}` kWh",
            f"Fault code: `{data.get('fault_code', '-')}`",
        ]
    )

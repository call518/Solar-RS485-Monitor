import re


MAX_ERROR_MESSAGE_LENGTH = 500
GOOGLE_SHEET_SINK_NAMES = {"google_sheet", "google_sheets", "googlesheet"}
GOOGLE_SHEET_STATUS_RE = re.compile(r"(?:status=|error\s+)(\d{3})", re.IGNORECASE)


def parse_int_value(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def has_fault_event(fault_code: int) -> bool:
    # Bit 0 is operation/standby state and is not treated as a fault event.
    return (fault_code & 0xFFFE) != 0


def format_code(value) -> str:
    text = str(value).replace("`", "'")
    return f"`{text}`"


def format_error(error: Exception) -> str:
    text = " ".join(str(error).replace("`", "'").split())
    if len(text) > MAX_ERROR_MESSAGE_LENGTH:
        text = f"{text[:MAX_ERROR_MESSAGE_LENGTH]}..."
    return f"`{text}`"


def extract_google_sheet_status(error: Exception) -> str:
    match = GOOGLE_SHEET_STATUS_RE.search(str(error))
    return match.group(1) if match else "-"


def is_google_sheet_sink(sink: str) -> bool:
    return sink.strip().lower() in GOOGLE_SHEET_SINK_NAMES


def get_sink_error_title(sink: str, event: str) -> str:
    action_titles = {
        "sink_init_failed": "Initialization Failed",
        "sink_write_failed": "Write Failed",
        "sink_insert_failed": "Insert Failed",
    }
    action = action_titles.get(event, "Error")

    if is_google_sheet_sink(sink):
        return f"Solar RS485 Google Sheets {action}"

    return f"Solar RS485 Sink {action}: {sink}"


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
            f"Time: {format_code(data.get('@timestamp', '-'))}",
            f"Inverter: {format_code(data.get('inverter_name', '-'))} "
            f"(ID {format_code(data.get('inverter_id', '-'))})",
            f"Fault: {format_code(fault)}",
            f"Fault code: {format_code(fault_code)}",
            f"Active bits: {format_code(active_bits)}",
            "",
            "*DC Input*",
            f"- Voltage: {format_code(data.get('input_dc_voltage_v', '-'))} V",
            f"- Current: {format_code(data.get('input_dc_current_a', '-'))} A",
            f"- Power: {format_code(data.get('input_dc_power_w', '-'))} W",
            "",
            "*AC Output*",
            f"- Voltage: {format_code(data.get('output_ac_voltage_v', '-'))} V",
            f"- Current: {format_code(data.get('output_ac_current_a', '-'))} A",
            f"- Power: {format_code(data.get('output_ac_power_w', '-'))} W",
            f"- Power factor: "
            f"{format_code(data.get('output_ac_power_factor_pct', '-'))} %",
            f"- Frequency: {format_code(data.get('output_ac_frequency_hz', '-'))} Hz",
            "",
            f"Total: {format_code(data.get('total_generation_kwh', '-'))} kWh",
            f"Raw frame: {format_code(data.get('raw_frame_hex', '-'))}",
        ]
    )


def build_fault_event_message(data: dict) -> str:
    fault_code = parse_int_value(data.get("fault_code"), 0)
    fault = 1 if has_fault_event(fault_code) else 0
    active_bits = format_active_bits(fault_code)

    return "\n".join(
        [
            "*Solar RS485 Fault Event*",
            f"Time: {format_code(data.get('@timestamp', '-'))}",
            f"Inverter: {format_code(data.get('inverter_name', '-'))} "
            f"(ID {format_code(data.get('inverter_id', '-'))})",
            f"Fault: {format_code(fault)}",
            f"Fault code: {format_code(fault_code)}",
            f"Active bits: {format_code(active_bits)}",
            "",
            "*DC Input*",
            f"- Voltage: {format_code(data.get('input_dc_voltage_v', '-'))} V",
            f"- Current: {format_code(data.get('input_dc_current_a', '-'))} A",
            f"- Power: {format_code(data.get('input_dc_power_w', '-'))} W",
            "",
            "*AC Output*",
            f"- Voltage: {format_code(data.get('output_ac_voltage_v', '-'))} V",
            f"- Current: {format_code(data.get('output_ac_current_a', '-'))} A",
            f"- Power: {format_code(data.get('output_ac_power_w', '-'))} W",
            f"- Power factor: "
            f"{format_code(data.get('output_ac_power_factor_pct', '-'))} %",
            f"- Frequency: {format_code(data.get('output_ac_frequency_hz', '-'))} Hz",
            "",
            f"Total: {format_code(data.get('total_generation_kwh', '-'))} kWh",
            f"Raw frame: {format_code(data.get('raw_frame_hex', '-'))}",
        ]
    )


def build_sink_error_message(
    data: dict,
    sink: str,
    error: Exception,
    event: str = "sink_insert_failed",
) -> str:
    title = get_sink_error_title(sink=sink, event=event)
    sink_lines = [f"Sink: {format_code(sink)}"]

    if is_google_sheet_sink(sink):
        sink_lines.append(
            f"Google Sheets status: {format_code(extract_google_sheet_status(error))}"
        )

    return "\n".join(
        [
            f"*{title}*",
            f"Time: {format_code(data.get('@timestamp', '-'))}",
            f"Inverter: {format_code(data.get('inverter_name', '-'))} "
            f"(ID {format_code(data.get('inverter_id', '-'))})",
            *sink_lines,
            f"Error: {format_error(error)}",
            "",
            f"Total: {format_code(data.get('total_generation_kwh', '-'))} kWh",
            f"Fault code: {format_code(data.get('fault_code', '-'))}",
        ]
    )


def build_system_error_message(
    data: dict,
    component: str,
    event: str,
    error: Exception,
    failures: int | None = None,
) -> str:
    lines = [
        "*Solar RS485 System Error*",
        f"Time: {format_code(data.get('@timestamp', '-'))}",
        f"Inverter: {format_code(data.get('inverter_name', '-'))}",
        f"Component: {format_code(component)}",
        f"Event: {format_code(event)}",
        f"Error: {format_error(error)}",
    ]

    if failures is not None:
        lines.append(f"Consecutive failures: {format_code(failures)}")

    return "\n".join(lines)


def build_system_recovered_message(
    data: dict,
    component: str,
    event: str,
    failures: int,
) -> str:
    return "\n".join(
        [
            "*Solar RS485 System Recovered*",
            f"Time: {format_code(data.get('@timestamp', '-'))}",
            f"Inverter: {format_code(data.get('inverter_name', '-'))}",
            f"Component: {format_code(component)}",
            f"Event: {format_code(event)}",
            f"Recovered after failures: {format_code(failures)}",
        ]
    )

from solar_rs485_monitor.alerts.message import (
    build_fault_event_message,
    build_system_error_message,
    format_active_bits,
    has_fault_event,
)


def make_data(fault_code: int) -> dict:
    return {
        "@timestamp": "2026-07-08T06:00:00+09:00",
        "inverter_name": "bad`name",
        "inverter_id": 1,
        "input_dc_voltage_v": 193,
        "input_dc_current_a": 0,
        "input_dc_power_w": 54,
        "output_ac_voltage_v": 229,
        "output_ac_current_a": 0,
        "output_ac_power_w": 37,
        "output_ac_power_factor_pct": 85.0,
        "output_ac_frequency_hz": 60.0,
        "total_generation_kwh": 112.244,
        "fault_code": fault_code,
        "raw_frame_hex": "7e 01 02",
    }


def test_fault_event_ignores_operation_state_bit_zero() -> None:
    assert has_fault_event(0) is False
    assert has_fault_event(1) is False
    assert has_fault_event(2) is True
    assert has_fault_event(3) is True


def test_format_active_bits_lists_enabled_fault_bits() -> None:
    assert format_active_bits(0) == "-"
    assert format_active_bits(0b1010) == "Bit 1, Bit 3"


def test_fault_message_escapes_backticks_and_includes_measurements() -> None:
    message = build_fault_event_message(make_data(2))

    assert "bad'name" in message
    assert "Fault code: `2`" in message
    assert "Active bits: `Bit 1`" in message
    assert "Voltage: `193` V" in message


def test_system_error_message_includes_failure_count() -> None:
    message = build_system_error_message(
        data=make_data(0),
        component="collector",
        event="collector_failed",
        error=RuntimeError("No response from inverter"),
        failures=3,
    )

    assert "Solar RS485 System Error" in message
    assert "Component: `collector`" in message
    assert "Event: `collector_failed`" in message
    assert "Consecutive failures: `3`" in message

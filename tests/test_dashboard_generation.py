from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from solar_rs485_monitor.dashboard import (
    build_generation_snapshot,
    format_fault_event_active_bits,
    format_fault_event_code,
    format_fault_event_label,
    get_fault_code_label,
    get_fault_event_rows,
    extract_virtual_event,
    has_fault_condition,
    is_dashboard_operation_stopped,
    is_operation_stopped,
    is_power_standby_event,
    read_sqlite_fault_events,
)
from solar_rs485_monitor.sinks import sqlite as sqlite_sink


def test_build_generation_snapshot_includes_current_week_generation() -> None:
    daily_df = pd.DataFrame(
        [
            {
                "timestamp": datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
                "value": 4.5,
            },
            {
                "timestamp": datetime(2026, 7, 21, 12, tzinfo=timezone.utc),
                "value": 5.0,
            },
            {
                "timestamp": datetime(2026, 7, 13, 12, tzinfo=timezone.utc),
                "value": 9.0,
            },
        ]
    )

    snapshot = build_generation_snapshot(
        daily_df=daily_df,
        snapshot_timestamp=datetime(2026, 7, 22, 12, tzinfo=timezone.utc),
        display_timezone=ZoneInfo("Asia/Seoul"),
    )

    assert snapshot["weekly_generation_kwh"] == 9.5


def test_collector_virtual_event_is_rendered_without_fault_code() -> None:
    raw_frame_hex = "[V:1] 4f ab 7e 01"
    virtual_event = extract_virtual_event(raw_frame_hex)

    assert virtual_event == 1
    assert format_fault_event_code(None, virtual_event) == "-"
    assert format_fault_event_active_bits(None, virtual_event) == "가상이벤트"
    assert format_fault_event_label(None, virtual_event) == (
        "가상이벤트: 수집기 CRC 오류"
    )
    assert format_fault_event_label(None, 2) == "가상이벤트: 2"


def test_dashboard_decodes_fault_code_with_protocol_metadata() -> None:
    assert is_operation_stopped(1) is True
    assert is_dashboard_operation_stopped(0, 0) is True
    assert is_power_standby_event(0, None, 0) is True
    assert has_fault_condition(2) is True
    assert get_fault_code_label(3) == "인버터 미작동, 태양전지 과전압"
    assert get_fault_event_rows(2, (0, 1)) == [
        "bit1 | 0x0002 | 2 | 태양전지 과전압"
    ]


def test_sqlite_fault_events_include_power_derived_standby(tmp_path) -> None:
    database_path = tmp_path / "dashboard.sqlite3"
    config = {"path": str(database_path), "table": "inverter_log"}
    data = {
        "@timestamp": "2026-08-24T09:51:21+00:00",
        "inverter_name": "Test Inverter",
        "inverter_id": 1,
        "input_dc_voltage_v": 138,
        "input_dc_current_a": 0.0,
        "input_dc_power_w": 0,
        "output_ac_voltage_v": 225,
        "output_ac_current_a": 0.0,
        "output_ac_power_w": 0,
        "output_ac_power_factor_pct": 85.0,
        "output_ac_frequency_hz": 59.98,
        "total_generation_kwh": 19.884,
        "fault_code": 0,
        "raw_frame_hex": "7e 01",
    }

    sqlite_sink.write_to_sqlite(data=data, config=config)

    df = read_sqlite_fault_events(
        database_path=database_path,
        table="inverter_log",
        since=datetime(2026, 8, 24, 0, tzinfo=timezone.utc),
        until=datetime(2026, 8, 24, 23, tzinfo=timezone.utc),
        limit=200,
    )

    assert len(df) == 1
    assert int(df.iloc[0]["fault_code"]) == 0
    assert float(df.iloc[0]["output_ac_power_w"]) == 0

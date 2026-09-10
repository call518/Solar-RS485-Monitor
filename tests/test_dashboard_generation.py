from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from solar_rs485_monitor.dashboard import (
    build_yearly_generation_from_cumulative_samples,
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
    read_sqlite_yearly_generation,
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


def test_yearly_generation_uses_cumulative_sample_increments() -> None:
    sample_df = pd.DataFrame(
        [
            {
                "timestamp": datetime(2026, 1, 1, 0, tzinfo=timezone.utc),
                "total_generation_kwh": 100.0,
            },
            {
                "timestamp": datetime(2026, 6, 1, 0, tzinfo=timezone.utc),
                "total_generation_kwh": 275.5,
            },
            {
                "timestamp": datetime(2026, 7, 1, 0, tzinfo=timezone.utc),
                "total_generation_kwh": 20.0,
            },
            {
                "timestamp": datetime(2026, 9, 1, 0, tzinfo=timezone.utc),
                "total_generation_kwh": 123.063,
            },
        ]
    )

    yearly_df = build_yearly_generation_from_cumulative_samples(
        sample_df,
        ZoneInfo("Asia/Seoul"),
    )

    assert yearly_df["label"].to_list() == ["2026"]
    assert yearly_df["value"].to_list() == pytest.approx([398.563])


def test_generation_snapshot_uses_year_end_delta_when_provided() -> None:
    daily_df = pd.DataFrame(
        [
            {
                "timestamp": datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
                "value": 4.5,
            },
        ]
    )
    yearly_df = pd.DataFrame([{"label": "2026", "value": 1234.063}])

    snapshot = build_generation_snapshot(
        daily_df=daily_df,
        snapshot_timestamp=datetime(2026, 7, 22, 12, tzinfo=timezone.utc),
        display_timezone=ZoneInfo("Asia/Seoul"),
        yearly_df=yearly_df,
    )

    assert snapshot["yearly_generation_kwh"] == 1234.063


def test_sqlite_yearly_generation_uses_cumulative_increments(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "dashboard.sqlite3"
    config = {"path": str(database_path), "table": "inverter_log"}

    rows = [
        ("2026-01-01T00:00:00+00:00", 100.0),
        ("2026-06-01T00:00:00+00:00", 275.5),
        ("2026-06-02T00:00:00+00:00", 0.0),
        ("2026-07-01T00:00:00+00:00", 20.0),
        ("2026-09-01T00:00:00+00:00", 123.063),
    ]
    for index, (timestamp, total_generation_kwh) in enumerate(rows, start=1):
        data = {
            "@timestamp": timestamp,
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
            "total_generation_kwh": total_generation_kwh,
            "fault_code": 0,
            "raw_frame_hex": f"7e {index:02x}",
        }
        sqlite_sink.write_to_sqlite(data=data, config=config)

    monkeypatch.setattr(
        "solar_rs485_monitor.dashboard.get_sqlite_config",
        lambda: config,
    )

    yearly_df = read_sqlite_yearly_generation(
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        until=datetime(2026, 12, 31, tzinfo=timezone.utc),
        display_timezone=ZoneInfo("Asia/Seoul"),
    )

    assert yearly_df["label"].to_list() == ["2026"]
    assert yearly_df["value"].to_list() == pytest.approx([398.563])


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

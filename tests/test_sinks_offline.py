from datetime import datetime

import pytest

from solar_rs485_monitor.sinks import mariadb, sqlite, supabase, thingspeak


def make_data() -> dict:
    return {
        "@timestamp": "2026-07-08T06:00:00+09:00",
        "inverter_name": "Inoelectric IEPVS-3.5-G1",
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
        "fault_code": 0,
        "raw_frame_hex": "7e 01 02",
    }


def test_sqlite_build_row_preserves_column_order_and_timestamp() -> None:
    row = sqlite.build_row(make_data())

    assert row[0] == "2026-07-08T06:00:00+09:00"
    assert row[1] == "Inoelectric IEPVS-3.5-G1"
    assert row[2] == 1
    assert row[-1] == "7e 01 02"
    assert len(row) == len(sqlite.INSERT_COLUMNS)


def test_sqlite_write_to_sqlite_creates_table_and_inserts_row(tmp_path) -> None:
    database_path = tmp_path / "collector.sqlite3"

    insert_id = sqlite.write_to_sqlite(
        make_data(),
        {"path": str(database_path), "table": "inverter_log"},
    )

    assert insert_id == 1

    import sqlite3

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT inverter_name, total_generation_kwh, raw_frame_hex "
            "FROM inverter_log"
        ).fetchone()

    assert row == ("Inoelectric IEPVS-3.5-G1", 112.244, "7e 01 02")


def test_database_identifier_validation_rejects_sql_injection_names() -> None:
    for require_identifier in (
        sqlite.require_identifier,
        mariadb.require_identifier,
        supabase.require_identifier,
    ):
        with pytest.raises(RuntimeError, match="Invalid"):
            require_identifier("bad;DROP_TABLE", "table")


def test_mariadb_build_row_converts_timestamp_to_utc_naive_datetime() -> None:
    row = mariadb.build_row(make_data())

    assert row[0] == datetime(2026, 7, 7, 21, 0)
    assert row[1] == "Inoelectric IEPVS-3.5-G1"
    assert row[-1] == 0
    assert len(row) == len(mariadb.INSERT_COLUMNS)


def test_supabase_build_row_preserves_timezone_aware_timestamp() -> None:
    row = supabase.build_row(make_data())

    assert row[0] == datetime.fromisoformat("2026-07-08T06:00:00+09:00")
    assert row[0].utcoffset().total_seconds() == 9 * 60 * 60
    assert row[-1] == "7e 01 02"
    assert len(row) == len(supabase.INSERT_COLUMNS)


def test_thingspeak_requires_api_key() -> None:
    with pytest.raises(RuntimeError, match="THINGSPEAK_API_KEY is not set"):
        thingspeak.write_to_thingspeak(
            data=make_data(),
            api_key="",
            field_map=thingspeak.get_field_map(),
            timeout=1.0,
        )


def test_thingspeak_rejects_missing_metric_without_network() -> None:
    with pytest.raises(RuntimeError, match="ThingSpeak metric not found"):
        thingspeak.write_to_thingspeak(
            data={},
            api_key="dummy",
            field_map={"field1": "input_dc_voltage_v"},
            timeout=1.0,
        )

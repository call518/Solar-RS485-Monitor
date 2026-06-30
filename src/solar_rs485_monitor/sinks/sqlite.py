import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path


INSERT_COLUMNS = [
    "timestamp",
    "inverter_name",
    "inverter_id",
    "input_dc_voltage_v",
    "input_dc_current_a",
    "input_dc_power_w",
    "output_ac_voltage_v",
    "output_ac_current_a",
    "output_ac_power_w",
    "output_ac_power_factor_pct",
    "output_ac_frequency_hz",
    "total_generation_kwh",
    "fault_code",
    "fault",
    "raw_frame_hex",
]

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def require_identifier(value: str, name: str) -> str:
    if not value or not IDENTIFIER_RE.fullmatch(value):
        raise RuntimeError(f"Invalid SQLite {name}: {value!r}")

    return value


def get_sqlite_config() -> dict:
    database_path = os.getenv(
        "SQLITE_PATH",
        "solar-rs485-monitor.sqlite3",
    ).strip()

    if not database_path:
        raise RuntimeError("SQLITE_PATH is not set")

    return {
        "path": database_path,
        "table": require_identifier(
            os.getenv("SQLITE_TABLE", "inverter_log").strip(),
            "table",
        ),
    }


def parse_timestamp_text(value: str) -> str:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return timestamp.isoformat()


def build_row(data: dict) -> list:
    values = {
        "timestamp": parse_timestamp_text(data["@timestamp"]),
        "inverter_name": data["inverter_name"],
        "inverter_id": data["inverter_id"],
        "input_dc_voltage_v": data["input_dc_voltage_v"],
        "input_dc_current_a": data["input_dc_current_a"],
        "input_dc_power_w": data["input_dc_power_w"],
        "output_ac_voltage_v": data["output_ac_voltage_v"],
        "output_ac_current_a": data["output_ac_current_a"],
        "output_ac_power_w": data["output_ac_power_w"],
        "output_ac_power_factor_pct": data["output_ac_power_factor_pct"],
        "output_ac_frequency_hz": data["output_ac_frequency_hz"],
        "total_generation_kwh": data["total_generation_kwh"],
        "fault_code": data["fault_code"],
        "fault": int(data["fault"]),
        "raw_frame_hex": data["raw_frame_hex"],
    }

    return [values[column] for column in INSERT_COLUMNS]


def ensure_sqlite_table(connection: sqlite3.Connection, table: str) -> None:
    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS "{table}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            inverter_name TEXT NOT NULL,
            inverter_id INTEGER NOT NULL,
            input_dc_voltage_v INTEGER,
            input_dc_current_a REAL,
            input_dc_power_w INTEGER,
            output_ac_voltage_v INTEGER,
            output_ac_current_a REAL,
            output_ac_power_w INTEGER,
            output_ac_power_factor_pct REAL,
            output_ac_frequency_hz REAL,
            total_generation_kwh REAL,
            fault_code INTEGER DEFAULT 0,
            fault INTEGER DEFAULT 0,
            raw_frame_hex TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_{table}_timestamp" '
        f'ON "{table}" (timestamp)'
    )
    connection.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_{table}_inverter_id" '
        f'ON "{table}" (inverter_id)'
    )
    connection.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_{table}_fault" '
        f'ON "{table}" (fault)'
    )


def write_to_sqlite(data: dict, config: dict) -> int:
    database_path = Path(config["path"]).expanduser()
    table = require_identifier(config["table"], "table")

    if database_path.parent != Path("."):
        database_path.parent.mkdir(parents=True, exist_ok=True)

    columns = ", ".join(f'"{column}"' for column in INSERT_COLUMNS)
    placeholders = ", ".join(["?"] * len(INSERT_COLUMNS))
    sql = f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})'

    with sqlite3.connect(database_path) as connection:
        ensure_sqlite_table(connection, table)
        cursor = connection.execute(sql, build_row(data))
        connection.commit()
        return int(cursor.lastrowid)

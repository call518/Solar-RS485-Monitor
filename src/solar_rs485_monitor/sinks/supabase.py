import os
import re
from datetime import datetime


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
    "raw_frame_hex",
]

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def require_identifier(value: str, name: str) -> str:
    if not value or not IDENTIFIER_RE.fullmatch(value):
        raise RuntimeError(f"Invalid Supabase {name}: {value!r}")

    return value


def get_supabase_config() -> dict:
    host = os.getenv("SUPABASE_HOST", "").strip()

    return {
        "host": host,
        "port": int(os.getenv("SUPABASE_PORT", "5432")),
        "user": os.getenv("SUPABASE_USER", "").strip(),
        "password": os.getenv("SUPABASE_PASSWORD", ""),
        "database": os.getenv("SUPABASE_DATABASE", "postgres").strip(),
        "schema": require_identifier(
            os.getenv("SUPABASE_SCHEMA", "public").strip(),
            "schema",
        ),
        "table": require_identifier(
            os.getenv("SUPABASE_TABLE", "inverter_log").strip(),
            "table",
        ),
        "connect_timeout": float(os.getenv("SUPABASE_CONNECT_TIMEOUT", "5.0")),
    }


def validate_supabase_config(config: dict) -> None:
    required_keys = ["host", "user", "password", "database", "schema", "table"]

    for key in required_keys:
        if not config.get(key):
            raise RuntimeError(f"SUPABASE_{key.upper()} is not set")


def parse_timestamp_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_row(data: dict) -> list:
    values = {
        "timestamp": parse_timestamp_datetime(data["@timestamp"]),
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
        "raw_frame_hex": data.get("raw_frame_hex", ""),
    }

    return [values[column] for column in INSERT_COLUMNS]


def ensure_supabase_table(connection, schema: str, table: str) -> None:
    safe_schema = require_identifier(schema, "schema")
    safe_table = require_identifier(table, "table")

    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{safe_schema}"')

        cursor.execute(
            f'''
            CREATE TABLE IF NOT EXISTS "{safe_schema}"."{safe_table}" (
                id BIGSERIAL PRIMARY KEY,
                "timestamp" TIMESTAMPTZ NOT NULL,
                inverter_name TEXT NOT NULL,
                inverter_id INTEGER NOT NULL,
                input_dc_voltage_v INTEGER,
                input_dc_current_a DOUBLE PRECISION,
                input_dc_power_w INTEGER,
                output_ac_voltage_v INTEGER,
                output_ac_current_a DOUBLE PRECISION,
                output_ac_power_w INTEGER,
                output_ac_power_factor_pct DOUBLE PRECISION,
                output_ac_frequency_hz DOUBLE PRECISION,
                total_generation_kwh DOUBLE PRECISION,
                fault_code INTEGER DEFAULT 0,
                raw_frame_hex TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            '''
        )

        cursor.execute(
            f'''
            CREATE INDEX IF NOT EXISTS "idx_{safe_table}_timestamp"
            ON "{safe_schema}"."{safe_table}" ("timestamp")
            '''
        )
        cursor.execute(
            f'''
            CREATE INDEX IF NOT EXISTS "idx_{safe_table}_inverter_id"
            ON "{safe_schema}"."{safe_table}" (inverter_id)
            '''
        )
        cursor.execute(
            f'''
            CREATE INDEX IF NOT EXISTS "idx_{safe_table}_fault_code"
            ON "{safe_schema}"."{safe_table}" (fault_code)
            '''
        )


def write_to_supabase(data: dict, config: dict) -> int:
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError(
            "psycopg is required for Supabase logging. "
            "Install the package again with project dependencies."
        ) from e

    validate_supabase_config(config)

    schema = require_identifier(config["schema"], "schema")
    table = require_identifier(config["table"], "table")

    columns = ", ".join(f'"{column}"' for column in INSERT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(INSERT_COLUMNS))
    sql = (
        f'INSERT INTO "{schema}"."{table}" ({columns}) '
        f"VALUES ({placeholders}) RETURNING id"
    )

    with psycopg.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        dbname=config["database"],
        connect_timeout=config["connect_timeout"],
        autocommit=True,
    ) as connection:
        ensure_supabase_table(connection, schema=schema, table=table)

        with connection.cursor() as cursor:
            cursor.execute(sql, build_row(data))
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Supabase insert did not return an id")

            return int(row[0])

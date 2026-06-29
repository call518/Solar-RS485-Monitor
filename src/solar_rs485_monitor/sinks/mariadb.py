import os
import re
from datetime import datetime


INSERT_COLUMNS = [
    "timestamp",
    "inverter_name",
    "inverter_id",
    "pv_voltage_v",
    "pv_current_a",
    "pv_power_w",
    "grid_voltage_v",
    "grid_current_a",
    "current_output_w",
    "power_factor_pct",
    "frequency_hz",
    "total_generation_kwh",
    "fault_code",
    "fault",
]

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def require_identifier(value: str, name: str) -> str:
    if not value or not IDENTIFIER_RE.fullmatch(value):
        raise RuntimeError(f"Invalid MariaDB {name}: {value!r}")

    return value


def get_mariadb_config() -> dict:
    return {
        "host": os.getenv("MARIADB_HOST", "").strip(),
        "port": int(os.getenv("MARIADB_PORT", "3306")),
        "user": os.getenv("MARIADB_USER", "").strip(),
        "password": os.getenv("MARIADB_PASSWORD", ""),
        "database": os.getenv(
            "MARIADB_DATABASE",
            "solar_rs485_monitor",
        ).strip(),
        "table": require_identifier(
            os.getenv("MARIADB_TABLE", "inverter_log").strip(),
            "table",
        ),
        "connect_timeout": float(os.getenv("MARIADB_CONNECT_TIMEOUT", "5.0")),
    }


def validate_mariadb_config(config: dict) -> None:
    required_keys = [
        "host",
        "user",
        "password",
        "database",
        "table",
    ]

    for key in required_keys:
        if not config.get(key):
            raise RuntimeError(f"MARIADB_{key.upper()} is not set")


def parse_timestamp_datetime(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if timestamp.tzinfo is None:
        return timestamp

    return timestamp.replace(tzinfo=None)


def build_row(data: dict) -> list:
    values = {
        "timestamp": parse_timestamp_datetime(data["@timestamp"]),
        "inverter_name": data["inverter_name"],
        "inverter_id": data["inverter_id"],
        "pv_voltage_v": data["pv_voltage_v"],
        "pv_current_a": data["pv_current_a"],
        "pv_power_w": data["pv_power_w"],
        "grid_voltage_v": data["grid_voltage_v"],
        "grid_current_a": data["grid_current_a"],
        "current_output_w": data["current_output_w"],
        "power_factor_pct": data["power_factor_pct"],
        "frequency_hz": data["frequency_hz"],
        "total_generation_kwh": data["total_generation_kwh"],
        "fault_code": data["fault_code"],
        "fault": int(bool(data["fault"])),
    }

    return [values[column] for column in INSERT_COLUMNS]


def write_to_mariadb(data: dict, config: dict) -> int:
    try:
        import pymysql
    except ImportError as e:
        raise RuntimeError(
            "PyMySQL is required for MariaDB logging. "
            "Install the package again with project dependencies."
        ) from e

    validate_mariadb_config(config)

    table = require_identifier(config["table"], "table")
    columns = ", ".join(f"`{column}`" for column in INSERT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(INSERT_COLUMNS))
    sql = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"

    with pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=config["connect_timeout"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, build_row(data))
            return cursor.lastrowid

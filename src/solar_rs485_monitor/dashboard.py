import base64
import html
import getpass
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from solar_rs485_monitor.sinks.mariadb import (
    get_mariadb_config,
    require_identifier as require_mariadb_identifier,
    validate_mariadb_config,
)
from solar_rs485_monitor.sinks.sqlite import (
    ensure_sqlite_table,
    get_sqlite_config,
    require_identifier as require_sqlite_identifier,
)
from solar_rs485_monitor.version import get_version


CONFIG_FILENAME = "solar-rs485-monitor.conf"
DEFAULT_DASHBOARD_TITLE = "Solar RS485 Monitor"
DEFAULT_DASHBOARD_LANGUAGE = "ko"
DEFAULT_DASHBOARD_STANDBY_POWER_W_THRESHOLD = 20.0
DEFAULT_DASHBOARD_AUTO_REFRESH_SECONDS = 60
DASHBOARD_AUTH_HASH_ALGORITHM = "pbkdf2_sha256"
DASHBOARD_AUTH_HASH_ITERATIONS = 260000
DASHBOARD_AUTH_SESSION_KEY = "solar_rs485_monitor_dashboard_auth_user"
DASHBOARD_AUTH_SESSION_EXPIRES_AT_KEY = "solar_rs485_monitor_dashboard_auth_expires_at"
DASHBOARD_AUTH_SESSION_EXPIRED_KEY = "solar_rs485_monitor_dashboard_auth_expired"
DASHBOARD_AUTH_COOKIE_NAME = "solar_rs485_monitor_dashboard_auth"
DEFAULT_DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS = 86400
DEFAULT_DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS = "admin"
DASHBOARD_AUTH_PERSISTENT_COOKIE_MAX_AGE_SECONDS = 10 * 365 * 24 * 60 * 60

METRICS = {
    "input_dc_voltage_v": "DC input voltage (V)",
    "input_dc_current_a": "DC input current (A)",
    "input_dc_power_w": "DC input power (W)",
    "output_ac_voltage_v": "AC output voltage (V)",
    "output_ac_current_a": "AC output current (A)",
    "output_ac_power_w": "AC output power (W)",
    "output_ac_power_factor_pct": "AC output power factor (%)",
    "output_ac_frequency_hz": "AC output frequency (Hz)",
    "total_generation_kwh": "Total generation (kWh)",
    "fault_code": "Fault code",
    "fault": "Fault",
}

METRIC_LABELS = {
    "ko": {
        "input_dc_voltage_v": "DC 입력 전압 (V)",
        "input_dc_current_a": "DC 입력 전류 (A)",
        "input_dc_power_w": "DC 입력 전력 (W)",
        "output_ac_voltage_v": "AC 출력 전압 (V)",
        "output_ac_current_a": "AC 출력 전류 (A)",
        "output_ac_power_w": "AC 출력 전력 (W)",
        "output_ac_power_factor_pct": "AC 출력 역률 (%)",
        "output_ac_frequency_hz": "AC 출력 주파수 (Hz)",
        "total_generation_kwh": "누적 발전량 (kWh)",
        "fault_code": "점검 코드",
        "fault": "점검",
    },
    "en": METRICS,
}

UI_TEXT = {
    "ko": {
        "language": "언어",
        "data_source": "데이터 소스",
        "source": "소스",
        "range": "조회 범위",
        "x_axis_mode": "시간축 스케일",
        "x_axis_mode_fixed": "고정 스케일",
        "x_axis_mode_auto": "자동 스케일",
        "bucket_minutes": "집계 시간 단위",
        "max_points": "최대 조회 포인트 수",
        "aggregate_caption": (
            "이 값은 차트에 표시할 {bucket} 단위 집계 데이터의 "
            "최대 포인트 수입니다."
        ),
        "auto_refresh": "자동 새로고침",
        "login_title": "대시보드 로그인",
        "login_user": "아이디",
        "login_password": "비밀번호",
        "login_button": "로그인",
        "login_failed": "아이디 또는 비밀번호가 올바르지 않습니다.",
        "logout": "로그아웃",
        "auth_not_configured": "대시보드 인증이 켜져 있지만 DASHBOARD_AUTH_USERS가 설정되지 않았습니다.",
        "login_success": "로그인되었습니다. 대시보드를 여는 중입니다.",
        "logout_success": "로그아웃되었습니다.",
        "no_rows": "선택한 소스와 조회 범위에 해당하는 데이터가 없습니다.",
        "inverter": "인버터",
        "id": "ID",
        "latest": "최신 시각",
        "ac_output_w": "AC 출력 (W)",
        "status": "상태",
        "fault": "점검",
        "fault_normal": "정상",
        "fault_fault": "장애",
        "fault_standby": "대기",
        "utc": "UTC",
        "local": "Local",
        "latest_snapshot": "최신 메트릭",
        "metric_charts": "메트릭 차트",
        "chart_caption": "각 차트는 선택한 조회 범위의 {bucket} 단위 집계값을 표시합니다.",
        "fault_events": "장애 이벤트 (최근 200건)",
        "fault_events_caption": "선택한 범위에서 고장 비트(Bit 1~12)가 활성화된 최신 이벤트입니다.",
        "fault_events_empty": "선택한 범위에서 장애 이벤트가 없습니다.",
        "active_bits": "활성 비트",
        "fault_code_label": "점검 코드 설명",
        "latest_rows": "최신 데이터 (최근 200건)",
    },
    "en": {
        "language": "Language",
        "data_source": "Data Source",
        "source": "Source",
        "range": "Range",
        "x_axis_mode": "Time axis scale",
        "x_axis_mode_fixed": "Fixed scale",
        "x_axis_mode_auto": "Auto scale",
        "bucket_minutes": "Aggregation interval",
        "max_points": "Max chart points",
        "aggregate_caption": (
            "This limits the maximum number of {bucket} aggregated chart "
            "points shown."
        ),
        "auto_refresh": "Auto refresh",
        "login_title": "Dashboard Login",
        "login_user": "Username",
        "login_password": "Password",
        "login_button": "Log in",
        "login_failed": "Invalid username or password.",
        "logout": "Log out",
        "auth_not_configured": "Dashboard authentication is enabled, but DASHBOARD_AUTH_USERS is not set.",
        "login_success": "Login successful. Opening dashboard.",
        "logout_success": "Logged out.",
        "no_rows": "No rows found for the selected source and range.",
        "inverter": "Inverter",
        "id": "ID",
        "latest": "Latest",
        "ac_output_w": "AC Output (W)",
        "status": "Status",
        "fault": "Fault",
        "fault_normal": "NORMAL",
        "fault_fault": "FAULT",
        "fault_standby": "STANDBY",
        "utc": "UTC",
        "local": "Local",
        "latest_snapshot": "Latest Metrics",
        "metric_charts": "Metric Charts",
        "chart_caption": "Each chart shows {bucket} aggregated values for the selected range.",
        "fault_events": "Fault Events (Recent 200)",
        "fault_events_caption": "Latest events where fault bits (Bit 1-12) are active within the selected range.",
        "fault_events_empty": "No fault events in the selected range.",
        "active_bits": "Active bits",
        "fault_code_label": "Fault code detail",
        "latest_rows": "Latest Rows (Recent 200)",
    },
}

RANGE_LABELS = {
    "ko": {
        "Last 1 hour": "최근 1시간",
        "Last 6 hours": "최근 6시간",
        "Last 24 hours": "최근 24시간",
        "Today": "오늘",
        "Last 2 days": "최근 2일",
        "Last 3 days": "최근 3일",
        "Last 7 days": "최근 7일",
        "Last 30 days": "최근 30일",
        "Last 90 days": "최근 90일",
        "Last 6 months": "최근 6개월",
    },
    "en": {
        "Last 1 hour": "Last 1 hour",
        "Last 6 hours": "Last 6 hours",
        "Last 24 hours": "Last 24 hours",
        "Today": "Today",
        "Last 2 days": "Last 2 days",
        "Last 3 days": "Last 3 days",
        "Last 7 days": "Last 7 days",
        "Last 30 days": "Last 30 days",
        "Last 90 days": "Last 90 days",
        "Last 6 months": "Last 6 months",
    },
}

BUCKET_SECONDS = [10, 30, 60, 120, 300, 600, 900, 1800]

BUCKET_LABELS = {
    "ko": {
        10: "10초",
        30: "30초",
        60: "1분",
        120: "2분",
        300: "5분",
        600: "10분",
        900: "15분",
        1800: "30분",
    },
    "en": {
        10: "10 seconds",
        30: "30 seconds",
        60: "1 minute",
        120: "2 minutes",
        300: "5 minutes",
        600: "10 minutes",
        900: "15 minutes",
        1800: "30 minutes",
    },
}

REFRESH_SECONDS = [0, 10, 30, 60, 120, 300, 600]

REFRESH_LABELS = {
    "ko": {
        0: "끄기",
        10: "10초",
        30: "30초",
        60: "1분",
        120: "2분",
        300: "5분",
        600: "10분",
    },
    "en": {
        0: "Off",
        10: "10 seconds",
        30: "30 seconds",
        60: "1 minute",
        120: "2 minutes",
        300: "5 minutes",
        600: "10 minutes",
    },
}

TIME_AXIS_FORMAT = "%m-%d %H:%M"
TOOLTIP_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

TABLE_LABELS = {
    "ko": {
        "timestamp": "시각 (UTC)",
        "inverter_name": "인버터 이름",
        "inverter_id": "인버터 ID",
        **METRIC_LABELS["ko"],
    },
    "en": {
        "timestamp": "Timestamp (UTC)",
        "inverter_name": "Inverter name",
        "inverter_id": "Inverter ID",
        **METRIC_LABELS["en"],
    },
}

DEFAULT_METRICS = [
    *METRICS.keys(),
]

CHART_GROUPS = [
    ["total_generation_kwh"],
    ["input_dc_power_w", "output_ac_power_w"],
    ["input_dc_voltage_v", "output_ac_voltage_v"],
    ["input_dc_current_a", "output_ac_current_a"],
    ["output_ac_power_factor_pct", "output_ac_frequency_hz"],
    ["fault", "fault_code"],
]

BAR_CHART_COLORS = {
    "total_generation_kwh": "#16a34a",
    "fault": "#dc2626",
    "fault_code": "#be185d",
}

AREA_CHART_COLORS = {
    "input_dc_voltage_v": "#f59e0b",
    "input_dc_current_a": "#f59e0b",
    "input_dc_power_w": "#f59e0b",
    "output_ac_voltage_v": "#3b82f6",
    "output_ac_current_a": "#3b82f6",
    "output_ac_power_w": "#3b82f6",
    "output_ac_power_factor_pct": "#14b8a6",
    "output_ac_frequency_hz": "#6366f1",
}

RANGES = {
    "Last 1 hour": timedelta(hours=1),
    "Last 6 hours": timedelta(hours=6),
    "Last 24 hours": timedelta(hours=24),
    "Today": timedelta(days=1),
    "Last 2 days": timedelta(days=2),
    "Last 3 days": timedelta(days=3),
    "Last 7 days": timedelta(days=7),
    "Last 30 days": timedelta(days=30),
    "Last 90 days": timedelta(days=90),
    "Last 6 months": timedelta(days=183),
}

MAX_AGGREGATE_METRICS = {
    "total_generation_kwh",
    "fault_code",
    "fault",
}

FAULT_OPERATION_STOP_BIT = 0
# Bit 1-12 are fault bits from the inverter remote monitoring status table.
FAULT_STATUS_MASK = 0x1FFE

FAULT_BIT_LABELS_KO = {
    0: "Bit 0 인버터 동작유무(미작동)",
    1: "Bit 1 태양전지 과전압",
    2: "Bit 2 태양전지 저전압",
    3: "Bit 3 태양전지 과전류",
    4: "Bit 4 인버터 IGBT 에러",
    5: "Bit 5 인버터 과온",
    6: "Bit 6 계통 과전압",
    7: "Bit 7 계통 저전압",
    8: "Bit 8 계통 과전류",
    9: "Bit 9 계통 과주파수",
    10: "Bit 10 계통 저주파수",
    11: "Bit 11 단독운전(정전)",
    12: "Bit 12 지락(누전)",
}


def get_config_path() -> Path | None:
    system_config = Path("/etc") / CONFIG_FILENAME

    if system_config.is_file():
        return system_config

    current_config = Path.cwd() / CONFIG_FILENAME

    if current_config.is_file():
        return current_config

    return None


def load_config() -> Path | None:
    config_path = get_config_path()

    if config_path is not None:
        load_dotenv(dotenv_path=config_path, override=True)

    return config_path


def get_timezone() -> ZoneInfo:
    timezone_name = os.getenv("TIMEZONE", "Asia/Seoul").strip()

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Seoul")


def get_dashboard_title() -> str:
    return (
        os.getenv("DASHBOARD_TITLE", DEFAULT_DASHBOARD_TITLE).strip()
        or DEFAULT_DASHBOARD_TITLE
    )


def get_dashboard_language() -> str:
    language = os.getenv("DASHBOARD_LANGUAGE", "").strip().lower()

    if language in {"english", "en"}:
        return "en"

    if language in {"korean", "ko"}:
        return "ko"

    return DEFAULT_DASHBOARD_LANGUAGE


def get_dashboard_standby_power_w_threshold() -> float:
    raw = os.getenv(
        "DASHBOARD_STANDBY_POWER_W_THRESHOLD",
        str(DEFAULT_DASHBOARD_STANDBY_POWER_W_THRESHOLD),
    ).strip()

    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_DASHBOARD_STANDBY_POWER_W_THRESHOLD

    return max(0.0, value)


def get_dashboard_auto_refresh_seconds() -> int:
    raw = os.getenv(
        "DASHBOARD_AUTO_REFRESH_SECONDS",
        str(DEFAULT_DASHBOARD_AUTO_REFRESH_SECONDS),
    ).strip()

    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_DASHBOARD_AUTO_REFRESH_SECONDS

    if value == 0:
        return 0

    if 0 < value < 10:
        return 10

    if value in REFRESH_SECONDS:
        return value

    return DEFAULT_DASHBOARD_AUTO_REFRESH_SECONDS


def is_operation_stopped(fault_code: int) -> bool:
    return bool(fault_code & (1 << FAULT_OPERATION_STOP_BIT))


def has_fault_condition(fault_code: int) -> bool:
    return bool(fault_code & FAULT_STATUS_MASK)


def get_fault_code_label(fault_code: int) -> str | None:
    if fault_code <= 0:
        return None

    labels = []

    for bit in range(16):
        if not (fault_code & (1 << bit)):
            continue

        label = FAULT_BIT_LABELS_KO.get(bit)
        if label:
            labels.append(label)

    if not labels:
        return None

    return ", ".join(labels)


def format_active_bits(fault_code: int) -> str:
    if fault_code <= 0:
        return "-"

    bits = [f"Bit {bit}" for bit in range(16) if fault_code & (1 << bit)]
    return ", ".join(bits) if bits else "-"


def is_dashboard_auth_enabled() -> bool:
    value = os.getenv("DASHBOARD_AUTH_ENABLED", "false").strip().lower()
    return value in ("1", "true", "yes", "y", "on")


def hash_dashboard_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        DASHBOARD_AUTH_HASH_ITERATIONS,
    ).hex()
    return (
        f"{DASHBOARD_AUTH_HASH_ALGORITHM}$"
        f"{DASHBOARD_AUTH_HASH_ITERATIONS}$"
        f"{salt}$"
        f"{digest}"
    )


def verify_dashboard_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = encoded_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False

    if algorithm != DASHBOARD_AUTH_HASH_ALGORITHM:
        return False

    try:
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            iterations,
        ).hex()
    except ValueError:
        return False

    return hmac.compare_digest(actual_digest, expected_digest)


def parse_dashboard_auth_users() -> dict[str, str]:
    raw_users = os.getenv("DASHBOARD_AUTH_USERS", "").strip()
    users = {}

    if not raw_users:
        return users

    for entry in raw_users.split(","):
        entry = entry.strip()
        if not entry:
            continue

        username, separator, encoded_hash = entry.partition(":")
        username = username.strip()
        encoded_hash = encoded_hash.strip()
        if separator and username and encoded_hash:
            users[username] = encoded_hash

    return users


def get_dashboard_auth_cookie_secret() -> str:
    explicit_secret = os.getenv("DASHBOARD_AUTH_COOKIE_SECRET", "").strip()
    if explicit_secret:
        return explicit_secret

    return hashlib.sha256(
        os.getenv("DASHBOARD_AUTH_USERS", "").encode("utf-8")
    ).hexdigest()


def parse_dashboard_auth_cookie_persistent_users() -> set[str]:
    raw_users = os.getenv("DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS", "").strip()

    # Backward compatibility for older configuration key.
    if not raw_users:
        raw_users = os.getenv("DASHBOARD_AUTH_PERSISTENT_USERS", "").strip()

    if not raw_users:
        raw_users = DEFAULT_DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS

    if not raw_users:
        return set()

    return {
        username.strip()
        for username in raw_users.split(",")
        if username.strip()
    }


def get_dashboard_auth_cookie_max_age_seconds(username: str | None = None) -> int:
    if username and username in parse_dashboard_auth_cookie_persistent_users():
        return DASHBOARD_AUTH_PERSISTENT_COOKIE_MAX_AGE_SECONDS

    raw_value = os.getenv(
        "DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS",
        str(DEFAULT_DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS),
    ).strip()

    try:
        max_age = int(raw_value)
    except ValueError:
        return DEFAULT_DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS

    return max(1, max_age)


def encode_urlsafe_json(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_urlsafe_json(value: str) -> dict:
    padded_value = value + ("=" * (-len(value) % 4))
    raw = base64.urlsafe_b64decode(padded_value.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def sign_dashboard_auth_payload(payload: str) -> str:
    secret = get_dashboard_auth_cookie_secret().encode("utf-8")
    return hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()


def get_dashboard_auth_expires_at(username: str) -> int:
    return int(time.time()) + get_dashboard_auth_cookie_max_age_seconds(username)


def build_dashboard_auth_cookie(username: str, expires_at: int) -> str:
    max_age = get_dashboard_auth_cookie_max_age_seconds(username)
    payload = encode_urlsafe_json(
        {
            "username": username,
            "expires_at": expires_at,
        }
    )
    signature = sign_dashboard_auth_payload(payload)
    return f"{payload}.{signature}"


def verify_dashboard_auth_cookie(
    token: str,
    users: dict[str, str],
) -> tuple[str, int] | None:
    try:
        payload, signature = token.split(".", 1)
        expected_signature = sign_dashboard_auth_payload(payload)
        if not hmac.compare_digest(signature, expected_signature):
            return None

        data = decode_urlsafe_json(payload)
        username = str(data["username"])
        expires_at = int(data["expires_at"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    if expires_at < int(time.time()):
        return None

    if username not in users:
        return None

    return username, expires_at


def get_dashboard_auth_cookie(st) -> str:
    try:
        value = st.context.cookies.get(DASHBOARD_AUTH_COOKIE_NAME)
    except Exception:
        return ""

    return value or ""


def clear_dashboard_auth_session(st) -> None:
    st.session_state.pop(DASHBOARD_AUTH_SESSION_KEY, None)
    st.session_state.pop(DASHBOARD_AUTH_SESSION_EXPIRES_AT_KEY, None)


def set_dashboard_auth_session(st, username: str, expires_at: int) -> None:
    st.session_state[DASHBOARD_AUTH_SESSION_KEY] = username
    st.session_state[DASHBOARD_AUTH_SESSION_EXPIRES_AT_KEY] = expires_at


def get_authenticated_dashboard_user(st, users: dict[str, str]) -> str | None:
    username = st.session_state.get(DASHBOARD_AUTH_SESSION_KEY)
    expires_at = st.session_state.get(DASHBOARD_AUTH_SESSION_EXPIRES_AT_KEY)

    if username not in users:
        clear_dashboard_auth_session(st)
        return None

    try:
        expires_at = int(expires_at)
    except (TypeError, ValueError):
        clear_dashboard_auth_session(st)
        return None

    if expires_at < int(time.time()):
        clear_dashboard_auth_session(st)
        st.session_state[DASHBOARD_AUTH_SESSION_EXPIRED_KEY] = True
        return None

    return username


def render_cookie_script(st, token: str | None, max_age: int) -> None:
    import streamlit.components.v1 as components

    cookie_name = json.dumps(DASHBOARD_AUTH_COOKIE_NAME)
    if token is None:
        cookie_value = '""'
        cookie_max_age = "0"
    else:
        cookie_value = json.dumps(token)
        cookie_max_age = str(max_age)

    components.html(
        f"""
        <script>
          document.cookie = {cookie_name} + "=" + encodeURIComponent({cookie_value})
            + "; path=/; max-age=" + {cookie_max_age} + "; samesite=lax";
          window.parent.location.reload();
        </script>
        """,
        height=0,
    )


def env_bool_text(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().lower()
    return "true" if value in ("1", "true", "yes", "y", "on") else "false"


def has_streamlit_option(args: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(f"{option}=") for arg in args)


def build_streamlit_args(cli_args: list[str]) -> list[str]:
    option_defaults = {
        "--server.address": os.getenv("DASHBOARD_SERVER_ADDRESS", "0.0.0.0"),
        "--server.port": os.getenv("DASHBOARD_SERVER_PORT", "8501"),
        "--server.headless": env_bool_text("DASHBOARD_SERVER_HEADLESS", "true"),
        "--browser.gatherUsageStats": env_bool_text(
            "DASHBOARD_GATHER_USAGE_STATS",
            "false",
        ),
        "--server.runOnSave": env_bool_text("DASHBOARD_RUN_ON_SAVE", "false"),
    }
    streamlit_args = []

    for option, value in option_defaults.items():
        if value and not has_streamlit_option(cli_args, option):
            streamlit_args.extend([option, value])

    return streamlit_args


def get_time_bounds(
    range_name: str,
    display_timezone: ZoneInfo,
) -> tuple[datetime, datetime]:
    now_utc = datetime.now(timezone.utc)

    if range_name == "Today":
        now_local = now_utc.astimezone(display_timezone)
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_local.astimezone(timezone.utc), now_utc

    return now_utc - RANGES[range_name], now_utc


def normalize_timestamp_value(value):
    import pandas as pd

    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return pd.NaT

    if pd.isna(timestamp):
        return pd.NaT

    if timestamp.tzinfo is not None:
        return timestamp.tz_convert(timezone.utc)

    return timestamp.tz_localize(timezone.utc)


def normalize_dataframe(df):
    import pandas as pd

    if df.empty:
        return df

    df["timestamp"] = df["timestamp"].map(
        normalize_timestamp_value
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    for column in METRICS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    return df


def build_aggregate_selects(quote: str) -> str:
    selects = []

    for column in METRICS:
        function = "MAX" if column in MAX_AGGREGATE_METRICS else "AVG"
        selects.append(f"{function}({quote}{column}{quote}) AS {quote}{column}{quote}")

    return ", ".join(selects)


def merge_mode_fault_code(df, mode_df):
    if df.empty or mode_df.empty:
        return df

    merged = df.merge(
        mode_df,
        on="timestamp",
        how="left",
        suffixes=("", "_mode"),
    )

    if "fault_code_mode" in merged.columns:
        merged["fault_code_mode"] = (
            merged["fault_code_mode"]
            .astype(float)
            .round()
        )
        merged["fault_code"] = merged["fault_code_mode"].combine_first(
            merged.get("fault_code")
        )
        merged = merged.drop(columns=["fault_code_mode"])

    if "fault_code" in merged.columns:
        merged["fault_code"] = merged["fault_code"].fillna(0).round().astype(int)
        merged["fault"] = ((merged["fault_code"] & FAULT_STATUS_MASK) != 0).astype(int)

    return merged


def read_sqlite_fault_code_mode_data(
    database_path: Path,
    table: str,
    since: datetime,
    until: datetime,
    limit: int,
    bucket_seconds: int,
):
    import pandas as pd

    sql = (
        "SELECT bucket_index, timestamp, fault_code, cnt, last_seen FROM ("
        "  SELECT "
        "    (CAST(strftime('%s', timestamp) AS INTEGER) / ?) AS bucket_index, "
        "    datetime((CAST(strftime('%s', timestamp) AS INTEGER) / ?) * ?, 'unixepoch') AS timestamp, "
        "    CAST(\"fault_code\" AS INTEGER) AS fault_code, "
        "    COUNT(*) AS cnt, "
        "    MAX(timestamp) AS last_seen "
        f"  FROM \"{table}\" "
        "  WHERE timestamp >= ? AND timestamp <= ? "
        "  GROUP BY bucket_index, fault_code"
        ") grouped "
        "ORDER BY timestamp DESC LIMIT ?"
    )

    query_limit = max(1, limit) * 32

    with sqlite3.connect(database_path) as connection:
        df = pd.read_sql_query(
            sql,
            connection,
            params=[
                bucket_seconds,
                bucket_seconds,
                bucket_seconds,
                since.isoformat(),
                until.isoformat(),
                query_limit,
            ],
        )

    if df.empty:
        return normalize_dataframe(df)

    grouped_df = df.sort_values(
        ["bucket_index", "cnt", "last_seen", "fault_code"],
        ascending=[True, False, False, False],
    )
    mode_df = grouped_df.drop_duplicates(subset=["bucket_index"], keep="first")
    mode_df = mode_df[["timestamp", "fault_code"]].rename(
        columns={"fault_code": "fault_code_mode"}
    )
    mode_df = mode_df.sort_values("timestamp", ascending=False).head(limit)
    return normalize_dataframe(mode_df)


def read_mariadb_fault_code_mode_data(
    config: dict,
    table: str,
    since: datetime,
    until: datetime,
    limit: int,
    bucket_seconds: int,
):
    import pandas as pd
    import pymysql

    sql = (
        "SELECT bucket_index, `timestamp`, fault_code, cnt, last_seen FROM ("
        "  SELECT "
        "    FLOOR(UNIX_TIMESTAMP(`timestamp`) / %s) AS bucket_index, "
        "    FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(`timestamp`) / %s) * %s) AS `timestamp`, "
        "    CAST(`fault_code` AS SIGNED) AS fault_code, "
        "    COUNT(*) AS cnt, "
        "    MAX(`timestamp`) AS last_seen "
        f"  FROM `{table}` "
        "  WHERE `timestamp` >= %s AND `timestamp` <= %s "
        "  GROUP BY bucket_index, fault_code"
        ") grouped "
        "ORDER BY `timestamp` DESC LIMIT %s"
    )

    query_limit = max(1, limit) * 32

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
            cursor.execute("SET time_zone = '+00:00'")

        df = pd.read_sql_query(
            sql,
            connection,
            params=[
                bucket_seconds,
                bucket_seconds,
                bucket_seconds,
                since,
                until,
                query_limit,
            ],
        )

    if df.empty:
        return normalize_dataframe(df)

    grouped_df = df.sort_values(
        ["bucket_index", "cnt", "last_seen", "fault_code"],
        ascending=[True, False, False, False],
    )
    mode_df = grouped_df.drop_duplicates(subset=["bucket_index"], keep="first")
    mode_df = mode_df[["timestamp", "fault_code"]].rename(
        columns={"fault_code": "fault_code_mode"}
    )
    mode_df = mode_df.sort_values("timestamp", ascending=False).head(limit)
    return normalize_dataframe(mode_df)


def read_sqlite_fault_events(
    database_path: Path,
    table: str,
    since: datetime,
    until: datetime,
    limit: int,
):
    import pandas as pd

    sql = (
        "SELECT timestamp, inverter_name, inverter_id, fault_code "
        f"FROM \"{table}\" "
        "WHERE timestamp >= ? AND timestamp <= ? "
        f"AND (CAST(\"fault_code\" AS INTEGER) & {FAULT_STATUS_MASK}) != 0 "
        "ORDER BY timestamp DESC LIMIT ?"
    )

    with sqlite3.connect(database_path) as connection:
        df = pd.read_sql_query(
            sql,
            connection,
            params=[since.isoformat(), until.isoformat(), limit],
        )

    return normalize_dataframe(df)


def read_mariadb_fault_events(
    config: dict,
    table: str,
    since: datetime,
    until: datetime,
    limit: int,
):
    import pandas as pd
    import pymysql

    sql = (
        "SELECT `timestamp`, `inverter_name`, `inverter_id`, `fault_code` "
        f"FROM `{table}` "
        "WHERE `timestamp` >= %s AND `timestamp` <= %s "
        f"AND (CAST(`fault_code` AS SIGNED) & {FAULT_STATUS_MASK}) != 0 "
        "ORDER BY `timestamp` DESC LIMIT %s"
    )

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
            cursor.execute("SET time_zone = '+00:00'")

        df = pd.read_sql_query(
            sql,
            connection,
            params=[since, until, limit],
        )

    return normalize_dataframe(df)


def format_table_header(column: str, lang: str) -> str:
    label = TABLE_LABELS[lang].get(column, column)
    return (
        f"<th><strong>{html.escape(label)}</strong>"
        f"<br><span>({html.escape(column)})</span></th>"
    )


def render_latest_rows_table(df, columns: list[str], lang: str) -> str:
    display_df = df.sort_values("timestamp", ascending=False)[columns].head(200)
    header = "".join(format_table_header(column, lang) for column in columns)
    rows = []

    for _, row in display_df.iterrows():
        cells = []
        for column in columns:
            value = row[column]
            if hasattr(value, "isoformat"):
                value = value.isoformat(sep=" ")
            cells.append(f"<td>{html.escape(str(value))}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    return f"""
    <div style="overflow-x: auto; max-height: 520px; border: 1px solid #e5e7eb;">
      <table style="border-collapse: collapse; width: 100%; font-size: 0.875rem;">
        <thead>
          <tr>{header}</tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </div>
    <style>
      table th {{
        position: sticky;
        top: 0;
        background: #f8fafc;
        border-bottom: 1px solid #d1d5db;
        padding: 0.5rem;
        text-align: left;
        white-space: nowrap;
      }}
      table th span {{
        color: #6b7280;
        font-size: 0.75rem;
        font-weight: 400;
      }}
      table td {{
        border-bottom: 1px solid #e5e7eb;
        padding: 0.45rem 0.5rem;
        white-space: nowrap;
      }}
    </style>
    """


def format_timezone_offset(timestamp) -> str:
    offset = timestamp.utcoffset()
    if offset is None:
        return "+00:00"

    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def format_timestamp_text(
    timestamp,
    display_timezone: ZoneInfo,
) -> tuple[str, str, str, str]:
    if not hasattr(timestamp, "tz_convert"):
        timestamp = datetime.fromisoformat(str(timestamp))

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    utc_timestamp = timestamp.astimezone(timezone.utc)
    local_timestamp = timestamp.astimezone(display_timezone)

    return (
        utc_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        local_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        format_timezone_offset(utc_timestamp),
        format_timezone_offset(local_timestamp),
    )


def render_latest_timestamp(timestamp, text: dict[str, str], display_timezone: ZoneInfo) -> str:
    utc_text, local_text, utc_offset, local_offset = format_timestamp_text(
        timestamp,
        display_timezone,
    )

    return f"""
    <div style="line-height: 1.45;">
      <div style="font-size: 1.05rem; color: #475569; margin-bottom: 0.35rem; font-weight: 600;">
        {html.escape(text["latest"])}
      </div>
      <div style="font-size: 1.2rem; font-weight: 650;">
        {html.escape(local_text)} <span style="color:#64748b;">({html.escape(text["local"])}, {html.escape(local_offset)})</span>
      </div>
      <div style="font-size: 1.2rem; font-weight: 650;">
        {html.escape(utc_text)} <span style="color:#64748b;">({html.escape(text["utc"])}, {html.escape(utc_offset)})</span>
      </div>
    </div>
    """


def require_dashboard_auth(st, text: dict[str, str]) -> bool:
    if not is_dashboard_auth_enabled():
        return True

    users = parse_dashboard_auth_users()
    if not users:
        st.error(text["auth_not_configured"])
        return False

    if get_authenticated_dashboard_user(st, users):
        return True

    if st.session_state.pop(DASHBOARD_AUTH_SESSION_EXPIRED_KEY, False):
        render_cookie_script(st, None, 0)
        return False

    cookie_token = get_dashboard_auth_cookie(st)
    cookie_auth = verify_dashboard_auth_cookie(cookie_token, users)
    if cookie_auth:
        cookie_username, cookie_expires_at = cookie_auth
        set_dashboard_auth_session(st, cookie_username, cookie_expires_at)
        return True

    clear_dashboard_auth_session(st)
    if cookie_token:
        render_cookie_script(st, None, 0)
        return False

    st.subheader(text["login_title"])
    with st.form("dashboard_login_form", clear_on_submit=False):
        username = st.text_input(text["login_user"])
        password = st.text_input(text["login_password"], type="password")
        submitted = st.form_submit_button(text["login_button"])

    if submitted:
        encoded_hash = users.get(username.strip())
        if encoded_hash and verify_dashboard_password(password, encoded_hash):
            authenticated_user = username.strip()
            expires_at = get_dashboard_auth_expires_at(authenticated_user)
            set_dashboard_auth_session(st, authenticated_user, expires_at)
            token = build_dashboard_auth_cookie(authenticated_user, expires_at)
            st.success(text["login_success"])
            render_cookie_script(
                st,
                token,
                get_dashboard_auth_cookie_max_age_seconds(authenticated_user),
            )
            return False

        st.error(text["login_failed"])

    return False


def render_dashboard_logout(st, text: dict[str, str]) -> None:
    if not is_dashboard_auth_enabled():
        return

    authenticated_user = st.session_state.get(DASHBOARD_AUTH_SESSION_KEY)
    if not authenticated_user:
        return

    st.caption(authenticated_user)
    if st.button(text["logout"], use_container_width=True):
        clear_dashboard_auth_session(st)
        st.success(text["logout_success"])
        render_cookie_script(st, None, 0)


def format_snapshot_value(metric_name: str, value) -> str:
    if value is None:
        return "-"

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)

    if metric_name in {"fault", "fault_code", "inverter_id"}:
        return str(int(round(numeric)))

    if metric_name == "total_generation_kwh":
        return f"{numeric:.3f}"

    if metric_name in {
        "input_dc_current_a",
        "output_ac_current_a",
        "output_ac_power_factor_pct",
        "output_ac_frequency_hz",
    }:
        return f"{numeric:.2f}"

    return f"{numeric:.1f}"


def render_latest_metric_board(st, latest, metric_labels: dict[str, str]) -> None:
    metric_order = [
        "total_generation_kwh",
        "input_dc_power_w",
        "output_ac_power_w",
        "input_dc_voltage_v",
        "output_ac_voltage_v",
        "input_dc_current_a",
        "output_ac_current_a",
        "output_ac_power_factor_pct",
        "output_ac_frequency_hz",
        "fault_code",
        "fault",
    ]
    items = []

    for metric_name in metric_order:
        label = metric_labels.get(metric_name, metric_name)
        value = format_snapshot_value(metric_name, latest.get(metric_name))
        items.append(f"""
        <div class="latest-metric">
          <div class="latest-metric-label">{html.escape(label)}</div>
          <div class="latest-metric-value">{html.escape(value)}</div>
        </div>
        """)

    st.markdown(
        f"""
        <div class="latest-metric-grid">
          {''.join(items)}
        </div>
        <style>
          .latest-metric-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1.1rem 2rem;
            margin-top: 0.5rem;
            margin-bottom: 1.5rem;
          }}
          .latest-metric {{
            border-top: 1px solid #e5e7eb;
            padding-top: 0.7rem;
            min-width: 0;
          }}
          .latest-metric-label {{
            color: #475569;
            font-size: 0.86rem;
            line-height: 1.3;
            margin-bottom: 0.25rem;
          }}
          .latest-metric-value {{
            color: #1f2937;
            font-size: 1.85rem;
            line-height: 1.15;
            font-weight: 520;
            word-break: break-word;
          }}
          @media (max-width: 900px) {{
            .latest-metric-grid {{
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
          }}
          @media (max-width: 640px) {{
            .latest-metric-grid {{
              grid-template-columns: 1fr;
            }}
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def chart_title(metric_name: str, latest, metric_labels: dict[str, str]) -> str:
    label = metric_labels.get(metric_name, metric_name)
    value = format_snapshot_value(metric_name, latest.get(metric_name))

    # Merge trailing unit from label (e.g. "... (W)") into "(value unit)".
    unit = None
    base_label = label

    if label.endswith(")") and " (" in label:
        base_label, trailing = label.rsplit(" (", 1)
        unit_candidate = trailing[:-1].strip()
        if unit_candidate:
            unit = unit_candidate
        else:
            base_label = label

    if unit is not None:
        return f"{base_label} ({value} {unit})"

    return f"{label} ({value})"


def build_nonzero_metric_domain(values) -> list[float] | None:
    numeric_values = []

    for value in values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue

        if math.isnan(numeric) or numeric == 0:
            continue

        numeric_values.append(numeric)

    if not numeric_values:
        return None

    min_value = min(numeric_values)
    max_value = max(numeric_values)

    if min_value == max_value:
        lower = math.floor(min_value) - 1
        upper = math.ceil(max_value) + 1
        return [float(lower), float(upper)]

    padding = (max_value - min_value) * 0.03
    lower = math.floor(min_value - padding)
    upper = math.ceil(max_value + padding)

    if lower == upper:
        upper += 1

    return [float(lower), float(upper)]


def render_area_echart(
    st,
    chart_df,
    metric_name: str,
    metric_label: str,
    since: datetime,
    until: datetime,
    fixed_time_axis: bool,
) -> None:
    from streamlit_echarts import st_echarts

    chart_data = (
        chart_df[[metric_name]]
        .reset_index()
        .rename(columns={metric_name: "value"})
        .dropna(subset=["timestamp", "value"])
    )

    if chart_data.empty:
        return

    points = []
    for _, row in chart_data.iterrows():
        points.append([row["timestamp"].isoformat(), float(row["value"])])

    domain = build_nonzero_metric_domain(chart_data["value"])
    y_min = None
    y_max = None
    if domain is not None:
        y_min, y_max = domain

    x_axis = {
        "type": "time",
        "axisLabel": {
            "formatter": "{MM}-{dd} {HH}:{mm}",
            "hideOverlap": True,
            "interval": "auto",
        },
    }

    if fixed_time_axis:
        x_axis["min"] = since.isoformat()
        x_axis["max"] = until.isoformat()

    color = AREA_CHART_COLORS.get(metric_name, "#3b82f6")
    latest_timestamp = chart_data["timestamp"].max().isoformat()
    latest_value = float(chart_data["value"].iloc[-1])
    chart_key = (
        f"echart_area_{metric_name}_"
        f"{latest_timestamp}_"
        f"{latest_value:.6f}_"
        f"{len(chart_data)}"
    )

    options = {
        "animation": False,
        "grid": {"left": 70, "right": 24, "top": 24, "bottom": 56},
        "xAxis": x_axis,
        "yAxis": {
            "type": "value",
            "name": metric_label,
            "scale": True,
            "min": y_min,
            "max": y_max,
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "line"},
        },
        "series": [
            {
                "name": metric_label,
                "type": "line",
                "showSymbol": False,
                "smooth": True,
                "lineStyle": {"width": 2, "color": color},
                "areaStyle": {"opacity": 0.18, "color": color},
                "itemStyle": {"color": color},
                "data": points,
            }
        ],
    }

    st_echarts(
        options=options,
        height="320px",
        renderer="svg",
        key=chart_key,
    )


def render_area_chart(
    st,
    chart_df,
    metric_name: str,
    metric_label: str,
    since: datetime,
    until: datetime,
    fixed_time_axis: bool,
) -> None:
    render_area_echart(
        st=st,
        chart_df=chart_df,
        metric_name=metric_name,
        metric_label=metric_label,
        since=since,
        until=until,
        fixed_time_axis=fixed_time_axis,
    )


def render_total_generation_echart(
    st,
    chart_data,
    metric_label: str,
    since: datetime,
    until: datetime,
    fixed_time_axis: bool,
) -> None:
    from streamlit_echarts import st_echarts

    if chart_data.empty:
        return

    echart_data = chart_data.dropna(subset=["timestamp", "value"]).copy()
    if echart_data.empty:
        return

    points = []
    for _, row in echart_data.iterrows():
        timestamp = row["timestamp"]
        value = row["value"]
        points.append([timestamp.isoformat(), float(value)])

    domain = build_nonzero_metric_domain(echart_data["value"])
    y_min = None
    y_max = None
    if domain is not None:
        y_min, y_max = domain

    x_axis = {
        "type": "time",
        "axisLabel": {
            "formatter": "{MM}-{dd} {HH}:{mm}",
            "hideOverlap": True,
            "interval": "auto",
        },
    }

    if fixed_time_axis:
        x_axis["min"] = since.isoformat()
        x_axis["max"] = until.isoformat()

    latest_timestamp = echart_data["timestamp"].max().isoformat()
    latest_value = float(echart_data["value"].iloc[-1])
    chart_key = (
        "echart_total_generation_"
        f"{latest_timestamp}_"
        f"{latest_value:.6f}_"
        f"{len(echart_data)}"
    )

    options = {
        # Auto refresh re-runs the script; disable animation to reduce visual flicker.
        "animation": False,
        "grid": {"left": 70, "right": 24, "top": 24, "bottom": 56},
        "xAxis": x_axis,
        "yAxis": {
            "type": "value",
            "name": metric_label,
            "scale": True,
            "min": y_min,
            "max": y_max,
            "minInterval": 1,
            "axisLabel": {"formatter": "{value}"},
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "line"},
        },
        "series": [
            {
                "name": metric_label,
                "type": "bar",
                "barMaxWidth": 18,
                "itemStyle": {"color": BAR_CHART_COLORS["total_generation_kwh"]},
                "data": points,
            }
        ],
    }

    st_echarts(
        options=options,
        height="320px",
        renderer="svg",
        key=chart_key,
    )


def render_bar_chart(
    st,
    chart_df,
    metric_name: str,
    metric_label: str,
    since: datetime,
    until: datetime,
    fixed_time_axis: bool,
) -> None:
    from streamlit_echarts import st_echarts

    color = BAR_CHART_COLORS.get(metric_name, "#16a34a")
    chart_data = (
        chart_df[[metric_name]]
        .reset_index()
        .rename(columns={metric_name: "value"})
        .dropna(subset=["timestamp", "value"])
    )

    if chart_data.empty:
        return

    if metric_name == "total_generation_kwh":
        render_total_generation_echart(
            st=st,
            chart_data=chart_data,
            metric_label=metric_label,
            since=since,
            until=until,
            fixed_time_axis=fixed_time_axis,
        )
        return

    points = []
    for _, row in chart_data.iterrows():
        points.append([row["timestamp"].isoformat(), float(row["value"])])

    x_axis = {
        "type": "time",
        "axisLabel": {
            "formatter": "{MM}-{dd} {HH}:{mm}",
            "hideOverlap": True,
            "interval": "auto",
        },
    }

    if fixed_time_axis:
        x_axis["min"] = since.isoformat()
        x_axis["max"] = until.isoformat()

    y_axis = {
        "type": "value",
        "name": metric_label,
        "scale": True,
    }

    if metric_name == "fault":
        y_axis["min"] = 0
        y_axis["max"] = 1
        y_axis["minInterval"] = 1
        y_axis["axisLabel"] = {"formatter": "{value}"}
    elif metric_name == "fault_code":
        y_axis["min"] = 0
        y_axis["minInterval"] = 1
        y_axis["axisLabel"] = {"formatter": "{value}"}

    latest_timestamp = chart_data["timestamp"].max().isoformat()
    latest_value = float(chart_data["value"].iloc[-1])
    chart_key = (
        f"echart_bar_{metric_name}_"
        f"{latest_timestamp}_"
        f"{latest_value:.6f}_"
        f"{len(chart_data)}"
    )

    options = {
        "animation": False,
        "grid": {"left": 70, "right": 24, "top": 24, "bottom": 56},
        "xAxis": x_axis,
        "yAxis": y_axis,
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
        },
        "series": [
            {
                "name": metric_label,
                "type": "bar",
                "barMaxWidth": 18,
                "itemStyle": {"color": color},
                "data": points,
            }
        ],
    }

    st_echarts(
        options=options,
        height="320px",
        renderer="svg",
        key=chart_key,
    )


def validate_bucket_seconds(bucket_seconds: int) -> int:
    if bucket_seconds not in BUCKET_SECONDS:
        raise RuntimeError(f"Invalid aggregation interval: {bucket_seconds}")

    return bucket_seconds


def read_sqlite_data(
    since: datetime,
    until: datetime,
    limit: int,
    bucket_seconds: int,
):
    import pandas as pd

    bucket_seconds = validate_bucket_seconds(bucket_seconds)
    config = get_sqlite_config()
    database_path = Path(config["path"]).expanduser()
    table = require_sqlite_identifier(config["table"], "table")

    if not database_path.is_file():
        raise RuntimeError(f"SQLite database not found: {database_path}")

    metric_selects = build_aggregate_selects('"')
    sql = (
        "SELECT "
        "datetime((CAST(strftime('%s', timestamp) AS INTEGER) / ?) * ?, 'unixepoch') "
        "AS timestamp, "
        'MIN("inverter_name") AS "inverter_name", '
        'MIN("inverter_id") AS "inverter_id", '
        f"{metric_selects} "
        f'FROM "{table}" '
        "WHERE timestamp >= ? AND timestamp <= ? "
        "GROUP BY (CAST(strftime('%s', timestamp) AS INTEGER) / ?) "
        "ORDER BY timestamp DESC LIMIT ?"
    )

    with sqlite3.connect(database_path) as connection:
        ensure_sqlite_table(connection, table)
        df = pd.read_sql_query(
            sql,
            connection,
            params=[
                bucket_seconds,
                bucket_seconds,
                since.isoformat(),
                until.isoformat(),
                bucket_seconds,
                limit,
            ],
        )

    df = normalize_dataframe(df)
    mode_df = read_sqlite_fault_code_mode_data(
        database_path=database_path,
        table=table,
        since=since,
        until=until,
        limit=limit,
        bucket_seconds=bucket_seconds,
    )
    return merge_mode_fault_code(df, mode_df)


def read_mariadb_data(
    since: datetime,
    until: datetime,
    limit: int,
    bucket_seconds: int,
):
    import pandas as pd
    import pymysql

    bucket_seconds = validate_bucket_seconds(bucket_seconds)
    config = get_mariadb_config()
    validate_mariadb_config(config)
    table = require_mariadb_identifier(config["table"], "table")
    metric_selects = build_aggregate_selects("`")
    sql = (
        "SELECT "
        "FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(`timestamp`) / %s) * %s) AS `timestamp`, "
        "MIN(`inverter_name`) AS `inverter_name`, "
        "MIN(`inverter_id`) AS `inverter_id`, "
        f"{metric_selects} "
        f"FROM `{table}` "
        "WHERE `timestamp` >= %s AND `timestamp` <= %s "
        "GROUP BY FLOOR(UNIX_TIMESTAMP(`timestamp`) / %s) "
        "ORDER BY `timestamp` DESC LIMIT %s"
    )

    since_naive = since.astimezone(timezone.utc).replace(tzinfo=None)
    until_naive = until.astimezone(timezone.utc).replace(tzinfo=None)

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
            cursor.execute("SET time_zone = '+00:00'")

        df = pd.read_sql_query(
            sql,
            connection,
            params=[
                bucket_seconds,
                bucket_seconds,
                since_naive,
                until_naive,
                bucket_seconds,
                limit,
            ],
        )

    df = normalize_dataframe(df)
    mode_df = read_mariadb_fault_code_mode_data(
        config=config,
        table=table,
        since=since_naive,
        until=until_naive,
        limit=limit,
        bucket_seconds=bucket_seconds,
    )
    return merge_mode_fault_code(df, mode_df)


def read_fault_events(
    source: str,
    since: datetime,
    until: datetime,
    limit: int = 200,
):
    if source == "MariaDB":
        config = get_mariadb_config()
        validate_mariadb_config(config)
        table = require_mariadb_identifier(config["table"], "table")
        since_naive = since.astimezone(timezone.utc).replace(tzinfo=None)
        until_naive = until.astimezone(timezone.utc).replace(tzinfo=None)
        return read_mariadb_fault_events(
            config=config,
            table=table,
            since=since_naive,
            until=until_naive,
            limit=limit,
        )

    config = get_sqlite_config()
    database_path = Path(config["path"]).expanduser()
    table = require_sqlite_identifier(config["table"], "table")
    if not database_path.is_file():
        raise RuntimeError(f"SQLite database not found: {database_path}")

    return read_sqlite_fault_events(
        database_path=database_path,
        table=table,
        since=since,
        until=until,
        limit=limit,
    )


def render_fault_events_table(
    st,
    fault_events_df,
    text: dict[str, str],
) -> None:
    import pandas as pd

    if fault_events_df.empty:
        st.caption(text["fault_events_empty"])
        return

    display_df = fault_events_df.copy()
    display_df = display_df.sort_values("timestamp", ascending=False).head(200)
    display_df["fault_code"] = pd.to_numeric(
        display_df["fault_code"],
        errors="coerce",
    ).fillna(0).astype(int)
    display_df[text["active_bits"]] = display_df["fault_code"].map(
        lambda code: format_active_bits(int(code))
    )
    display_df[text["fault_code_label"]] = display_df["fault_code"].map(
        lambda code: get_fault_code_label(int(code)) or f"FAULT CODE {int(code)}"
    )

    st.dataframe(
        display_df[[
            "timestamp",
            "inverter_name",
            "inverter_id",
            "fault_code",
            text["active_bits"],
            text["fault_code_label"],
        ]],
        use_container_width=True,
        hide_index=True,
    )


def render_dashboard_body(
    st,
    source: str,
    range_name: str,
    bucket_seconds: int,
    limit: int,
    text: dict[str, str],
    metric_labels: dict[str, str],
    lang: str,
    dashboard_title: str,
    display_timezone: ZoneInfo,
    fixed_time_axis: bool,
) -> None:
    since, until = get_time_bounds(range_name, display_timezone)

    try:
        if source == "MariaDB":
            df = read_mariadb_data(
                since,
                until,
                int(limit),
                bucket_seconds,
            )
        else:
            df = read_sqlite_data(
                since,
                until,
                int(limit),
                bucket_seconds,
            )
    except Exception as e:
        st.error(str(e))
        return

    if df.empty:
        st.warning(text["no_rows"])
        return

    latest = df.sort_values("timestamp").iloc[-1]
    inverter_name = latest.get("inverter_name", "")
    inverter_id = int(latest.get("inverter_id", 0))
    try:
        output_ac_power_w = float(latest.get("output_ac_power_w", 0.0))
    except (TypeError, ValueError):
        output_ac_power_w = 0.0

    standby_threshold_w = get_dashboard_standby_power_w_threshold()
    is_standby = output_ac_power_w <= standby_threshold_w

    try:
        fault_code = int(latest.get("fault_code", 0))
    except (TypeError, ValueError):
        fault_code = 0

    operation_stopped = is_operation_stopped(fault_code)
    fault = 1 if has_fault_condition(fault_code) else 0

    if fault:
        fault_label = text["fault_fault"]
        fault_color = "#dc2626"
        fault_bg = "#fee2e2"
        fault_badge_text = f"{fault_label} ({fault})"
    elif is_standby or operation_stopped:
        fault_label = text["fault_standby"]
        fault_color = "#475569"
        fault_bg = "#e2e8f0"
        fault_badge_text = fault_label
    else:
        fault_label = text["fault_normal"]
        fault_color = "#16a34a"
        fault_bg = "#dcfce7"
        fault_badge_text = f"{fault_label} ({fault})"

    fault_code_label = get_fault_code_label(fault_code)

    st.markdown(
        f"""
        <div style="
            font-size: 1.75rem;
            line-height: 1.35;
            margin-bottom: 1rem;
            font-weight: 650;
            color: #1f2937;
        ">
          <strong>{text["inverter"]}:</strong> {html.escape(str(inverter_name))}
          <span style="margin-left: 1.5rem;"><strong>{text["id"]}:</strong> {inverter_id}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary_columns = st.columns([2, 1])
    with summary_columns[0]:
        st.markdown(
            render_latest_timestamp(latest["timestamp"], text, display_timezone),
            unsafe_allow_html=True,
        )
    summary_columns[1].markdown(
        f"""
        <div style="font-size: 0.875rem; margin-bottom: 0.25rem;">{text["status"]}</div>
        <div style="
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.65rem;
            border-radius: 0.4rem;
            color: {fault_color};
            background: {fault_bg};
            border: 1px solid {fault_color};
            font-weight: 700;
            letter-spacing: 0.02em;
        ">{fault_badge_text}</div>
        {
            (
                f'<div style="margin-top:0.45rem; font-size:0.95rem; color:#991b1b; font-weight:600;">{html.escape(fault_code_label or f"FAULT CODE {fault_code}")}</div>'
                if fault
                else ""
            )
        }
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height: 1.25rem;"></div>', unsafe_allow_html=True)
    st.subheader(text["latest_snapshot"])
    render_latest_metric_board(st, latest, metric_labels)

    chart_df = df.sort_values("timestamp").set_index("timestamp")
    st.subheader(text["metric_charts"])
    st.caption(
        text["chart_caption"].format(
            bucket=BUCKET_LABELS[lang][bucket_seconds],
        )
    )

    for group in CHART_GROUPS:
        if len(group) == 1:
            metric_name = group[0]
            st.markdown(f"#### {chart_title(metric_name, latest, metric_labels)}")
            if metric_name in BAR_CHART_COLORS:
                render_bar_chart(
                    st,
                    chart_df,
                    metric_name,
                    metric_labels[metric_name],
                    since,
                    until,
                    fixed_time_axis,
                )
            else:
                render_area_chart(
                    st,
                    chart_df,
                    metric_name,
                    metric_labels[metric_name],
                    since,
                    until,
                    fixed_time_axis,
                )
            continue

        chart_columns = st.columns(2)

        for column, metric_name in zip(chart_columns, group):
            with column:
                st.markdown(f"#### {chart_title(metric_name, latest, metric_labels)}")
                if metric_name in BAR_CHART_COLORS:
                    render_bar_chart(
                        st,
                        chart_df,
                        metric_name,
                        metric_labels[metric_name],
                        since,
                        until,
                        fixed_time_axis,
                    )
                else:
                    render_area_chart(
                        st,
                        chart_df,
                        metric_name,
                        metric_labels[metric_name],
                        since,
                        until,
                        fixed_time_axis,
                    )

    st.subheader(text["fault_events"])
    st.caption(text["fault_events_caption"])
    try:
        fault_events_df = read_fault_events(source, since, until, limit=200)
    except Exception as e:
        st.warning(str(e))
    else:
        render_fault_events_table(st, fault_events_df, text)

    st.subheader(text["latest_rows"])
    display_columns = [
        "timestamp",
        "inverter_name",
        "inverter_id",
        "total_generation_kwh",
        *[
            metric_name
            for metric_name in DEFAULT_METRICS
            if metric_name != "total_generation_kwh"
        ],
    ]
    st.markdown(
        render_latest_rows_table(df, display_columns, lang),
        unsafe_allow_html=True,
    )


def run_app() -> None:
    import streamlit as st

    load_config()
    dashboard_title = get_dashboard_title()
    display_timezone = get_timezone()

    st.set_page_config(
        page_title=dashboard_title,
        layout="wide",
    )

    auth_text = UI_TEXT["en"]
    st.title(dashboard_title)
    if not require_dashboard_auth(st, auth_text):
        return

    with st.sidebar:
        if "dashboard_lang" not in st.session_state:
            st.session_state["dashboard_lang"] = get_dashboard_language()

        current_lang = st.session_state["dashboard_lang"]
        if current_lang not in {"ko", "en"}:
            current_lang = get_dashboard_language()
            st.session_state["dashboard_lang"] = current_lang

        language_choice = st.selectbox(
            UI_TEXT[current_lang]["language"],
            ["ko", "en"],
            index=0 if current_lang == "ko" else 1,
            format_func=lambda value: "한국어" if value == "ko" else "English",
            key="dashboard_lang_selector",
        )

        if language_choice != current_lang:
            st.session_state["dashboard_lang"] = language_choice
            st.rerun()

        lang = st.session_state["dashboard_lang"]
        text = UI_TEXT[lang]
        metric_labels = METRIC_LABELS[lang]

        st.header(text["data_source"])
        source = "MariaDB"
        st.caption("MariaDB")
        # SQLite support is intentionally kept in the code path, but hidden from
        # the default UI. Re-enable this selector if SQLite dashboard access is
        # needed again.
        # source = st.radio(text["source"], ["MariaDB", "SQLite"], horizontal=True)
        range_name = st.selectbox(
            text["range"],
            list(RANGES.keys()),
            index=list(RANGES.keys()).index("Today"),
            format_func=lambda value: RANGE_LABELS[lang][value],
        )
        bucket_seconds = st.selectbox(
            text["bucket_minutes"],
            BUCKET_SECONDS,
            index=BUCKET_SECONDS.index(600),
            format_func=lambda value: BUCKET_LABELS[lang][value],
        )
        limit = st.number_input(
            text["max_points"],
            min_value=100,
            max_value=300000,
            value=50000,
            step=1000,
        )
        st.caption(
            text["aggregate_caption"].format(
                bucket=BUCKET_LABELS[lang][bucket_seconds],
            )
        )
        default_refresh_seconds = get_dashboard_auto_refresh_seconds()
        refresh_seconds = st.selectbox(
            text["auto_refresh"],
            REFRESH_SECONDS,
            index=REFRESH_SECONDS.index(default_refresh_seconds),
            format_func=lambda value: REFRESH_LABELS[lang][value],
        )
        axis_mode = st.selectbox(
            text["x_axis_mode"],
            ["fixed", "auto"],
            index=0,
            format_func=lambda value: text[f"x_axis_mode_{value}"],
        )
        fixed_time_axis = axis_mode == "fixed"
        render_dashboard_logout(st, text)

    if hasattr(st, "fragment"):
        run_every = f"{refresh_seconds}s" if refresh_seconds > 0 else None

        @st.fragment(run_every=run_every)
        def dashboard_fragment() -> None:
            if not require_dashboard_auth(st, text):
                return

            render_dashboard_body(
                st=st,
                source=source,
                range_name=range_name,
                bucket_seconds=bucket_seconds,
                limit=int(limit),
                text=text,
                metric_labels=metric_labels,
                lang=lang,
                dashboard_title=dashboard_title,
                display_timezone=display_timezone,
                fixed_time_axis=fixed_time_axis,
            )

        dashboard_fragment()
        return

    render_dashboard_body(
        st=st,
        source=source,
        range_name=range_name,
        bucket_seconds=bucket_seconds,
        limit=int(limit),
        text=text,
        metric_labels=metric_labels,
        lang=lang,
        dashboard_title=dashboard_title,
        display_timezone=display_timezone,
        fixed_time_axis=fixed_time_axis,
    )


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(f"solar-rs485-monitor-dashboard {get_version()}")
        return

    if "--hash-password" in sys.argv[1:]:
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            raise SystemExit("Passwords do not match")
        if not password:
            raise SystemExit("Password must not be empty")
        print(hash_dashboard_password(password))
        return

    load_config()
    cli_args = sys.argv[1:]

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        *build_streamlit_args(cli_args),
        *cli_args,
        str(Path(__file__).resolve()),
    ]
    stcli.main()


if __name__ == "__main__":
    run_app()
